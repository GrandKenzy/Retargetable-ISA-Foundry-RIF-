"""Read-only, bounded inspection of RIF ``.pack`` artifacts.

The inspector deliberately does not compile sources, activate frontend globals,
execute Rules, load plugins, or extract package members.  It first delegates
ZIP/hash validation to :mod:`pack`, then reads the optional SQLite compilation
database in an isolated in-memory connection.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from MIR.compiled import SCHEMA_VERSION, context_from_dict, program_from_dict
from MIR.instructions import CompiledRuleSet, Operand
from MIR.preprocessor import RIF_META_OPERATIONS
from rif_core.pack import (
    MAX_COMPILED_SIZE,
    PACK_FORMAT,
    PACK_FORMAT_VERSION,
    PackManifest,
    PackReader,
    read_pack,
)
from rif_core.limits import resolve_limits


MAX_REPORT_ITEMS = 1_000
MAX_REPORT_ITEMS_HARD = 10_000
MAX_INSPECT_JSON_BYTES = 64 << 20
MAX_INSPECT_TABLE_COLUMNS = 4_096
MAX_INSPECT_TABLE_ROWS = 1_000_000
MAX_INSPECT_JSON_DEPTH = 64
MAX_INSPECT_STRING = 1 << 20


class PackInspectionError(ValueError):
    """The package is valid enough to open but not safe to inspect."""


def _bounded_limit(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError("max_items debe ser un entero.")
    if value < 1 or value > MAX_REPORT_ITEMS_HARD:
        raise ValueError(
            f"max_items debe estar entre 1 y {MAX_REPORT_ITEMS_HARD}."
        )
    return value


def _load_json(text: str, label: str) -> Any:
    if not isinstance(text, str):
        raise PackInspectionError(f"El artefacto {label} no contiene texto JSON.")
    if len(text.encode("utf-8")) > resolve_limits().cap(MAX_INSPECT_JSON_BYTES):
        raise PackInspectionError(f"El artefacto JSON {label} excede el límite de inspección.")
    try:
        return json.loads(text)
    except (RecursionError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PackInspectionError(f"El artefacto {label} no contiene JSON válido.") from exc


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PackInspectionError(f"El artefacto {label} debe ser un objeto JSON.")
    return value


def _bounded_text(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise PackInspectionError(f"{label} debe ser texto.")
    if len(value) > MAX_INSPECT_STRING:
        raise PackInspectionError(f"{label} excede el límite de inspección.")
    return value


def _bounded_json_value(value: Any, *, depth: int = 0) -> Any:
    """Convert decoded target values into JSON-safe, bounded report data."""

    if depth > MAX_INSPECT_JSON_DEPTH:
        return "<depth-limit>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= MAX_INSPECT_STRING else "<string-limit>"
    if isinstance(value, (tuple, list)):
        items = list(value[:MAX_REPORT_ITEMS])
        result = [
            _bounded_json_value(item, depth=depth + 1)
            for item in items
        ]
        if len(value) > MAX_REPORT_ITEMS:
            result.append("<items-truncated>")
        return result
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= MAX_REPORT_ITEMS:
                result["<items-truncated>"] = True
                break
            result[str(key)] = _bounded_json_value(item, depth=depth + 1)
        return result
    if isinstance(value, Operand):
        return {
            "type": "Operand",
            "kind": _safe_text(value.kind),
            "value": _bounded_json_value(value.value, depth=depth + 1),
            "raw": _safe_optional_path(value.raw),
            "width": value.width,
            "resolved": _bounded_json_value(value.resolved, depth=depth + 1),
        }
    if hasattr(value, "name") and hasattr(value, "value"):
        return {
            "type": type(value).__name__,
            "name": _bounded_json_value(getattr(value, "name"), depth=depth + 1),
            "value": _bounded_json_value(getattr(value, "value"), depth=depth + 1),
        }
    if hasattr(value, "name"):
        return {
            "type": type(value).__name__,
            "name": _bounded_json_value(getattr(value, "name"), depth=depth + 1),
        }
    return f"<{type(value).__name__}>"


def _safe_optional_path(
    value: str | None,
    *,
    show_origins: bool = False,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return f"<{type(value).__name__}>"
    if len(value) > MAX_INSPECT_STRING:
        return "<string-limit>"
    if show_origins:
        return value
    if value.startswith("pack://") and "::" in value:
        return "pack://...::" + value.rsplit("::", 1)[1]
    if Path(value).is_absolute() or (len(value) >= 2 and value[1] == ":"):
        return "<origin-hidden>"
    return value


def _safe_text(value: Any) -> str:
    if not isinstance(value, str):
        return f"<{type(value).__name__}>"
    return value if len(value) <= MAX_INSPECT_STRING else "<string-limit>"


def _validate_sqlite_shape(connection: sqlite3.Connection) -> None:
    """Validate the fixed compiled schema without executing package SQL."""

    try:
        connection.execute("PRAGMA query_only = ON")
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity != ("ok",):
            raise PackInspectionError("La base SQLite compilada no pasó integrity_check.")

        objects = {
            (str(name), str(kind))
            for name, kind in connection.execute(
                "SELECT name, type FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%'"
            )
        }
        required = {
            ("meta", "table"),
            ("artifacts", "table"),
            ("table_defs", "table"),
            ("table_columns", "table"),
            ("table_rows", "table"),
        }
        if not required.issubset(objects):
            raise PackInspectionError("La base compilada no contiene el esquema RIF completo.")
        if any(kind not in {"table", "index"} for _, kind in objects):
            raise PackInspectionError("La base compilada contiene objetos SQLite no permitidos.")

        schema = connection.execute(
            "SELECT value FROM meta WHERE key = 'schema'"
        ).fetchone()
        if schema is None or schema[0] != str(SCHEMA_VERSION):
            raise PackInspectionError("Versión de esquema SQLite compilado no compatible.")
        user_version = connection.execute("PRAGMA user_version").fetchone()
        if user_version != (1,):
            raise PackInspectionError("Versión SQLite interna del paquete no compatible.")

        for table_name, headers_json in connection.execute(
            "SELECT name, headers_json FROM table_defs ORDER BY name"
        ):
            table_name = _bounded_text(table_name, "nombre de tabla")
            headers = _load_json(headers_json, f"headers de tabla {table_name!r}")
            if (
                not isinstance(headers, list)
                or len(headers) > MAX_INSPECT_TABLE_COLUMNS
                or any(not isinstance(header, str) or not header for header in headers)
                or len(set(headers)) != len(headers)
            ):
                raise PackInspectionError(
                    f"La tabla {table_name!r} tiene columnas inválidas."
                )

            columns = connection.execute(
                "SELECT column_name, column_index FROM table_columns "
                "WHERE table_name = ? ORDER BY column_index",
                (table_name,),
            ).fetchall()
            expected_columns = list(zip(headers, range(len(headers))))
            if columns != expected_columns:
                raise PackInspectionError(
                    f"El índice de columnas de la tabla {table_name!r} es inconsistente."
                )

            row_count = connection.execute(
                "SELECT COUNT(*) FROM table_rows WHERE table_name = ?",
                (table_name,),
            ).fetchone()[0]
            if row_count > MAX_INSPECT_TABLE_ROWS:
                raise PackInspectionError(
                    f"La tabla {table_name!r} excede el límite de filas inspeccionable."
                )
            row_indices = connection.execute(
                "SELECT row_index FROM table_rows WHERE table_name = ? "
                "ORDER BY row_index",
                (table_name,),
            )
            for expected, (row_index,) in enumerate(row_indices):
                if row_index != expected:
                    raise PackInspectionError(
                        f"Los índices de filas de la tabla {table_name!r} no son contiguos."
                    )

        dangling_columns = connection.execute(
            "SELECT DISTINCT table_name FROM table_columns "
            "WHERE table_name NOT IN (SELECT name FROM table_defs)"
        ).fetchone()
        if dangling_columns is not None:
            raise PackInspectionError("La base compilada contiene columnas sin tabla.")
        dangling_rows = connection.execute(
            "SELECT DISTINCT table_name FROM table_rows "
            "WHERE table_name NOT IN (SELECT name FROM table_defs)"
        ).fetchone()
        if dangling_rows is not None:
            raise PackInspectionError("La base compilada contiene filas sin tabla.")
    except sqlite3.DatabaseError as exc:
        raise PackInspectionError("No se pudo validar el esquema SQLite compilado.") from exc


def _artifact_text(connection: sqlite3.Connection, name: str) -> str:
    row = connection.execute(
        "SELECT value FROM artifacts WHERE name = ?",
        (name,),
    ).fetchone()
    if row is None:
        raise PackInspectionError(f"Falta el artefacto compilado {name!r}.")
    if not isinstance(row[0], str):
        raise PackInspectionError(f"El artefacto {name!r} no contiene texto JSON.")
    if len(row[0].encode("utf-8")) > resolve_limits().cap(MAX_INSPECT_JSON_BYTES):
        raise PackInspectionError(
            f"El artefacto JSON {name!r} excede el límite de inspección."
        )
    return row[0]


def _rule_report(
    program: CompiledRuleSet,
    *,
    verbose: bool,
    limit: int,
    show_origins: bool,
) -> dict[str, Any]:
    names = sorted(program.rules)
    items: list[dict[str, Any]] = []
    for name in names[:limit]:
        rule = program.rules[name]
        opcodes: dict[str, int] = {}
        for instruction in rule.instructions:
            opcode = _safe_text(instruction.opcode)
            opcodes[opcode] = opcodes.get(opcode, 0) + 1
        item: dict[str, Any] = {
            "name": _safe_text(rule.name),
            "source_path": _safe_optional_path(
                rule.source_path,
                show_origins=show_origins,
            ),
            "instruction_count": len(rule.instructions),
            "opcodes": dict(sorted(opcodes.items())),
        }
        if verbose:
            item["instructions"] = [
                {
                    "opcode": _safe_text(instruction.opcode),
                    "operands": [
                        _bounded_json_value(operand)
                        for operand in instruction.operands
                    ],
                    "span": {
                        "path": _safe_optional_path(
                            instruction.span.path,
                            show_origins=show_origins,
                        ),
                        "line": instruction.span.line,
                        "column": instruction.span.column,
                    },
                }
                for instruction in rule.instructions[:limit]
            ]
            if len(rule.instructions) > limit:
                item["instructions_truncated"] = True
        items.append(item)
    return {
        "count": len(names),
        "items": items,
        "truncated": len(names) > limit,
    }


def _table_report(
    connection: sqlite3.Connection,
    context: Any,
    *,
    verbose: bool,
    limit: int,
) -> dict[str, Any]:
    names = sorted(context.tables)
    items: list[dict[str, Any]] = []
    for name in names[:limit]:
        table = context.tables[name]
        item: dict[str, Any] = {
            "name": _safe_text(table.name),
            "columns": [_safe_text(header) for header in table.headers],
            "row_count": len(table.matrix),
            "unique_columns": [
                _safe_text(column) for column in sorted(table.unique_columns)
            ],
        }
        if verbose:
            item["rows"] = [
                [_bounded_json_value(value) for value in row]
                for row in table.matrix[:limit]
            ]
            if len(table.matrix) > limit:
                item["rows_truncated"] = True
        items.append(item)
    return {
        "count": len(names),
        "items": items,
        "truncated": len(names) > limit,
    }


def _config_report(config: Any) -> dict[str, Any] | None:
    if config is None:
        return None
    return {
        "sections": [_safe_text(item) for item in config.sections],
        "entry_section": _safe_text(config.entrysection),
        "entry_label": _safe_text(config.entrylabel),
        "default_section": _safe_text(config.defaultsection),
        "data_section": _safe_text(config.datasection),
        "word_size": config.wordsize,
        "address_size": config.addresssize,
        "byte_order": _safe_text(config.endianness),
        "bit_order": _safe_text(config.bitorder),
        "section_flags": {
            _safe_text(key): _safe_text(value)
            for key, value in sorted(config.sectionflags.items())
        },
        "section_alignment": {
            _safe_text(key): value
            for key, value in sorted(config.sectionalign.items())
        },
        "section_virtual_addresses": {
            _safe_text(key): value
            for key, value in sorted(config.sectionvaddr.items())
        },
        "strict": config.strict,
        "allow_empty_sections": config.allowemptysections,
        "case_sensitive": config.casesensitive,
        "undefined_symbols": _safe_text(config.undefinedsymbols),
        "duplicate_symbols": _safe_text(config.duplicatesymbols),
        "symbol_prefix": _safe_text(config.symbolprefix),
        "local_prefix": _safe_text(config.localprefix),
    }


def _linker_report(linker: Any) -> dict[str, Any] | None:
    if linker is None:
        return None
    if linker.search_path is not False and not isinstance(linker.search_path, (tuple, list)):
        raise PackInspectionError("El linker contiene un search_path inválido.")
    if not isinstance(linker.extension, str):
        raise PackInspectionError("El linker contiene una extensión inválida.")
    if linker.search_path is not False and any(
        not isinstance(item, str) for item in linker.search_path
    ):
        raise PackInspectionError("El linker contiene una ruta inválida.")
    if linker.search_path is False:
        search_path: list[str] | bool = False
        search_path_truncated = False
    else:
        search_path = [_safe_text(item) for item in linker.search_path[:MAX_REPORT_ITEMS]]
        search_path_truncated = len(linker.search_path) > MAX_REPORT_ITEMS
    return {
        "extension": _safe_text(linker.extension),
        "search_path": search_path,
        "search_path_truncated": search_path_truncated,
    }


def _variants_report(
    context: Any,
    limit: int,
    *,
    show_origins: bool,
) -> dict[str, Any]:
    items = [
        {
            "name": _safe_text(value.name),
            "mode": _safe_text(value.mode),
            "enter_rule": _safe_text(value.enter_rule),
            "exit_rule": _safe_text(value.exit_rule),
            "path": _safe_optional_path(value.path, show_origins=show_origins),
        }
        for _, value in sorted(context.asm_variants.items())
    ]
    return {
        "count": len(items),
        "items": items[:limit],
        "truncated": len(items) > limit,
    }


def _supports_report(
    context: Any,
    limit: int,
    *,
    show_origins: bool,
) -> dict[str, Any]:
    items = [
        {
            "name": _safe_text(value.name),
            "path": _safe_optional_path(value.path, show_origins=show_origins),
        }
        for _, value in sorted(context.supports.items())
    ]
    return {
        "count": len(items),
        "items": items[:limit],
        "truncated": len(items) > limit,
    }


def _blocks_report(
    context: Any,
    limit: int,
    *,
    show_origins: bool,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for name, blocks in sorted(context.blocks.items()):
        items.append(
            {
                "name": _safe_text(name),
                "count": len(blocks),
                "entries": sum(len(block.entries) for block in blocks),
                "sources": sorted(
                    {
                        _safe_optional_path(
                            block.source_path,
                            show_origins=show_origins,
                        )
                        for block in blocks
                        if block.source_path is not None
                    }
                ),
            }
        )
    return {
        "count": len(items),
        "items": items[:limit],
        "truncated": len(items) > limit,
    }


def _inspect_compiled(
    data: bytes,
    manifest: PackManifest,
    *,
    verbose: bool,
    limit: int,
    show_origins: bool,
) -> dict[str, Any]:
    if len(data) > resolve_limits().cap(MAX_COMPILED_SIZE):
        raise PackInspectionError("La base compilada excede el límite de inspección.")
    connection = sqlite3.connect(":memory:")
    try:
        try:
            connection.deserialize(data)
        except sqlite3.DatabaseError as exc:
            raise PackInspectionError("La base compilada no es una imagen SQLite válida.") from exc
        _validate_sqlite_shape(connection)
        fingerprint = connection.execute(
            "SELECT value FROM meta WHERE key = 'source_fingerprint'"
        ).fetchone()
        if fingerprint is None or fingerprint[0] != manifest.content_sha256:
            raise PackInspectionError(
                "La huella de la base compilada no coincide con el manifiesto."
            )
        contract_row = connection.execute(
            "SELECT value FROM meta WHERE key = 'contract'"
        ).fetchone()
        contract_fingerprint = connection.execute(
            "SELECT value FROM meta WHERE key = 'contract_fingerprint'"
        ).fetchone()
        if contract_row is None or contract_fingerprint is None:
            raise PackInspectionError("La base compilada no declara su contrato.")
        stored_contract = _require_object(
            _load_json(contract_row[0], "contract"),
            "contract",
        )
        if stored_contract != manifest.contract.as_dict():
            raise PackInspectionError(
                "El contrato SQLite compilado no coincide con el manifiesto."
            )
        if contract_fingerprint[0] != manifest.contract.fingerprint():
            raise PackInspectionError("La huella del contrato compilado es inválida.")

        raw_program = _require_object(
            _load_json(_artifact_text(connection, "program"), "program"),
            "program",
        )
        raw_context = _require_object(
            _load_json(_artifact_text(connection, "context"), "context"),
            "context",
        )
        try:
            context = context_from_dict(connection, raw_context)
            program = program_from_dict(raw_program)
        except (
            KeyError,
            RecursionError,
            TypeError,
            ValueError,
            sqlite3.DatabaseError,
        ) as exc:
            raise PackInspectionError(
                "Los artefactos serializados del target no son consistentes."
            ) from exc
        if program.contract.as_dict() != stored_contract:
            raise PackInspectionError(
                "El contrato del programa SQLite no coincide con su metadata."
            )

        linker = _linker_report(context.linker)
        return {
            "present": True,
            "schema_version": SCHEMA_VERSION,
            "source_fingerprint": fingerprint[0],
            "contract": stored_contract,
            "contract_fingerprint": contract_fingerprint[0],
            "verified": True,
            "config": _config_report(context.config),
            "linker": linker,
            "defines": [_safe_text(item) for item in sorted(context.defines)[:limit]],
            "defines_truncated": len(context.defines) > limit,
            "stack_size": context.stack_size,
            "rules": _rule_report(
                program,
                verbose=verbose,
                limit=limit,
                show_origins=show_origins,
            ),
            "tables": _table_report(
                connection, context, verbose=verbose, limit=limit
            ),
            "variants": _variants_report(
                context,
                limit,
                show_origins=show_origins,
            ),
            "supports": _supports_report(
                context,
                limit,
                show_origins=show_origins,
            ),
            "blocks": _blocks_report(
                context,
                limit,
                show_origins=show_origins,
            ),
            "loaded_sources": (
                {
                    _safe_optional_path(key, show_origins=True): _safe_text(value)
                    for key, value in sorted(context.loaded_sources.items())[:limit]
                }
                if show_origins
                else {"count": len(context.loaded_sources), "hidden": True}
            ),
            "loaded_sources_truncated": (
                len(context.loaded_sources) > limit if show_origins else False
            ),
            "mir": {
                "file_extension": (
                    _safe_text(context.linker.extension)
                    if context.linker
                    else None
                ),
                "rule_names": [
                    _safe_text(name) for name in sorted(program.rules)[:limit]
                ],
                "rule_names_truncated": len(program.rules) > limit,
                "preprocessor_directives": {
                    name: list(operations)
                    for name, operations in sorted(RIF_META_OPERATIONS.items())
                },
            },
        }
    finally:
        connection.close()


def inspect_pack(
    path: str | Path,
    *,
    verbose: bool = False,
    max_items: int = MAX_REPORT_ITEMS,
    show_origins: bool = False,
) -> dict[str, Any]:
    """Verify and inspect one package without executing target code.

    ``max_items`` bounds every potentially repeated report section.  Package
    verification is always enabled; there is intentionally no bypass flag in
    this API or the CLI.
    """

    limit = _bounded_limit(max_items)
    try:
        manifest = read_pack(path, verify=True)
    except Exception as exc:
        # BadZipFile is not an OSError on all supported Python versions. Keep
        # malformed archives inside the inspector's stable error contract.
        if isinstance(exc, (KeyboardInterrupt, SystemExit, MemoryError)):
            raise
        if isinstance(exc, PackInspectionError):
            raise
        raise PackInspectionError(f"No se pudo verificar el paquete: {exc}") from exc
    package_path = Path(path).expanduser().resolve()
    source_size = sum(entry.size for entry in manifest.files)
    asset_size = sum(entry.size for entry in manifest.assets)
    library_size = sum(entry.size for entry in manifest.libraries)
    report: dict[str, Any] = {
        "tool": {
            "name": "rif-pack-inspector",
            "version": 1,
            "verified": True,
        },
        "package": {
            "path": str(package_path),
            "format": PACK_FORMAT,
            "format_version": PACK_FORMAT_VERSION,
            "name": manifest.name,
            "version": manifest.version,
            "entrypoint": manifest.entrypoint,
            "content_sha256": manifest.content_sha256,
            "contract": manifest.contract.as_dict(),
            "contract_fingerprint": manifest.contract.fingerprint(),
            "sources": {
                "count": len(manifest.files),
                "total_size": source_size,
                "entrypoint": manifest.entrypoint,
                "dependency_order": list(manifest.dependency_order)[:limit],
                "dependency_order_truncated": len(manifest.dependency_order) > limit,
            },
            "assets": {
                "count": len(manifest.assets),
                "total_size": asset_size,
                "items": [
                    {"path": entry.path, "size": entry.size, "sha256": entry.sha256}
                    for entry in manifest.assets[:limit]
                ],
                "truncated": len(manifest.assets) > limit,
            },
            "libraries": {
                "count": len(manifest.libraries),
                "total_size": library_size,
                "items": [
                    {"path": entry.path, "size": entry.size, "sha256": entry.sha256}
                    for entry in manifest.libraries[:limit]
                ],
                "truncated": len(manifest.libraries) > limit,
            },
            "origins": (
                dict(sorted(manifest.origins.items()))
                if show_origins
                else {"count": len(manifest.origins), "hidden": True}
            ),
        },
    }
    with PackReader(package_path, verify=True) as reader:
        compiled = reader.compiled_database()
        if compiled is None:
            report["compiled"] = {
                "present": False,
                "reason": "El paquete es source-only; no contiene SQLite precompilado.",
            }
        else:
            report["compiled"] = _inspect_compiled(
                compiled,
                manifest,
                verbose=verbose,
                limit=limit,
                show_origins=show_origins,
            )
    return report


def render_pack_inspection(
    report: dict[str, Any],
    *,
    json_output: bool = False,
) -> str:
    """Render an inspection report as stable JSON or bounded human text."""

    if json_output:
        return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    package = report["package"]
    compiled = report["compiled"]
    lines = [
        "RIF PACK INSPECT",
        f"status: {'OK' if report['tool']['verified'] else 'ERROR'}",
        f"path: {package['path']}",
        f"format: {package['format']} v{package['format_version']}",
        f"target: {package['name']} version={package['version']}",
        f"entrypoint: {package['entrypoint']}",
        f"fingerprint: {package['content_sha256']}",
        f"contract: {package['contract_fingerprint']}",
        f"sources: {package['sources']['count']} ({package['sources']['total_size']} bytes)",
        f"assets: {package['assets']['count']} ({package['assets']['total_size']} bytes)",
        f"libraries: {package['libraries']['count']} ({package['libraries']['total_size']} bytes)",
    ]
    if not compiled.get("present"):
        lines.append("compiled: no (source-only package)")
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            f"compiled: yes schema={compiled['schema_version']} verified={compiled['verified']}",
            f"rules: {compiled['rules']['count']}",
        ]
    )
    for rule in compiled["rules"]["items"]:
        opcodes = ", ".join(
            f"{opcode}={count}" for opcode, count in rule["opcodes"].items()
        )
        lines.append(
            f"  rule {rule['name']}: {rule['instruction_count']} instructions"
            + (f" [{opcodes}]" if opcodes else "")
        )
    if compiled["rules"]["truncated"]:
        lines.append("  ... rules truncated by max_items")

    lines.append(f"tables: {compiled['tables']['count']}")
    for table in compiled["tables"]["items"]:
        columns = ", ".join(table["columns"])
        lines.append(
            f"  table {table['name']}: {table['row_count']} rows"
            + (f" ({columns})" if columns else "")
        )
    if compiled["tables"]["truncated"]:
        lines.append("  ... tables truncated by max_items")

    config = compiled.get("config")
    if config is None:
        lines.append("config: none")
    else:
        lines.append(
            "config: "
            f"sections={','.join(config['sections'])} "
            f"entry={config['entry_section']} default={config['default_section']} "
            f"word_size={config['word_size']} address_size={config['address_size']}"
        )
    linker = compiled.get("linker")
    if linker is None:
        lines.append("linker: none")
    else:
        lines.append(
            f"linker: extension={linker['extension']!r} "
            f"search_path={linker['search_path']!r}"
        )
    lines.append(f"variants: {compiled['variants']['count']}")
    for variant in compiled["variants"]["items"]:
        lines.append(
            f"  variant {variant['name']}: mode={variant['mode']} "
            f"enter={variant['enter_rule']} exit={variant['exit_rule']}"
        )
    lines.append(
        "MIR: "
        f"extension={compiled['mir']['file_extension']!r} "
        "preprocessor="
        + ",".join(sorted(compiled["mir"]["preprocessor_directives"]))
    )
    return "\n".join(lines) + "\n"


__all__ = [
    "MAX_REPORT_ITEMS",
    "MAX_REPORT_ITEMS_HARD",
    "PackInspectionError",
    "inspect_pack",
    "render_pack_inspection",
]
