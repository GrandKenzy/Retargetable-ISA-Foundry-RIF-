"""Serialización segura del programa RIF compilado en SQLite."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from gram import lexer

from Frontend import globals
from rif_core.contract import (
    COMPILED_SCHEMA_VERSION,
    CompilationContract,
    ContractError,
    current_contract,
    require_compatible,
)

from .instructions import CompiledRule, CompiledRuleSet, Instruction, Operand, SourceSpan
from .semantic import RuleRef, TableLookupRef, TableRef, TokenRef


SCHEMA_VERSION = COMPILED_SCHEMA_VERSION


def _token_from_name(name: str) -> lexer.Token:
    token = lexer.Token.from_code(int(name)) if name.isdigit() else lexer.Token.from_string(name)
    if token is None:
        raise ValueError(f"Token serializado inválido: {name}")
    return token


def _encode(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, lexer.Token):
        return {"__type__": "token", "name": value.name}
    if isinstance(value, TokenRef):
        return {
            "__type__": "token_ref",
            "name": value.name,
            "token": value.token.name,
        }
    if isinstance(value, TableRef):
        return {
            "__type__": "table_ref",
            "table": value.table,
            "column": value.column,
            "index": value.index,
        }
    if isinstance(value, TableLookupRef):
        return {
            "__type__": "table_lookup_ref",
            "table": value.table,
            "selector": value.selector,
            "key": _encode(value.key),
            "column": value.column,
            "selector_index": value.selector_index,
            "index": value.index,
        }
    if isinstance(value, RuleRef):
        return {"__type__": "rule_ref", "name": value.name}
    if isinstance(value, globals.LinkerData):
        return {
            "__type__": "linker",
            "extension": value.extension,
            "search_path": value.search_path,
        }
    if isinstance(value, globals.SupportData):
        return {"__type__": "support", "name": value.name, "path": value.path}
    if isinstance(value, globals.AsmVariantData):
        return {
            "__type__": "asm_variant",
            "name": value.name,
            "mode": value.mode,
            "enter_rule": value.enter_rule,
            "exit_rule": value.exit_rule,
            "path": value.path,
        }
    if isinstance(value, globals.BlockValueData):
        return {
            "__type__": "block_value",
            "kind": value.kind,
            "value": _encode(value.value),
            "raw": value.raw,
        }
    if isinstance(value, globals.BlockEntryData):
        return {
            "__type__": "block_entry",
            "name": value.name,
            "values": _encode(value.values),
        }
    if isinstance(value, globals.BlockData):
        return {
            "__type__": "block",
            "name": value.name,
            "entries": _encode(value.entries),
            "source_path": value.source_path,
        }
    if isinstance(value, Operand):
        return {
            "__type__": "operand",
            "kind": value.kind,
            "value": _encode(value.value),
            "raw": value.raw,
            "width": value.width,
            "resolved": _encode(value.resolved),
        }
    if isinstance(value, tuple):
        return {"__type__": "tuple", "items": [_encode(item) for item in value]}
    if isinstance(value, list):
        return {"__type__": "list", "items": [_encode(item) for item in value]}
    if isinstance(value, dict):
        return {
            "__type__": "dict",
            "items": [[_encode(key), _encode(item)] for key, item in value.items()],
        }
    raise TypeError(f"Tipo no serializable en MIR: {type(value).__name__}")


def _decode(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if not isinstance(value, dict):
        raise ValueError("Valor serializado inválido.")
    kind = value.get("__type__")
    if kind == "token":
        return _token_from_name(str(value["name"]))
    if kind == "token_ref":
        return TokenRef(str(value["name"]), _token_from_name(str(value["token"])))
    if kind == "table_ref":
        return TableRef(str(value["table"]), str(value["column"]), int(value["index"]))
    if kind == "table_lookup_ref":
        return TableLookupRef(
            str(value["table"]),
            str(value["selector"]),
            _decode(value["key"]),
            str(value["column"]),
            int(value["selector_index"]),
            int(value["index"]),
        )
    if kind == "rule_ref":
        return RuleRef(str(value["name"]))
    if kind == "linker":
        return globals.LinkerData(
            extension=str(value["extension"]),
            search_path=value["search_path"],
        )
    if kind == "support":
        return globals.SupportData(name=str(value["name"]), path=str(value["path"]))
    if kind == "asm_variant":
        return globals.AsmVariantData(
            name=str(value["name"]),
            mode=str(value["mode"]),
            enter_rule=str(value["enter_rule"]),
            exit_rule=str(value["exit_rule"]),
            path=str(value["path"]),
        )
    if kind == "block_value":
        return globals.BlockValueData(
            kind=str(value["kind"]),
            value=_decode(value.get("value")),
            raw=value.get("raw"),
        )
    if kind == "block_entry":
        return globals.BlockEntryData(
            name=str(value["name"]),
            values=tuple(_decode(value.get("values"))),
        )
    if kind == "block":
        return globals.BlockData(
            name=str(value["name"]),
            entries=tuple(_decode(value.get("entries"))),
            source_path=value.get("source_path"),
        )
    if kind == "operand":
        return Operand(
            kind=str(value["kind"]),
            value=_decode(value.get("value")),
            raw=value.get("raw"),
            width=value.get("width"),
            resolved=_decode(value.get("resolved")),
        )
    if kind == "tuple":
        return tuple(_decode(item) for item in value["items"])
    if kind == "list":
        return [_decode(item) for item in value["items"]]
    if kind == "dict":
        return {_decode(key): _decode(item) for key, item in value["items"]}
    raise ValueError(f"Tipo serializado desconocido: {kind!r}")


def _json(value: Any) -> str:
    return json.dumps(_encode(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _unjson(value: str) -> Any:
    return _decode(json.loads(value))


def _portable_path(path: str | None, source_root: str | Path | None) -> str | None:
    if path is None or source_root is None:
        return path
    try:
        relative = Path(path).resolve().relative_to(Path(source_root).resolve())
    except (OSError, ValueError):
        return path
    return f"sources/{relative.as_posix()}"


def program_to_dict(
    program: CompiledRuleSet,
    source_root: str | Path | None = None,
) -> dict[str, Any]:
    return {
        "contract": program.contract.as_dict(),
        "rules": {
            name: {
                "name": rule.name,
                "source_path": _portable_path(rule.source_path, source_root),
                "instructions": [
                    {
                        "opcode": instruction.opcode,
                        "operands": [_encode(operand) for operand in instruction.operands],
                        "span": {
                            "path": _portable_path(instruction.span.path, source_root),
                            "line": instruction.span.line,
                            "column": instruction.span.column,
                        },
                    }
                    for instruction in rule.instructions
                ],
            }
            for name, rule in program.rules.items()
        },
    }


def program_from_dict(data: dict[str, Any]) -> CompiledRuleSet:
    rules: dict[str, CompiledRule] = {}
    for name, raw_rule in data.get("rules", {}).items():
        instructions = []
        for raw_instruction in raw_rule["instructions"]:
            raw_span = raw_instruction["span"]
            instructions.append(
                Instruction(
                    opcode=str(raw_instruction["opcode"]),
                    operands=tuple(_decode(item) for item in raw_instruction["operands"]),
                    span=SourceSpan(
                        raw_span.get("path"),
                        raw_span.get("line"),
                        raw_span.get("column"),
                    ),
                )
            )
        rules[str(name)] = CompiledRule(
            name=str(raw_rule.get("name", name)),
            instructions=tuple(instructions),
            source_path=raw_rule.get("source_path"),
        )
    contract = CompilationContract.from_dict(data.get("contract"))
    return CompiledRuleSet(rules, contract=contract)


def _config_to_dict(config: globals.ConfigData | None) -> dict[str, Any] | None:
    if config is None:
        return None
    return {
        "sectiondef": config.sectiondef,
        "sections": list(config.sections),
        "sectionend": config.sectionend,
        "entrysection": config.entrysection,
        "entrylabel": config.entrylabel,
        "comment": config.comment,
        "labelend": config.labelend,
        "datasection": config.datasection,
        "defaultsection": config.defaultsection,
        "sectionflags": config.sectionflags,
        "sectionalign": config.sectionalign,
        "wordsize": config.wordsize,
        "addresssize": config.addresssize,
        "endianness": config.endianness,
        "casesensitive": config.casesensitive,
        "symbolprefix": config.symbolprefix,
        "localprefix": config.localprefix,
        "undefinedsymbols": config.undefinedsymbols,
        "duplicatesymbols": config.duplicatesymbols,
        "strict": config.strict,
        "allowemptysections": config.allowemptysections,
        "bitorder": config.bitorder,
        "sectionvaddr": config.sectionvaddr,
    }


def context_to_dict(
    context: globals.TargetContext | None = None,
) -> dict[str, Any]:
    selected = context or globals.snapshot_target_context()
    return {
        "config": _config_to_dict(selected.config),
        "linker": _encode(selected.linker),
        "defines": sorted(selected.defines),
        "stack_size": selected.stack_size,
        "supports": _encode(selected.supports),
        "asm_variants": _encode(selected.asm_variants),
        "loaded_sources": dict(selected.loaded_sources),
        "blocks": _encode(selected.blocks),
    }


def _load_config(data: dict[str, Any] | None) -> globals.ConfigData | None:
    if data is None:
        return None
    return globals.ConfigData(
        sectiondef=data["sectiondef"],
        sections=tuple(data["sections"]),
        sectionend=data["sectionend"],
        entrysection=data["entrysection"],
        entrylabel=data["entrylabel"],
        comment=data["comment"],
        labelend=data["labelend"],
        datasection=data["datasection"],
        defaultsection=data["defaultsection"],
        sectionflags=dict(data["sectionflags"]),
        sectionalign={key: int(value) for key, value in data["sectionalign"].items()},
        wordsize=int(data["wordsize"]),
        addresssize=int(data["addresssize"]),
        endianness=data["endianness"],
        casesensitive=bool(data["casesensitive"]),
        symbolprefix=data["symbolprefix"],
        localprefix=data["localprefix"],
        undefinedsymbols=data["undefinedsymbols"],
        duplicatesymbols=data["duplicatesymbols"],
        strict=bool(data["strict"]),
        allowemptysections=bool(data["allowemptysections"]),
        bitorder=data.get("bitorder", "msb"),
        sectionvaddr={key: int(value) for key, value in data.get("sectionvaddr", {}).items()},
    )


def _load_tables(connection: sqlite3.Connection) -> dict[str, globals.TableData]:
    tables: dict[str, globals.TableData] = {}
    table_names = connection.execute(
        "SELECT name, headers_json FROM table_defs ORDER BY name"
    ).fetchall()
    for name, headers_json in table_names:
        headers = tuple(json.loads(headers_json))
        rows = [
            tuple(_unjson(values_json))
            for (values_json,) in connection.execute(
                "SELECT values_json FROM table_rows WHERE table_name = ? "
                "ORDER BY row_index",
                (name,),
            )
        ]
        columns = {header: index for index, header in enumerate(headers)}
        tables[name] = globals.TableData(
            name=name,
            headers=headers,
            matrix=rows,
            columns=columns,
        )
    return tables


def context_from_dict(
    connection: sqlite3.Connection,
    context: dict[str, Any],
) -> globals.TargetContext:
    """Decode a target context without consulting or mutating runtime globals."""

    linker = _decode(context.get("linker"))
    supports = _decode(
        context.get("supports", {"__type__": "dict", "items": []})
    )
    variants = _decode(
        context.get("asm_variants", {"__type__": "dict", "items": []})
    )
    blocks = _decode(
        context.get("blocks", {"__type__": "dict", "items": []})
    )
    return globals.TargetContext(
        config=_load_config(context.get("config")),
        linker=linker,
        defines=frozenset(context.get("defines", [])),
        stack_size=context.get("stack_size"),
        tables=_load_tables(connection),
        supports=supports,
        asm_variants=variants,
        loaded_sources=dict(context.get("loaded_sources", {})),
        blocks=blocks,
    )


def load_context(
    connection: sqlite3.Connection,
    context: dict[str, Any],
) -> globals.TargetContext:
    """Decode and expose a context for legacy frontend introspection."""

    target_context = context_from_dict(connection, context)
    globals.activate_target_context(target_context)
    return target_context


def build_database(
    program: CompiledRuleSet,
    source_root: str | Path | None = None,
    *,
    source_fingerprint: str | None = None,
    contract: CompilationContract | None = None,
) -> bytes:
    contract = contract or program.contract
    require_compatible(contract)
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(
            """
            PRAGMA user_version = 1;
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE artifacts (name TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE table_defs (name TEXT PRIMARY KEY, headers_json TEXT NOT NULL);
            CREATE TABLE table_columns (
                table_name TEXT NOT NULL,
                column_name TEXT NOT NULL,
                column_index INTEGER NOT NULL,
                PRIMARY KEY (table_name, column_name)
            );
            CREATE TABLE table_rows (
                table_name TEXT NOT NULL,
                row_index INTEGER NOT NULL,
                values_json TEXT NOT NULL,
                PRIMARY KEY (table_name, row_index)
            );
            CREATE INDEX table_rows_lookup ON table_rows(table_name, row_index);
            """
        )
        connection.execute("INSERT INTO meta VALUES (?, ?)", ("schema", str(SCHEMA_VERSION)))
        connection.execute(
            "INSERT INTO meta VALUES (?, ?)",
            ("contract", json.dumps(contract.as_dict(), sort_keys=True)),
        )
        connection.execute(
            "INSERT INTO meta VALUES (?, ?)",
            ("contract_fingerprint", contract.fingerprint()),
        )
        if source_fingerprint is not None:
            connection.execute(
                "INSERT INTO meta VALUES (?, ?)",
                ("source_fingerprint", source_fingerprint),
            )
        connection.execute(
            "INSERT INTO artifacts VALUES (?, ?)",
            (
                "program",
                json.dumps(
                    program_to_dict(program, source_root),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            ),
        )
        connection.execute("INSERT INTO artifacts VALUES (?, ?)", ("context", json.dumps(context_to_dict(program.context), ensure_ascii=False, separators=(",", ":"))))
        for table in program.context.tables.values():
            connection.execute(
                "INSERT INTO table_defs VALUES (?, ?)",
                (table.name, json.dumps(list(table.headers), ensure_ascii=False)),
            )
            for column, index in table.columns.items():
                connection.execute(
                    "INSERT INTO table_columns VALUES (?, ?, ?)",
                    (table.name, column, index),
                )
            for row_index, row in enumerate(table.matrix):
                connection.execute(
                    "INSERT INTO table_rows VALUES (?, ?, ?)",
                    (table.name, row_index, _json(row)),
                )
        connection.commit()
        return connection.serialize()
    finally:
        connection.close()


def load_database(
    data: bytes,
    *,
    expected_fingerprint: str | None = None,
    expected_contract: CompilationContract | None = None,
) -> CompiledRuleSet:
    expected_contract = expected_contract or current_contract()
    connection = sqlite3.connect(":memory:")
    try:
        connection.deserialize(data)
        row = connection.execute("SELECT value FROM meta WHERE key = 'schema'").fetchone()
        if row is None or int(row[0]) != SCHEMA_VERSION:
            raise ValueError("Versión de base SQLite compilada no compatible.")
        contract_row = connection.execute(
            "SELECT value FROM meta WHERE key = 'contract'"
        ).fetchone()
        fingerprint_row = connection.execute(
            "SELECT value FROM meta WHERE key = 'contract_fingerprint'"
        ).fetchone()
        if contract_row is None or fingerprint_row is None:
            raise ValueError("La base compilada no declara su contrato de ejecución.")
        stored_contract = CompilationContract.from_dict(json.loads(contract_row[0]))
        if fingerprint_row[0] != stored_contract.fingerprint():
            raise ValueError("La huella del contrato SQLite compilado es inválida.")
        try:
            require_compatible(stored_contract, expected_contract)
        except ContractError as exc:
            raise ValueError(str(exc)) from exc
        if expected_fingerprint is not None:
            source_fingerprint_row = connection.execute(
                "SELECT value FROM meta WHERE key = 'source_fingerprint'"
            ).fetchone()
            if source_fingerprint_row is None or source_fingerprint_row[0] != expected_fingerprint:
                raise ValueError(
                    "La base SQLite compilada no corresponde al contenido del paquete."
                )
        program_row = connection.execute(
            "SELECT value FROM artifacts WHERE name = 'program'"
        ).fetchone()
        context_row = connection.execute(
            "SELECT value FROM artifacts WHERE name = 'context'"
        ).fetchone()
        if program_row is None or context_row is None:
            raise ValueError("La base compilada no contiene el programa RIF completo.")
        context = json.loads(context_row[0])
        target_context = load_context(connection, context)
        program = program_from_dict(json.loads(program_row[0]))
        try:
            require_compatible(program.contract, stored_contract)
        except ContractError as exc:
            raise ValueError(str(exc)) from exc
        return CompiledRuleSet(
            rules=program.rules,
            context=target_context,
            contract=stored_contract,
        )
    finally:
        connection.close()


__all__ = [
    "SCHEMA_VERSION",
    "build_database",
    "context_to_dict",
    "context_from_dict",
    "load_context",
    "load_database",
    "program_from_dict",
    "program_to_dict",
]
