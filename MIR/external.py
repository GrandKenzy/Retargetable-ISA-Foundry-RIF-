"""Entry points for compiling an external MIR program against RIF Rules."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from gram import lexer

from Frontend import RIF_LANG_SESSION, globals
from pack import PackReader
from pcpi import PCPIError, PCPI_HEADER_SIZE, load_pcpi_file
from rif_limits import COMPILATION_LOCK, resolve_limits

from .instructions import CompiledRuleSet
from .diagnostics import Diagnostic, DiagnosticBag
from .buffer import BufferResult, execute_preprocessor_buffer
from .output import AssemblyImage
from .output_map import build_output_map
from .artifacts import (
    ArtifactError,
    InsertData,
    PatchData,
    apply_insert_directives,
    apply_patch_directives,
    parse_patch_tokens,
)
from .pipeline import compile_definition
from .preprocessor import MIRLine, RIFMetaDirective, preprocess_mir_lines
from .runtime import ExecutionResult, RIFMachine, RIFRuntimeError
from .relocations import relocation_specs
from .storage import StorageError, load_storage_file


MAX_MIR_SOURCE_BYTES = 64 << 20
MAX_MIR_TOKENS = 4_000_000


class MIRInputError(ValueError):
    """An external MIR input or linker-extension error."""


@dataclass(frozen=True)
class PCPIPitAddress:
    """Absolute address reported by one ``::RIF_PCPI PIT`` query."""

    index: int
    address: int
    section: str


def _write_binary_atomic(
    output: str | Path,
    data: bytes,
    *,
    protected: tuple[Path, ...],
) -> Path:
    target = Path(output).expanduser().resolve()
    if any(target == item for item in protected):
        raise MIRInputError(f"La salida no puede sobrescribir un archivo de entrada: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_bytes(data)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


@dataclass(frozen=True)
class PreparedTarget:
    """A compiled target and its packaged binary assets."""

    program: CompiledRuleSet
    target_path: Path | None
    assets: dict[str, bytes] = field(default_factory=dict)
    buffer: BufferResult | None = None


@dataclass
class MIRCompilation:
    """Binary result of applying an external MIR program to a RIF target."""

    program: CompiledRuleSet
    image: AssemblyImage
    executions: tuple[ExecutionResult, ...]
    section: str
    binary: bytes
    context: RIFMachine
    buffer: BufferResult | None = None
    target_path: Path | None = None
    mir_path: Path | None = None
    pcpi_pit_addresses: tuple[PCPIPitAddress, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def section_binary(self) -> bytes:
        """Return only the finalized bytes of the selected section."""

        return self.image.final_binary(self.section)

    @property
    def symbols(self) -> dict[str, int]:
        """Return native symbols as absolute virtual byte addresses."""

        self.image.layout()
        return {
            name: self.image.section_virtual_base(symbol.section or self.section)
            + symbol.virtual_offset
            for name, symbol in self.context.symbols.items()
        }

    def output_map(self) -> dict[str, object]:
        """Return an optional JSON-ready map of the finalized output."""

        return build_output_map(self).as_dict()


def tokenize_mir(source: str, name: str = "<memory>") -> tuple[lexer.TokenType, ...]:
    """Tokenize MIR once for callers that do not already have tokens."""

    if not isinstance(source, str):
        raise TypeError("El MIR fuente debe ser str.")
    if len(source.encode("utf-8")) > resolve_limits().cap(MAX_MIR_SOURCE_BYTES):
        raise MIRInputError("El MIR excede el límite de 64 MiB.")
    with COMPILATION_LOCK:
        RIF_LANG_SESSION.load()
        return tuple(RIF_LANG_SESSION.tokenize(source, name))


def prepare_target(path: str | Path, *, backend: str = "aot") -> PreparedTarget:
    """Compile a ``.rif``/``.pack`` and load its binary assets."""

    target_path = Path(path).expanduser().resolve()
    if target_path.suffix.lower() not in {".rif", ".pack"}:
        raise MIRInputError("La definición RIF debe terminar en .rif o .pack.")
    program = compile_definition(target_path, backend=backend)
    assets: dict[str, bytes] = {}
    if target_path.suffix.lower() == ".pack":
        with PackReader(target_path) as package:
            assets = package.assets()
    return PreparedTarget(
        program,
        target_path,
        assets,
        None,
    )


def _prepare_target(
    target: PreparedTarget | CompiledRuleSet | str | Path,
    *,
    backend: str = "aot",
) -> PreparedTarget:
    if isinstance(target, PreparedTarget):
        return target
    if isinstance(target, CompiledRuleSet):
        return PreparedTarget(
            target,
            None,
            buffer=None,
        )
    return prepare_target(target, backend=backend)


def _require_target_config(program: CompiledRuleSet) -> globals.ConfigData:
    return validate_target(program)


def validate_target(
    program: CompiledRuleSet,
    *,
    require_linker: bool = False,
) -> globals.ConfigData:
    """Validate the target contract before accepting external MIR input.

    A target may be compiled and packaged without an input program. The
    stronger contract is enforced at the boundary where MIR is accepted:
    sections, entry/default selection, section metadata, and—when compiling a
    file—the linker extension must describe one coherent target.
    """

    config = program.context.config
    if config is None:
        raise MIRInputError("La definición RIF requiere un bloque @block config.")

    if not program.rules:
        raise MIRInputError("El target no declara ninguna Rule ejecutable.")
    for name, rule in program.rules.items():
        if not isinstance(name, str) or not name:
            raise MIRInputError("El target contiene una Rule sin nombre.")
        if rule.name != name:
            raise MIRInputError(
                f"La Rule '{name}' tiene un nombre interno inconsistente."
            )

    sections = tuple(config.sections)
    if not sections:
        raise MIRInputError("El target no declara secciones de salida.")
    if len(set(sections)) != len(sections) or any(
        not isinstance(section, str) or not section for section in sections
    ):
        raise MIRInputError("El target contiene secciones vacías o duplicadas.")
    if config.entrysection not in sections:
        raise MIRInputError(
            f"La sección de entrada '{config.entrysection}' no existe en el target."
        )
    if config.defaultsection not in sections:
        raise MIRInputError(
            f"La sección por defecto '{config.defaultsection}' no existe en el target."
        )

    declared = set(sections)
    for field_name, values in (
        ("flags", config.sectionflags),
        ("alignment", config.sectionalign),
        ("vaddr", config.sectionvaddr),
    ):
        unknown = sorted(set(values) - declared)
        if unknown:
            rendered = ", ".join(unknown)
            raise MIRInputError(
                f"La metadata de {field_name} referencia sección(es) inexistente(s): {rendered}."
            )

    if config.wordsize <= 0 or config.addresssize <= 0:
        raise MIRInputError("word_size y address_size deben ser positivos.")
    if config.wordsize % 8 or config.addresssize % 8:
        raise MIRInputError("word_size y address_size deben ser múltiplos de ocho.")
    if config.endianness not in {"little", "big"}:
        raise MIRInputError("byte_order del target debe ser 'little' o 'big'.")
    if config.bitorder not in {"msb", "lsb"}:
        raise MIRInputError("bit_order del target debe ser 'msb' o 'lsb'.")
    if config.undefinedsymbols not in {"error", "warn", "ignore"}:
        raise MIRInputError("undefined_symbols del target no es válido.")
    if config.duplicatesymbols not in {"error", "warn", "ignore"}:
        raise MIRInputError("duplicate_symbols del target no es válido.")
    if not config.entrylabel or not config.defaultsection:
        raise MIRInputError("El target requiere entry y default no vacíos.")

    for section, alignment in config.sectionalign.items():
        if section not in declared or alignment <= 0:
            raise MIRInputError(
                f"La alineación de la sección '{section}' no es válida."
            )
    for section, address in config.sectionvaddr.items():
        if section not in declared or address < 0:
            raise MIRInputError(
                f"La dirección virtual de la sección '{section}' no es válida."
            )

    for table_name, table in program.context.tables.items():
        if table_name != table.name or not table_name:
            raise MIRInputError("El target contiene una tabla sin nombre consistente.")
        if not table.headers or len(set(table.headers)) != len(table.headers):
            raise MIRInputError(
                f"La tabla '{table_name}' contiene columnas vacías o duplicadas."
            )
        if set(table.columns) != set(table.headers):
            raise MIRInputError(
                f"La tabla '{table_name}' tiene columnas inconsistentes."
            )
    try:
        relocation_specs(program.context)
    except ValueError as exc:
        raise MIRInputError(str(exc)) from exc

    supports = program.context.supports
    variants = program.context.asm_variants
    for name, support in supports.items():
        if name != support.name or not support.path:
            raise MIRInputError(f"La variante soportada '{name}' es inconsistente.")
    for name, variant in variants.items():
        if name != variant.name or name not in supports:
            raise MIRInputError(
                f"La variante '{name}' no tiene una declaración @SUPPORTS válida."
            )
        if variant.mode not in {"SWITCH", "ENCAPSULATE"}:
            raise MIRInputError(f"El modo de la variante '{name}' no es válido.")
        missing = [
            rule_name
            for rule_name in (variant.enter_rule, variant.exit_rule)
            if rule_name not in program.rules
        ]
        if missing:
            raise MIRInputError(
                f"La variante '{name}' referencia Rules inexistentes: "
                + ", ".join(missing)
                + "."
            )

    if require_linker:
        linker = program.context.linker
        if linker is None:
            raise MIRInputError(
                "La compilación de un archivo MIR requiere un bloque @block linker."
            )
        if not linker.extension:
            raise MIRInputError("El target requiere una extensión MIR no vacía.")

    return config


def _split_lines(
    tokens: Iterable[lexer.TokenType],
) -> tuple[tuple[lexer.TokenType, ...], ...]:
    lines: list[tuple[lexer.TokenType, ...]] = []
    current: list[lexer.TokenType] = []
    for token in tokens:
        if token.token == lexer.Token.EOF:
            break
        if token.token == lexer.Token.NEWLINE:
            if current:
                lines.append(tuple(current))
                current = []
            continue
        current.append(token)
    if current:
        lines.append(tuple(current))
    return tuple(lines)


def _line_number(line: tuple[lexer.TokenType, ...]) -> int | None:
    return getattr(line[0], "line", None) if line else None


def _resolve_meta_path(requested: str, mir_path: str | Path | None) -> Path:
    path = Path(requested).expanduser()
    if path.is_absolute() or ".." in path.parts:
        raise MIRInputError(
            f"La ruta de metaprogramación debe ser relativa y permanecer junto al MIR: {requested!r}."
        )
    base = (
        Path(mir_path).expanduser().resolve(strict=False).parent
        if mir_path is not None
        else Path.cwd().resolve()
    )
    candidate = (base / path).resolve(strict=False)
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise MIRInputError(
            f"La ruta de metaprogramación intenta salir del directorio del MIR: {requested!r}."
        ) from exc
    return candidate


def _apply_meta_directive(
    directive: RIFMetaDirective,
    image: AssemblyImage,
    section: str,
    mir_path: str | Path | None,
) -> None:
    if directive.name != "RIF_STORE":
        raise MIRInputError(f"Directiva de metaprogramación no soportada: {directive.name}.")
    if directive.path is None or directive.label is None:
        raise MIRInputError("::RIF_STORE requiere una ruta y un label.")
    if directive.endianness not in {1, 2} or directive.bitorder not in {0, 1}:
        raise MIRInputError(
            "::RIF_STORE requiere ENDIANNESS 1/2 y BITORDER 0/1."
        )
    if Path(directive.path).suffix.casefold() != ".bin":
        raise MIRInputError("::RIF_STORE solo acepta archivos con extensión .bin.")
    storage_path = _resolve_meta_path(directive.path, mir_path)
    try:
        payload = load_storage_file(storage_path).payload(directive.label)
    except (FileNotFoundError, OSError, StorageError) as exc:
        location = f" en línea {directive.line}" if directive.line else ""
        raise MIRInputError(
            f"No se pudo cargar ::RIF_STORE{location}: {exc}"
        ) from exc
    emitter = image.emitter(section)
    if emitter.buffer.bit_length % 8:
        raise MIRInputError(
            "::RIF_STORE solo puede insertar raw en una posición alineada a bytes."
        )
    try:
        emitter.emit_bytes(payload)
    except (TypeError, ValueError) as exc:
        raise MIRInputError(
            f"No se pudo insertar el payload '{directive.label}' de ::RIF_STORE: {exc}"
        ) from exc


def _insert_from_meta(
    directive: RIFMetaDirective,
    image: AssemblyImage,
    mir_path: str | Path | None,
) -> InsertData:
    """Convert one assembler-side insertion into the shared binary artifact type."""

    if directive.operation not in {"BYTES", "BINARY", "FILE"}:
        raise MIRInputError("::RIF_INSERT requiere BYTES, BINARY o FILE.")
    if directive.operation == "FILE":
        value = directive.path
    else:
        value = directive.payload[0].value if directive.payload else None
    if not isinstance(value, str) or not value:
        raise MIRInputError(f"::RIF_INSERT {directive.operation} requiere un string no vacío.")
    section = directive.section or image.config.defaultsection
    if section not in image.sections:
        raise MIRInputError(f"La sección '{section}' de ::RIF_INSERT no existe en CONFIG.")
    return InsertData(
        section=section,
        kind=directive.operation.casefold(),
        value=value,
        source_path=str(mir_path) if mir_path is not None else None,
    )


def _load_pcpi_directive(
    directive: RIFMetaDirective,
    image: AssemblyImage,
    section: str,
    mir_path: str | Path | None,
) -> tuple[object, str, int]:
    if directive.path is None:
        raise MIRInputError("::RIF_PCPI SET requiere la ruta de un archivo .pcic.")
    if Path(directive.path).suffix.casefold() != ".pcic":
        raise MIRInputError("::RIF_PCPI SET solo acepta archivos con extensión .pcic.")
    pcpi_path = _resolve_meta_path(directive.path, mir_path)
    try:
        pcpi = load_pcpi_file(pcpi_path)
    except (FileNotFoundError, OSError, PCPIError) as exc:
        location = f" en línea {directive.line}" if directive.line else ""
        raise MIRInputError(f"No se pudo cargar ::RIF_PCPI SET{location}: {exc}") from exc
    emitter = image.emitter(section)
    if emitter.buffer.bit_length % 8:
        raise MIRInputError("::RIF_PCPI SET solo puede comenzar alineado a bytes.")
    offset = emitter.buffer.byte_length
    try:
        emitter.emit_bytes(pcpi.to_bytes())
    except (TypeError, ValueError) as exc:
        raise MIRInputError(f"No se pudo insertar ::RIF_PCPI SET: {exc}") from exc
    return pcpi, section, offset


def _pcpi_query_address(
    directive: RIFMetaDirective,
    pcpi: object,
    set_section: str,
    set_offset: int,
    image: AssemblyImage,
) -> tuple[int, str]:
    if directive.index is None:
        raise MIRInputError("::RIF_PCPI PIT requiere un índice.")
    pits = getattr(pcpi, "pits", ())
    try:
        pit = pits[directive.index]
    except IndexError as exc:
        raise MIRInputError(
            f"No existe el PIT {directive.index} en la PCP-I seleccionada."
        ) from exc
    section = directive.section or set_section
    if section not in image.sections:
        raise MIRInputError(f"La sección PCP-I '{section}' no existe en CONFIG.")
    image.layout()
    address = (
        image.section_offset(section)
        + set_offset
        + PCPI_HEADER_SIZE
        + len(getattr(pcpi, "padding"))
        + pit.address
    )
    return address, section


def _resolve_rule_name(
    program: CompiledRuleSet,
    line: tuple[lexer.TokenType, ...],
    *,
    line_number: int | None,
) -> str:
    if not line:
        raise MIRInputError("No se puede resolver una línea MIR vacía.")
    value = line[0].value
    if not isinstance(value, str) or not value:
        location = f" en la línea {line_number}" if line_number else ""
        raise MIRInputError(
            f"La primera posición de una línea MIR debe identificar una Rule{location}."
        )
    if value in program.rules:
        return value
    config = program.context.config
    if config is not None and not config.casesensitive:
        folded = value.casefold()
        matches = [name for name in program.rules if name.casefold() == folded]
        if len(matches) == 1:
            return matches[0]
    location = f" en la línea {line_number}" if line_number else ""
    raise MIRInputError(f"No existe una Rule llamada '{value}'{location}.")


def _compile_mir_tokens(
    target: PreparedTarget | CompiledRuleSet | str | Path,
    tokens: Iterable[lexer.TokenType],
    *,
    section: str | None = None,
    rule_name: str | None = None,
    mir_path: str | Path | None = None,
) -> MIRCompilation:
    """Compile already-tokenized MIR without lexing or parsing it again.

    With no ``rule_name``, each line is dispatched by its first token value.
    Supplying ``rule_name`` treats the complete token stream as one Rule input.
    """

    prepared = _prepare_target(target)
    program = prepared.program
    config = validate_target(program)
    selected_section = section or config.entrysection
    if selected_section not in config.sections:
        raise MIRInputError(f"La sección MIR '{selected_section}' no existe en @block config.")

    image = AssemblyImage(config)
    machine = RIFMachine(
        program,
        emitter=image.emitter(selected_section),
        section_name=selected_section,
        image=image,
    )
    collected: list[lexer.TokenType] = []
    for index, token in enumerate(tokens):
        if index >= MAX_MIR_TOKENS:
            raise MIRInputError(
                f"El MIR excede el límite de {MAX_MIR_TOKENS} tokens."
            )
        collected.append(token)
    token_stream = tuple(collected)
    lines: tuple[MIRLine, ...] = preprocess_mir_lines(_split_lines(token_stream))
    pcpi: object | None = None
    pcpi_set_section: str | None = None
    pcpi_set_offset = 0
    pcpi_queries: list[RIFMetaDirective] = []
    dynamic_patches: list[PatchData] = []

    def handle_directive(directive: RIFMetaDirective) -> None:
        nonlocal pcpi, pcpi_set_section, pcpi_set_offset
        if directive.name == "RIF_STORE":
            _apply_meta_directive(
                directive,
                image,
                machine.section_name or selected_section,
                mir_path,
            )
            return
        if directive.name == "RIF_SECTION":
            if directive.section is None:
                raise MIRInputError("::RIF_SECTION requiere el nombre de una sección.")
            try:
                machine.select_section(directive.section)
            except RIFRuntimeError as exc:
                raise MIRInputError(str(exc)) from exc
            return
        if directive.name == "RIF_INSERT":
            try:
                insert = _insert_from_meta(directive, image, mir_path)
                apply_insert_directives(image, (insert,), assets=prepared.assets)
            except (ArtifactError, FileNotFoundError, OSError, ValueError) as exc:
                location = f" en línea {directive.line}" if directive.line else ""
                raise MIRInputError(f"No se pudo ejecutar ::RIF_INSERT{location}: {exc}") from exc
            return
        if directive.name == "RIF_PATCH":
            try:
                dynamic_patches.append(parse_patch_tokens(directive.payload, str(mir_path) if mir_path else None))
            except (RuntimeError, ValueError) as exc:
                location = f" en línea {directive.line}" if directive.line else ""
                raise MIRInputError(f"No se pudo leer ::RIF_PATCH{location}: {exc}") from exc
            return
        if directive.name in {"RIF_BUFFER", "RIF_REQSTS"}:
            return
        if directive.name != "RIF_PCPI":
            raise MIRInputError(f"Directiva de metaprogramación no soportada: {directive.name}.")
        if directive.operation == "SET":
            if pcpi is not None:
                raise MIRInputError("::RIF_PCPI SET solo puede aparecer una vez.")
            pcpi, pcpi_set_section, pcpi_set_offset = _load_pcpi_directive(
                directive, image, selected_section, mir_path
            )
            return
        if directive.operation == "PIT":
            if pcpi is None:
                raise MIRInputError("::RIF_PCPI PIT requiere un SET previo.")
            pcpi_queries.append(directive)
            return
        raise MIRInputError("::RIF_PCPI requiere SET o PIT.")

    buffer_result = execute_preprocessor_buffer(
        line for line in lines if isinstance(line, RIFMetaDirective)
    )

    if rule_name is not None:
        lines = ((
            tuple(
                token for line in lines if isinstance(line, tuple) for token in line
                if token.token != lexer.Token.EOF
            ),
        ))
        resolved_names = (rule_name,)
    else:
        resolved_names = tuple(
            _resolve_rule_name(program, line, line_number=_line_number(line))
            for line in lines
            if isinstance(line, tuple)
        )

    executions: list[ExecutionResult] = []
    resolved_index = 0
    for line in lines:
        if isinstance(line, RIFMetaDirective):
            handle_directive(line)
            continue
        name = resolved_names[resolved_index]
        resolved_index += 1
        result = machine.execute_line(name, line)
        if result.position != len(line):
            line_number = _line_number(line)
            location = f" en la línea {line_number}" if line_number else ""
            raise MIRInputError(
                f"La Rule '{name}' dejó {len(line) - result.position} token(s) sin consumir{location}."
            )
        executions.append(result)

    if machine.fixups:
        image.layout()
        machine.finalize_fixups(
            virtual_bases={
                name: image.section_virtual_base(name)
                for name in image.sections
            }
        )
        image.invalidate_layout()

    apply_patch_directives(
        image,
        machine,
        tuple(dynamic_patches),
    )

    pit_addresses: list[PCPIPitAddress] = []
    if pcpi_queries:
        if pcpi is None or pcpi_set_section is None:
            raise MIRInputError("::RIF_PCPI PIT requiere un SET previo.")
        for directive in pcpi_queries:
            address, address_section = _pcpi_query_address(
                directive,
                pcpi,
                pcpi_set_section,
                pcpi_set_offset,
                image,
            )
            pit_addresses.append(
                PCPIPitAddress(directive.index or 0, address, address_section)
            )

    return MIRCompilation(
        program=program,
        image=image,
        executions=tuple(executions),
        section=selected_section,
        binary=image.file_bytes(),
        context=machine,
        buffer=buffer_result,
        target_path=prepared.target_path,
        mir_path=Path(mir_path).expanduser().resolve() if mir_path else None,
        pcpi_pit_addresses=tuple(pit_addresses),
    )


def _write_output_map_atomic(
    output: str | Path,
    result: MIRCompilation,
    *,
    protected: tuple[Path, ...] = (),
) -> Path:
    protected = protected + tuple(
        path
        for path in (result.target_path, result.mir_path)
        if path is not None
    )
    return _write_binary_atomic(
        output,
        build_output_map(result).json_bytes(),
        protected=protected,
    )


def compile_mir_tokens(
    target: PreparedTarget | CompiledRuleSet | str | Path,
    tokens: Iterable[lexer.TokenType],
    *,
    section: str | None = None,
    rule_name: str | None = None,
    mir_path: str | Path | None = None,
    map_output: str | Path | None = None,
    diagnostics: DiagnosticBag | None = None,
) -> MIRCompilation:
    """Compile MIR and expose the same structured diagnostics on failure/success."""

    bag = diagnostics if diagnostics is not None else DiagnosticBag()
    try:
        result = _compile_mir_tokens(
            target,
            tokens,
            section=section,
            rule_name=rule_name,
            mir_path=mir_path,
        )
    except Exception as exc:
        bag.add_exception(exc, path=str(mir_path) if mir_path is not None else None)
        raise
    result.diagnostics = bag.items
    if map_output is not None:
        _write_output_map_atomic(map_output, result)
    return result


def compile_mir_source(
    target: PreparedTarget | CompiledRuleSet | str | Path,
    source: str,
    *,
    name: str = "<memory>",
    section: str | None = None,
    rule_name: str | None = None,
    mir_path: str | Path | None = None,
    map_output: str | Path | None = None,
    diagnostics: DiagnosticBag | None = None,
) -> MIRCompilation:
    """Compile MIR text through the shared direct token execution path."""

    effective_mir_path = mir_path
    if effective_mir_path is None and name and not name.startswith("<"):
        effective_mir_path = name
    return compile_mir_tokens(
        target,
        tokenize_mir(source, name),
        section=section,
        rule_name=rule_name,
        mir_path=effective_mir_path,
        map_output=map_output,
        diagnostics=diagnostics,
    )


def _compile_mir_file(
    target: PreparedTarget | CompiledRuleSet | str | Path,
    mir_path: str | Path,
    *,
    output: str | Path | None = None,
    map_output: str | Path | None = None,
    section: str | None = None,
    backend: str = "aot",
) -> MIRCompilation:
    """Compile one MIR file after validating the target's linker extension."""

    input_path = Path(mir_path).expanduser().resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"Archivo MIR no encontrado: {input_path}")
    if input_path.stat().st_size > resolve_limits().cap(MAX_MIR_SOURCE_BYTES):
        raise MIRInputError("El archivo MIR excede el límite de 64 MiB.")
    prepared = _prepare_target(target, backend=backend)
    _config = validate_target(prepared.program, require_linker=True)
    assert prepared.program.context.linker is not None
    linker = prepared.program.context.linker
    expected = linker.extension
    if not expected.startswith("."):
        expected = "." + expected
    actual = input_path.suffix
    matches = actual == expected if _config.casesensitive else actual.casefold() == expected.casefold()
    if not matches:
        raise MIRInputError(
            f"El MIR debe usar la extensión '{linker.extension}', no '{actual}'."
        )
    result = compile_mir_source(
        prepared,
        input_path.read_text(encoding="utf-8"),
        name=str(input_path),
        section=section,
        mir_path=input_path,
    )
    result.mir_path = input_path
    if output is not None:
        protected = (input_path,) + (
            (prepared.target_path,) if prepared.target_path is not None else ()
        )
        _write_binary_atomic(output, result.binary, protected=protected)
    if map_output is not None:
        map_protected = (
            (Path(output).expanduser().resolve(),)
            if output is not None
            else ()
        )
        _write_output_map_atomic(
            map_output,
            result,
            protected=map_protected,
        )
    return result


def compile_mir_file(
    target: PreparedTarget | CompiledRuleSet | str | Path,
    mir_path: str | Path,
    *,
    output: str | Path | None = None,
    map_output: str | Path | None = None,
    section: str | None = None,
    backend: str = "aot",
    diagnostics: DiagnosticBag | None = None,
) -> MIRCompilation:
    """Compile a MIR file and collect diagnostics from every external phase."""

    bag = diagnostics if diagnostics is not None else DiagnosticBag()
    try:
        result = _compile_mir_file(
            target,
            mir_path,
            output=output,
            map_output=map_output,
            section=section,
            backend=backend,
        )
    except Exception as exc:
        bag.add_exception(exc, path=str(mir_path))
        raise
    result.diagnostics = bag.items
    return result


def compile_mir(
    target: PreparedTarget | CompiledRuleSet | str | Path,
    mir: str | Iterable[lexer.TokenType],
    *,
    name: str = "<memory>",
    section: str | None = None,
    rule_name: str | None = None,
    map_output: str | Path | None = None,
    diagnostics: DiagnosticBag | None = None,
) -> MIRCompilation:
    """Direct convenience entry point for MIR text or pre-tokenized MIR."""

    if isinstance(mir, str):
        return compile_mir_source(
            target,
            mir,
            name=name,
            section=section,
            rule_name=rule_name,
            map_output=map_output,
            diagnostics=diagnostics,
        )
    return compile_mir_tokens(
        target,
        mir,
        section=section,
        rule_name=rule_name,
        map_output=map_output,
        diagnostics=diagnostics,
    )


__all__ = [
    "MIRInputError",
    "PreparedTarget",
    "MIRCompilation",
    "prepare_target",
    "tokenize_mir",
    "compile_mir",
    "compile_mir_tokens",
    "compile_mir_source",
    "compile_mir_file",
    "validate_target",
]
