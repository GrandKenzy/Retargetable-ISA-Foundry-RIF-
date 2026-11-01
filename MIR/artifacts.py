"""Execution of assembler-side binary directives."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from Frontend import globals
from rif_limits import resolve_limits

from .emitter import BitEmitter
from .functions import CalcError, calc
from .output import AssemblyImage
from .runtime import RIFMachine


MAX_ARTIFACT_BYTES = 128 << 20


class ArtifactError(RuntimeError):
    """An insert or final patch could not be resolved safely."""


@dataclass(frozen=True)
class InsertData:
    """One assembler-side binary prelude."""

    section: str
    kind: str
    value: Any
    source_path: str | None = None


@dataclass(frozen=True)
class PatchData:
    """One assembler-side final patch evaluated after layout."""

    offset: int
    width: int | None
    expression: Any
    source_path: str | None = None


@dataclass(frozen=True)
class BinaryValue:
    data: bytes
    bit_width: int


@dataclass(frozen=True)
class ScalarValue:
    value: int
    width: int


_EXPRESSION_VALUE_KINDS = {"NUMBER", "DECIMAL", "STRING", "IDENT", "BOOL"}
_NATIVE_QUERY_KINDS = {"query", "qssize", "qlsize", "qvsize", "qvssize"}


def _token_kind(token: Any) -> str:
    return getattr(getattr(token, "token", None), "name", "")


def _token_value(token: Any) -> Any:
    return getattr(token, "value", None)


class _ExpressionParser:
    """Parse the closed native expression subset used by assembler patches."""

    def __init__(self, tokens: tuple[Any, ...]) -> None:
        self.tokens = tokens
        self.index = 0

    def _peek(self) -> Any | None:
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def _take(self, expected: str | None = None) -> Any:
        token = self._peek()
        if token is None:
            raise RuntimeError("Expresión nativa incompleta.")
        if expected is not None and _token_kind(token) != expected:
            raise RuntimeError(
                f"Se esperaba {expected} y se encontró {_token_kind(token)}."
            )
        self.index += 1
        return token

    def expression(self, *, stop: str | None = None) -> dict[str, Any]:
        left = self.atom()
        while self._peek() is not None:
            if stop is not None and _token_kind(self._peek()) == stop:
                break
            current = self._peek()
            if _token_kind(current) not in {"PLUS", "MINUS"}:
                break
            operator = "+" if _token_kind(self._take()) == "PLUS" else "-"
            right = self.atom()
            left = {"kind": "calc", "operator": operator, "left": left, "right": right}
        return left

    def atom(self) -> dict[str, Any]:
        token = self._peek()
        if token is None:
            raise RuntimeError("Expresión nativa incompleta.")
        if _token_kind(token) == "LPAREN":
            self._take("LPAREN")
            value = self.expression(stop="RPAREN")
            self._take("RPAREN")
            return value
        if _token_kind(token) == "HASH":
            if self.index + 1 < len(self.tokens) and _token_value(self.tokens[self.index + 1]) == "call":
                raise RuntimeError("::RIF_PATCH no permite #call[...].")
            return self.native()
        current = self._take()
        kind = _token_kind(current)
        if kind not in _EXPRESSION_VALUE_KINDS:
            raise RuntimeError(f"Se esperaba un valor y se encontró {kind or 'desconocido'}.")
        return {"kind": "literal", "token": kind, "value": _token_value(current)}

    def native(self) -> dict[str, Any]:
        self._take("HASH")
        self._take("COLON")
        name = str(_token_value(self._take()))
        if name == "calc":
            if self._peek() is not None and _token_kind(self._peek()) == "LPAREN":
                self._take("LPAREN")
                expression = self.expression(stop="RPAREN")
                self._take("RPAREN")
            else:
                expression = self.expression()
            return expression
        if name not in _NATIVE_QUERY_KINDS:
            raise RuntimeError(f"Función nativa desconocida: #:{name}.")
        parenthesized = self._peek() is not None and _token_kind(self._peek()) == "LPAREN"
        if parenthesized:
            self._take("LPAREN")
        first = self.atom()
        self._take("COMMA")
        second = self.atom()
        if parenthesized:
            self._take("RPAREN")
        return {"kind": name, "args": [first, second]}

    def finish(self) -> dict[str, Any]:
        result = self.expression()
        if self._peek() is not None:
            raise RuntimeError("Sobran tokens al final de la expresión nativa.")
        return result


def parse_patch_tokens(
    tokens: tuple[Any, ...], source_path: str | None = None
) -> PatchData:
    """Materialize one ``::RIF_PATCH`` payload without involving the frontend."""

    if len(tokens) < 2 or _token_kind(tokens[0]) not in {"NUMBER", "DECIMAL"} or _token_kind(tokens[1]) != "COMMA":
        raise RuntimeError("::RIF_PATCH requiere offset y payload.")
    offset = _token_value(tokens[0])
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise RuntimeError("El offset de ::RIF_PATCH debe ser un entero no negativo.")
    payload = tokens[2:]
    width: int | None = None
    if len(payload) >= 2 and _token_kind(payload[0]) in {"NUMBER", "DECIMAL"} and _token_kind(payload[1]) == "COMMA":
        width = _token_value(payload[0])
        if isinstance(width, bool) or not isinstance(width, int) or width <= 0:
            raise RuntimeError("El ancho de ::RIF_PATCH debe ser un entero mayor que cero.")
        payload = payload[2:]
    if not payload:
        raise RuntimeError("::RIF_PATCH requiere un payload.")
    expression = _ExpressionParser(tuple(payload)).finish()
    return PatchData(offset, width, expression, source_path)


def _hex_to_bytes(value: str) -> bytes:
    normalized = value.removeprefix("0x").replace(" ", "").replace("_", "")
    if not normalized or len(normalized) % 2 or any(char not in "0123456789abcdefABCDEF" for char in normalized):
        raise ArtifactError("::RIF_INSERT BYTES requiere una cadena hexadecimal de bytes completos.")
    if len(normalized) // 2 > resolve_limits().cap(MAX_ARTIFACT_BYTES):
        raise ArtifactError("::RIF_INSERT BYTES excede el límite de recursos configurado.")
    return bytes.fromhex(normalized)


def _binary_value(value: str, config: globals.ConfigData) -> BinaryValue:
    if not isinstance(value, str):
        raise ArtifactError("El payload binario debe ser un string.")
    if not value or any(bit not in "01" for bit in value):
        raise ArtifactError("El payload binario debe contener solamente 0 y 1.")
    maximum_bits = resolve_limits().cap(MAX_ARTIFACT_BYTES) * 8
    if len(value) > maximum_bits:
        raise ArtifactError("El payload binario excede el límite de recursos configurado.")
    if len(value) % 8:
        return BinaryValue(b"", len(value))
    data = bytes(
        int(value[offset : offset + 8], 2)
        for offset in range(0, len(value), 8)
    )
    if config.bitorder == "lsb":
        data = data[::-1]
    return BinaryValue(data, len(value))


def _file_payload(
    path_value: str,
    source_path: str | None,
    assets: Mapping[str, bytes],
) -> bytes:
    normalized = path_value.replace("\\", "/")
    requested = Path(normalized)
    if requested.is_absolute() or ".." in requested.parts:
        raise ArtifactError(f"El asset '{path_value}' usa una ruta no permitida.")
    asset_key = normalized
    packaged_source = False
    if source_path and source_path.startswith("pack://") and "::" in source_path:
        packaged_source = True
        source_key = source_path.rsplit("::", 1)[1].replace("\\", "/")
        if source_key.startswith("sources/"):
            asset_key = str(Path(source_key.removeprefix("sources/")).parent / Path(normalized)).replace("\\", "/")
    elif source_path and source_path.startswith("sources/"):
        packaged_source = True
        asset_key = str(Path(source_path.removeprefix("sources/")).parent / Path(normalized)).replace("\\", "/")
    if asset_key in assets:
        return bytes(assets[asset_key])
    if packaged_source:
        raise ArtifactError(f"El asset '{path_value}' no está incluido en el paquete.")
    base = Path(source_path).expanduser().resolve().parent if source_path else Path.cwd()
    candidate = (base / path_value).resolve(strict=False)
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise ArtifactError(f"El asset '{path_value}' intenta salir del proyecto.") from exc
    if not candidate.is_file():
        raise FileNotFoundError(f"No se encontró el asset binario: {candidate}")
    maximum = resolve_limits().cap(MAX_ARTIFACT_BYTES)
    if candidate.stat().st_size > maximum:
        raise ArtifactError("El asset excede el límite de recursos configurado.")
    return candidate.read_bytes()


def apply_insert_directives(
    image: AssemblyImage,
    inserts: tuple[Any, ...],
    *,
    assets: Mapping[str, bytes] | None = None,
) -> None:
    """Apply all preludes in declaration order before external MIR runs."""

    config = image.config
    asset_map = assets or {}
    for insert in inserts:
        section_name = insert.section or config.defaultsection
        emitter = image.emitter(section_name)
        if insert.kind == "binary":
            binary = _binary_value(str(insert.value), config)
            emitter.bits(str(insert.value), binary.bit_width)
        elif insert.kind == "bytes":
            emitter.emit_bytes(_hex_to_bytes(str(insert.value)))
        elif insert.kind == "file":
            emitter.emit_bytes(_file_payload(str(insert.value), insert.source_path, asset_map))
        elif insert.kind == "call":
            raise ArtifactError(
                f"No existe una función nativa registrada para #call[{insert.value}]."
            )
        else:
            raise ArtifactError(f"Tipo de insert desconocido: {insert.kind}.")
    image.invalidate_layout()


def _as_int(value: Any, label: str) -> int:
    if isinstance(value, ScalarValue):
        return value.value
    raise ArtifactError(f"{label} requiere un valor numérico.")


def _literal_value(
    expression: dict[str, Any], config: globals.ConfigData
) -> BinaryValue | ScalarValue:
    token = expression.get("token")
    value = expression.get("value")
    if token in {"NUMBER", "DECIMAL"}:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ArtifactError("El escalar nativo no es numérico.")
        if isinstance(value, float):
            if not value.is_integer():
                raise ArtifactError("Los parches solo aceptan números enteros.")
            value = int(value)
        return ScalarValue(int(value), 1)
    if token == "BOOL":
        raise ArtifactError("Un booleano no puede insertarse como escalar.")
    if token == "STRING":
        if not isinstance(value, str):
            raise ArtifactError("El string nativo no es válido.")
        if value and set(value) <= {"0", "1"}:
            return _binary_value(value, config)
        raise ArtifactError("Un string directo de ::RIF_PATCH debe ser binario.")
    raise ArtifactError("El valor no es válido para una expresión nativa.")


def _label_offsets(machine: RIFMachine, *, virtual: bool = False) -> dict[str, int]:
    labels: dict[str, int] = {}
    rule_addresses = (
        machine.virtual_rule_addresses if virtual else machine.rule_addresses
    )
    regions = (
        machine.emitter.virtual_regions
        if virtual
        else machine.emitter.buffer.regions
    )
    for name, offset in rule_addresses.items():
        labels.setdefault(name, offset // 8)
    for name, span in regions.items():
        labels.setdefault(name, span.offset // 8)
    for name, symbol in machine.symbols.items():
        offset = symbol.virtual_offset_bits if virtual else symbol.physical_offset_bits
        labels.setdefault(name, offset // 8)
    return labels


def evaluate_expression(
    expression: dict[str, Any],
    *,
    image: AssemblyImage,
    machine: RIFMachine,
    working: bytes,
) -> BinaryValue | ScalarValue:
    kind = expression.get("kind")
    if kind == "literal":
        return _literal_value(expression, image.config)
    if kind == "calc":
        left = evaluate_expression(
            expression["left"], image=image, machine=machine,
            working=working,
        )
        right = evaluate_expression(
            expression["right"], image=image, machine=machine,
            working=working,
        )
        left_value = _as_int(left, "calc")
        right_value = _as_int(right, "calc")
        try:
            value, width = calc(
                expression["operator"],
                left_value,
                left.width if isinstance(left, ScalarValue) else 1,
                right_value,
                right.width if isinstance(right, ScalarValue) else 1,
            )
        except CalcError as exc:
            raise ArtifactError(str(exc)) from exc
        return ScalarValue(value, width)
    if kind == "call":
        raise ArtifactError(
            "::RIF_PATCH solo permite operaciones nativas #:; #call[...] no está permitido."
        )
    args = expression.get("args", ())
    if kind == "query":
        offset = _as_int(
            evaluate_expression(args[0], image=image, machine=machine, working=working),
            "query",
        )
        size = _as_int(
            evaluate_expression(args[1], image=image, machine=machine, working=working),
            "query",
        )
        if offset < 0 or size < 0 or offset + size > len(working):
            raise ArtifactError("#:query está fuera del binario final.")
        return BinaryValue(bytes(working[offset : offset + size]), size * 8)

    image.layout()
    base = _as_int(
        evaluate_expression(args[0], image=image, machine=machine, working=working),
        kind,
    )
    target = args[1].get("value") if isinstance(args[1], dict) else None
    if not isinstance(target, str):
        raise ArtifactError(f"#:{kind} requiere un nombre string.")
    address_width = max(1, image.config.addresssize // 8)
    if kind == "qssize":
        try:
            section = image.sections[target]
        except KeyError as exc:
            raise ArtifactError(f"No existe la sección '{target}'.") from exc
        return ScalarValue(base + section.file_offset + section.file_size, address_width)
    if kind in {"qlsize", "qvsize"}:
        labels = _label_offsets(machine, virtual=kind == "qvsize")
        if target not in labels:
            raise ArtifactError(f"No existe el label '{target}'.")
        section_name = machine.section_name or image.config.defaultsection
        section = image.sections[section_name]
        relative = labels[target]
        if kind == "qlsize":
            return ScalarValue(base + section.file_offset + relative, address_width)
        return ScalarValue(base + section.virtual_base + relative, address_width)
    if kind == "qvssize":
        try:
            section = image.sections[target]
        except KeyError as exc:
            raise ArtifactError(f"No existe la sección '{target}'.") from exc
        return ScalarValue(base + section.virtual_base + section.virtual_size, address_width)
    raise ArtifactError(f"Query nativa desconocida: {kind}.")


def _encode_value(
    value: BinaryValue | ScalarValue,
    width: int | None,
    config: globals.ConfigData,
) -> bytes:
    if isinstance(value, BinaryValue):
        if value.bit_width % 8:
            raise ArtifactError("::RIF_PATCH requiere un payload alineado a bytes.")
        data = value.data
        if width is not None and len(data) != width:
            raise ArtifactError("El ancho del payload no coincide con ::RIF_PATCH.")
        return data
    selected_width = width or value.width
    maximum = resolve_limits().cap(MAX_ARTIFACT_BYTES)
    if selected_width <= 0 or selected_width > maximum:
        raise ArtifactError("El ancho del parche excede el límite de recursos configurado.")
    if value.value < 0 or value.value >= (1 << (selected_width * 8)):
        raise ArtifactError("El escalar no cabe en el ancho del parche.")
    return value.value.to_bytes(selected_width, config.endianness, signed=False)


def apply_patch_directives(
    image: AssemblyImage,
    machine: RIFMachine,
    patches: tuple[Any, ...],
) -> bytes:
    """Evaluate and commit all final patches transactionally."""

    working = bytearray(image.layout())
    for patch in patches:
        value = evaluate_expression(
            patch.expression,
            image=image,
            machine=machine,
            working=bytes(working),
        )
        payload = _encode_value(value, patch.width, image.config)
        end = patch.offset + len(payload)
        if patch.offset < 0 or end > len(working):
            raise ArtifactError("::RIF_PATCH está fuera del binario final.")
        working[patch.offset:end] = payload
    image.set_final_bytes(bytes(working))
    return bytes(working)


__all__ = [
    "ArtifactError",
    "BinaryValue",
    "InsertData",
    "PatchData",
    "ScalarValue",
    "apply_insert_directives",
    "apply_patch_directives",
    "evaluate_expression",
    "parse_patch_tokens",
]
