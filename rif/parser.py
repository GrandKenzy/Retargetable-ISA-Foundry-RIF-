from __future__ import annotations

"""Módulo del analizador sintáctico (Parser) del compilador RIF.

Analiza el flujo de tokens generado por el Lexer y construye la estructura
de datos del programa (objeto `Program`), validando la sintaxis de las secciones,
las tablas de registros, los bloques de reglas (.rules) y las directivas de
configuración general.
"""

from pathlib import Path
from typing import Any

from .errors import ParseError
from .lexer import Lexer
from .models import (
    BitVariable,
    DataDefinitionInfo,
    LexerConfig,
    PackerConfig,
    Program,
    Section,
    Statement,
    Table,
    TableRow,
    Token,
    HeaderBlock,
    TypeDefinition,
    GLOBAL_STATE_LOCK,
)


CONFIG_DIRECTIVES = {"commit", "comment", "separator", "blocks", "encoding"}


class Parser:
    """Analizador sintáctico para la nueva sintaxis de control RIF.

    Procesa las secciones de un archivo RIF (.pack, .regs, .rules, etc.),
    validando la indentación de los bloques y construyendo el árbol AST.
    """

    def __init__(self, source: str, source_path: str | Path | None = None):
        self.source = source
        self.source_path = Path(source_path) if source_path is not None else None
        self.lexer_config = Lexer.discover_config(source)
        self.comment_char = self.lexer_config.comment
        self.lexer = Lexer(source, self.lexer_config)

    def parse(self) -> Program:
        program = Program(self.source_path, self.lexer_config, {})
        current: Section | None = None
        stack: list[tuple[int, Statement]] = []
        active_table: Table | None = None
        active_table_owner: str | None = None

        for line_no, indent, raw, tokens in self.lexer.lex():
            if not tokens:
                continue

            if current is None and self._is_config_directive(tokens):
                program.top_level.append(Statement(tokens[0].value, tokens[1:], line_no, indent, raw))
                continue

            header = self._section_header(tokens)
            if header is not None and indent == 0:
                prefix, name = header
                if name in program.sections:
                    raise ParseError(f"duplicate section {name!r}", line_no)
                current = Section(name=name, prefix=prefix, line=line_no)
                program.sections[name] = current
                stack.clear()
                active_table = None
                active_table_owner = None
                continue

            if current is None:
                raise ParseError("statement outside any section", line_no)

            current.body_lines.append((line_no, raw))

            if tokens[0].kind == "BLOCK":
                continue

            if tokens[0].kind == "BACKSLASH":
                current.statements.append(Statement("\\", tokens[1:], line_no, indent, raw))
                active_table = None
                active_table_owner = None
                continue

            if self._is_table_line(tokens):
                owner = stack[-1][1].name if stack and indent > stack[-1][0] else None
                if owner != active_table_owner:
                    active_table = None
                    active_table_owner = owner
                active_table = self._parse_table_line(program, current, active_table, tokens, line_no, owner)
                continue

            active_table = None
            active_table_owner = None
            statement = self._statement(tokens, line_no, indent, raw)

            while stack and indent <= stack[-1][0]:
                stack.pop()

            if stack:
                stack[-1][1].children.append(statement)
            else:
                current.statements.append(statement)

            if tokens[-1].kind == "BLOCK":
                stack.append((indent, statement))

        self._build_world(program)
        self._build_regs(program)
        self._build_vars(program)
        self._build_types(program)
        self._build_data_definition(program)
        self._build_memory(program)
        self._build_headers(program)


        collect_codegen(program)
        return program

    def parse_ast(self) -> Program:
        """Parsea solamente AST y metadatos declarativos, sin ejecutar plugins."""
        program = Program(self.source_path, self.lexer_config, {})
        current: Section | None = None
        stack: list[tuple[int, Statement]] = []
        active_table: Table | None = None
        active_table_owner: str | None = None

        for line_no, indent, raw, tokens in self.lexer.lex():
            if not tokens:
                continue

            if current is None and self._is_config_directive(tokens):
                program.top_level.append(Statement(tokens[0].value, tokens[1:], line_no, indent, raw))
                continue

            header = self._section_header(tokens)
            if header is not None and indent == 0:
                prefix, name = header
                if name in program.sections:
                    raise ParseError(f"duplicate section {name!r}", line_no)
                current = Section(name=name, prefix=prefix, line=line_no)
                program.sections[name] = current
                stack.clear()
                active_table = None
                active_table_owner = None
                continue

            if current is None:
                raise ParseError("statement outside any section", line_no)

            current.body_lines.append((line_no, raw))

            if tokens[0].kind == "BLOCK":
                continue

            if tokens[0].kind == "BACKSLASH":
                current.statements.append(Statement("\\", tokens[1:], line_no, indent, raw))
                active_table = None
                active_table_owner = None
                continue

            if self._is_table_line(tokens):
                owner = stack[-1][1].name if stack and indent > stack[-1][0] else None
                if owner != active_table_owner:
                    active_table = None
                    active_table_owner = owner
                active_table = self._parse_table_line(program, current, active_table, tokens, line_no, owner)
                continue

            active_table = None
            active_table_owner = None
            statement = self._statement(tokens, line_no, indent, raw)

            while stack and indent <= stack[-1][0]:
                stack.pop()

            if stack:
                stack[-1][1].children.append(statement)
            else:
                current.statements.append(statement)

            if tokens[-1].kind == "BLOCK":
                stack.append((indent, statement))

        self._build_world(program)
        self._build_regs(program)
        self._build_vars(program)
        self._build_types(program)
        self._build_data_definition(program)
        self._build_memory(program)
        self._build_headers(program)
        return program

    def parse_packer_config(self) -> PackerConfig:
        return parse_packer_config(self.parse())

    def _is_config_directive(self, tokens: list[Token]) -> bool:
        return bool(tokens and tokens[0].kind == "IDENT" and tokens[0].value in CONFIG_DIRECTIVES)

    def _section_header(self, tokens: list[Token]) -> tuple[str | None, str] | None:

        if len(tokens) in (1, 2) and tokens[0].kind == "SECTION":
            if len(tokens) == 1 or tokens[1].kind == "BLOCK":
                return None, tokens[0].value

        if len(tokens) in (2, 3) and tokens[0].kind == "IDENT" and tokens[1].kind == "SECTION":
            if len(tokens) == 2 or tokens[2].kind == "BLOCK":
                return tokens[0].value, tokens[1].value
        return None

    def _statement(self, tokens: list[Token], line: int, indent: int, raw: str) -> Statement:
        block = bool(tokens and tokens[-1].kind == "BLOCK")
        if block:
            tokens = tokens[:-1]
        if not tokens:
            raise ParseError("empty block header", line)
        head = tokens[0]
        if head.kind not in {"IDENT", "SECTION"}:
            raise ParseError("statement must start with an identifier", line)
        return Statement(head.value, tokens[1:], line, indent, raw, block=block)

    def _is_table_line(self, tokens: list[Token]) -> bool:
        return bool(tokens and tokens[0].kind == "SEP")

    def _parse_table_line(
        self,
        program: Program,
        section: Section,
        active_table: Table | None,
        tokens: list[Token],
        line: int,
        owner: str | None = None,
    ) -> Table:
        cells = _table_cells(tokens, line)
        if not cells:
            raise ParseError("empty table line", line)

        if cells[0] == "NAME":
            fields = cells
            if len(fields) != len(set(fields)):
                raise ParseError("duplicate table field", line)
            table = Table(section=section.name, fields=fields, owner=owner)
            section.tables.append(table)
            table_key = section.name if owner is None else f"{section.name}:{owner}"
            program.tables[table_key] = table
            return table

        if active_table is None:
            raise ParseError("table row found before a NAME header", line)

        if len(cells) > len(active_table.fields):
            raise ParseError("table row has more cells than its header", line)
        padded = cells + [""] * (len(active_table.fields) - len(cells))
        row_name = padded[0]
        if not row_name:
            raise ParseError("table row NAME cannot be empty", line)
        if row_name in active_table.rows:
            raise ParseError(f"duplicate table object {row_name!r}", line)

        values = {
            field: _parse_table_value(field, value)
            for field, value in zip(active_table.fields[1:], padded[1:])
        }
        values.setdefault("NAME", row_name)
        if section.name == ".data":
            values.setdefault("PRIVTYPE", "symbol")
        row = TableRow(name=row_name, values=values, line=line, section=section.name)
        active_table.add_row(row)
        if owner is None and section.name not in {".types"}:
            if row_name in program.objects:
                raise ParseError(f"duplicate global object {row_name!r}", line)
            program.objects[row_name] = row
        return active_table

    def _build_world(self, program: Program) -> None:
        world = program.section(".world")
        if world is None:
            return
        for stmt in world.statements:
            if stmt.children:
                continue
            if not stmt.args:
                program.world.values[stmt.name] = True
            elif len(stmt.args) == 1:
                program.world.values[stmt.name] = _token_value(stmt.args[0])
            else:
                program.world.values[stmt.name] = [_token_value(token) for token in stmt.args]

    def _build_regs(self, program: Program) -> None:
        from .models import Register
        regs_sec = program.section(".regs")
        if regs_sec is None:
            return

        for stmt in regs_sec.statements:
            if stmt.name == "hiddesubs":
                program.regs.hiddesubs = True
            elif stmt.name == "order":
                if stmt.args:
                    program.regs.order_column = stmt.args[0].value

        table = program.tables.get(".regs")
        if table is None:
            return


        order_col = program.regs.order_column
        matched_col = None
        if order_col:
            matched_col = next((f for f in table.fields if f.lower() == order_col.lower()), None)

        sorted_rows = list(table.rows.values())

        if matched_col:
            def is_numeric(val: Any) -> bool:
                if isinstance(val, (int, float)):
                    return True
                try:
                    float(str(val))
                    return True
                except ValueError:
                    return False

            all_numeric = all(is_numeric(r.values.get(matched_col)) for r in table.rows.values() if r.values.get(matched_col) != "")

            if all_numeric:
                def get_numeric_val(row: TableRow) -> float:
                    val = row.values.get(matched_col, 0)
                    if isinstance(val, (int, float)):
                        return float(val)
                    try:
                        return float(val)
                    except ValueError:
                        return 0.0

                sorted_rows = sorted(sorted_rows, key=get_numeric_val, reverse=True)

        family_field = next((f for f in table.fields if f.lower() == "family"), "FAMILY")
        bits_field = next((f for f in table.fields if f.lower() == "bits"), "bits")

        rows_by_family: dict[str, list[TableRow]] = {}
        for row in sorted_rows:
            fam = str(row.values.get(family_field, "")).strip() or row.name
            rows_by_family.setdefault(fam, []).append(row)

        registers_list: list[Register] = []
        for fam, fam_rows in rows_by_family.items():
            parent_row = fam_rows[0]

            parent_bits = 0
            try:
                parent_bits = int(parent_row.values.get(bits_field, 0))
            except Exception:
                pass

            parent_reg = Register(
                name=parent_row.name,
                family=fam,
                bits=parent_bits,
                is_parent=True,
                parent_name=None,
                alias=None,
                values=parent_row.values
            )
            registers_list.append(parent_reg)
            program.regs.families.setdefault(fam, []).append(parent_reg)

            for idx, child_row in enumerate(fam_rows[1:]):
                child_bits = 0
                try:
                    child_bits = int(child_row.values.get(bits_field, 0))
                except Exception:
                    pass

                alias = None
                if program.regs.hiddesubs:
                    suffix = chr(97 + idx)
                    alias = f"{parent_row.name}:{suffix}"
                    program.regs.aliases[child_row.name] = alias

                child_reg = Register(
                    name=child_row.name,
                    family=fam,
                    bits=child_bits,
                    is_parent=False,
                    parent_name=parent_row.name,
                    alias=alias,
                    values=child_row.values
                )
                registers_list.append(child_reg)
                program.regs.families.setdefault(fam, []).append(child_reg)

        program.regs.registers = registers_list

    def _build_vars(self, program: Program) -> None:
        vars_sec = program.section(".vars")
        if vars_sec is None:
            return

        for stmt in vars_sec.statements:
            name: str | None = None
            value: str | None = None

            if len(stmt.args) == 2 and stmt.args[0].kind == "EQUAL":
                name = stmt.name
                value = stmt.args[1].value
            elif not stmt.args and "=" in stmt.name:
                left, right = stmt.name.split("=", 1)
                name = left.strip()
                value = right.strip()
            else:
                raise ParseError(".vars usa NAME=value", stmt.line)

            if not name or not _is_identifier_name(name):
                raise ParseError(f"variable de bits inválida {name!r}", stmt.line)
            if name in program.vars:
                raise ParseError(f"variable de bits duplicada {name!r}", stmt.line)

            bits = str(value or "").strip().replace("_", "")
            if len(bits) not in (4, 8) or any(ch not in "01" for ch in bits):
                raise ParseError("las variables de .vars solo permiten 4 u 8 bits exactos", stmt.line)

            program.vars[name] = BitVariable(name=name, bits=bits, line=stmt.line)

    def _build_types(self, program: Program) -> None:
        table = program.tables.get(".types")
        if table is None:
            return

        size_field = next((field for field in table.fields if field.lower() == "size"), "SIZE")
        for row in table.rows.values():
            values = dict(row.values)
            values.setdefault("NAME", row.name)
            size = values.get(size_field)
            values.setdefault("SIZE", size)
            values.setdefault("PRIVTYPE", "type")
            values.setdefault("TYPE", "TYPE")
            program.type_defs.add(TypeDefinition(row.name, size, values, row.line))

    def _build_data_definition(self, program: Program) -> None:
        section = program.section(".DATA_DEFINITION") or program.section(".data_definition")
        if section is None:
            return

        info = DataDefinitionInfo()
        in_pattern = False
        for stmt in section.statements:
            if stmt.name == "\\":
                in_pattern = not in_pattern
                continue

            if in_pattern:
                literal = None
                if stmt.name == "LITERAL":
                    if not stmt.args:
                        raise ParseError("LITERAL en .DATA_DEFINITION necesita valor", stmt.line)
                    literal = _token_value(stmt.args[0])
                info.pattern.append((stmt.name, literal))
                continue

            info.add_option(stmt.name, [_token_value(token) for token in stmt.args if token.kind != "COMMA"])

        program.data_definition = info

    def _build_memory(self, program: Program) -> None:
        from .memory import memory_kind_for_section, memory_region_from_values

        for section_name in (".stacks", ".stack", ".heaps", ".heap"):
            table = program.tables.get(section_name)
            if table is None:
                continue
            kind = memory_kind_for_section(section_name)
            if kind is None:
                continue
            for row in table.rows.values():
                region = memory_region_from_values(kind, row.name, row.values, row.line, program)
                row.values.update(region.values)
                program.memory.add(region)

    def _build_headers(self, program: Program) -> None:
        headers_sec = program.section(".headers")
        if headers_sec is None:
            return

        table = program.tables.get(".headers")
        if table is not None:
            for row in table.rows.values():
                block = HeaderBlock(
                    name=row.name,
                    size=row.values.get("SIZE"),
                    hex=str(row.values.get("HEX", "") or ""),
                    fill=str(row.values.get("FILL", "") or ""),
                    line=row.line,
                )
                program.headers.add(block)

        for stmt in headers_sec.statements:
            block = program.headers.blocks.get(stmt.name)
            if block is None:
                block = HeaderBlock(name=stmt.name, line=stmt.line)
                program.headers.add(block)
            block.table = program.tables.get(f".headers:{stmt.name}")
            block.statements = stmt.children


def parse_packer_config(program: Program) -> PackerConfig:
    config = PackerConfig()
    pack = program.section(".pack")
    if pack is None:
        program.type_map.clear()
        return config

    from .models import TYPES_MAP
    TYPES_MAP.clear()
    program.type_map.clear()

    for stmt in pack.statements:
        if stmt.name == "plugext":
            _require_args(stmt, 1)
            config.plugext = _stringish(stmt.args[0])
        elif stmt.name == "plugin":
            _require_args(stmt, 1)
            config.plugins.append(_stringish(stmt.args[0]))
        elif stmt.name == "precompile":
            _require_args(stmt, 1)
            config.precompilers.append(_stringish(stmt.args[0]))
        elif stmt.name == "types":
            for child in stmt.children:
                if child.name == "from":
                    if len(child.args) == 3 and _stringish(child.args[1]) == "as":
                        sec_name = _stringish(child.args[0])
                        type_name = _stringish(child.args[2])
                        config.types[sec_name] = type_name
                        TYPES_MAP[sec_name] = type_name
                        TYPES_MAP[type_name] = sec_name
                        program.type_map[sec_name] = type_name
                        program.type_map[type_name] = sec_name
        elif stmt.name == "packer":
            config.enabled = True
            for child in stmt.children:
                name = child.name
                args = child.args
                if name == "fsystem":
                    _require_args(child, 1)
                    config.fsystem = _int_arg(args[0], child.line)
                    if config.fsystem not in (0, 1):
                        raise ParseError("fsystem must be 0 or 1", child.line)
                elif name == "ext":
                    _require_args(child, 1)
                    config.ext = _stringish(args[0])
                    if not config.ext.startswith("."):
                        config.ext = "." + config.ext
                elif name == "sectpre":
                    _require_args(child, 1)
                    config.sectpre = _stringish(args[0])
                elif name == "subpre":
                    _require_args(child, 1)
                    config.subpre = "*" if args[0].kind == "STAR" else _stringish(args[0])
                elif name == "definesec":
                    _require_args(child, 1)
                    config.defined_sections.add(PackerConfig.normalize_section(_stringish(args[0])))
                elif name == "setpre":
                    _require_args(child, 2)
                    prefix = _stringish(args[0])
                    section = PackerConfig.normalize_section(_stringish(args[1]))
                    config.prefix_to_section[prefix] = section
                elif name == "needsect":
                    _require_args(child, 1)
                    config.required_prefixes.add(_stringish(args[0]))
                else:
                    raise ParseError(f"unknown packer option {name!r}", child.line)

    return config


def collect_codegen(program: Program) -> Program:
    """Ejecuta la fase de coleccion de IR basada en plugins sobre un AST ya parseado."""
    with GLOBAL_STATE_LOCK:
        packer_config = parse_packer_config(program)
        if packer_config.sectpre:
            for name, section in program.sections.items():
                if name != ".pack" and section.prefix != packer_config.sectpre:
                    raise ParseError(
                        f"section {name!r} must have prefix {packer_config.sectpre!r}",
                        section.line
                    )

        plugins = load_plugins(program, packer_config)
        if plugins:
            run_plugins_on_statements(program, plugins)
    return program


def load_plugins(program: Program, config: PackerConfig) -> dict[str, Any]:
    import importlib.util
    import sys
    from .errors import PackError

    loaded: dict[str, Any] = {}

    base_dir = Path.cwd()
    if program.source_path:
        base_dir = Path(program.source_path).parent

    plugin_roots = _plugin_roots(base_dir)
    if not plugin_roots:
        return loaded

    ext = config.plugext or ".py"

    for plugin_name in config.plugins:
        plugin_root = _find_plugin_root(plugin_roots, plugin_name)
        if plugin_root is None:
            continue
        plugin_dir = plugin_root / "plugins"
        if not plugin_dir.exists():
            continue

        for path in sorted(plugin_dir.rglob(f"*{ext}")):
            if path.is_file():
                relative_name = "_".join(path.relative_to(plugin_dir).with_suffix("").parts)
                module_name = f"rif.plugins.{_module_safe(plugin_name)}.{_module_safe(relative_name)}"
                spec = importlib.util.spec_from_file_location(module_name, path)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = mod
                    try:
                        spec.loader.exec_module(mod)
                        loaded[path.stem] = mod
                    except Exception as e:
                        raise PackError(f"Failed to load plugin {path}: {e}")
    return loaded


def run_precompilers(program: Program, config: PackerConfig) -> None:
    import importlib.util
    import sys
    from .errors import PackError
    from .models import Operators

    if not config.precompilers:
        return

    base_dir = Path.cwd()
    if program.source_path:
        base_dir = Path(program.source_path).parent

    Operators.set_program(program)

    for plugin_name in config.precompilers:
        plugin_root = _find_plugin_root(_plugin_roots(base_dir), plugin_name)
        if plugin_root is None:
            path = base_dir / "plugins" / plugin_name / "compiler.py"
            raise PackError(f"precompile plugin not found: {path}")
        path = plugin_root / "compiler.py"
        if not path.exists():
            raise PackError(f"precompile plugin not found: {path}")

        module_name = f"rif.precompile.{plugin_name}.compiler"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise PackError(f"Failed to load precompile plugin {path}")

        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        try:
            spec.loader.exec_module(mod)
            if not hasattr(mod, "_start"):
                raise PackError(f"precompile plugin {path} does not define _start()")
            mod._start()
        except PackError:
            raise
        except Exception as exc:
            raise PackError(f"Error executing precompile plugin {path}: {exc}") from exc


def _plugin_roots(base_dir: Path) -> list[Path]:
    roots: list[Path] = []
    for candidate in (base_dir / "plugins", Path.cwd() / "plugins"):
        resolved = candidate.resolve()
        if candidate.exists() and resolved not in roots:
            roots.append(resolved)
    return roots


def _find_plugin_root(plugin_roots: list[Path], plugin_name: str) -> Path | None:
    for plugins_root in plugin_roots:
        candidate = _safe_plugin_root(plugins_root, plugin_name)
        if candidate.exists():
            return candidate
    return None


def _safe_plugin_root(plugins_root: Path, plugin_name: str) -> Path:
    from .errors import PackError

    name = str(plugin_name).strip()
    if not name or Path(name).is_absolute() or any(part in {"", ".", ".."} for part in Path(name).parts):
        raise PackError(f'plugin name inseguro: "{plugin_name}"')
    if any(sep in name for sep in ("/", "\\")):
        raise PackError(f'plugin name no puede contener rutas: "{plugin_name}"')
    candidate = (plugins_root / name).resolve()
    root = plugins_root.resolve()
    if candidate != root and root not in candidate.parents:
        raise PackError(f'plugin fuera de plugins/: "{plugin_name}"')
    return candidate


def _module_safe(value: str) -> str:
    text = str(value).strip().replace("-", "_")
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in text)


def run_plugins_on_statements(program: Program, plugins: dict[str, Any]) -> None:
    from .models import Line, Err, Expr, FlowInstruction, Operators, PluginContext, RuleIndicator
    from .errors import Errors
    from .errors import PackError

    Operators.set_program(program)
    Operators.Reset()
    Errors.clear()

    def token_values(stmt: Statement) -> tuple[str, ...]:
        return tuple(token.value for token in stmt.args)

    def run_plugin(stmt: Statement, rule_name: str | None) -> list[Any]:
        mod = plugins[stmt.name]
        tokens = [stmt.name] + stmt.arg_values()
        Line.set_tokens(tokens)
        Line.line = stmt.line
        RuleIndicator.current = rule_name
        context = PluginContext(
            program=program,
            phase="parse",
            rule_name=rule_name,
            statement=stmt,
            line=stmt.line,
        )

        try:
            if hasattr(mod, "set_context"):
                mod.set_context(context)
            setattr(mod, "CONTEXT", context)
            if hasattr(mod, "_start"):
                res = mod._start()
            else:
                res = mod.main()
            if isinstance(res, Err):
                raise PackError(f"Plugin {stmt.name} error: {res.message}", stmt.line)
            _record_plugin_result(program, res, rule_name)
            return _result_items(res)
        except Exception as e:
            if isinstance(e, PackError):
                raise e
            raise PackError(f"Error executing plugin {stmt.name}: {e}", stmt.line)
        finally:
            RuleIndicator.current = None
            Line.clear()

    def process_plain_statement(stmt: Statement, rule_name: str | None) -> list[Any]:
        if stmt.name == "call" and rule_name is None:
            return process_statement_list(stmt.children, rule_name)
        if stmt.name in plugins:
            return run_plugin(stmt, rule_name)



        return process_statement_list(stmt.children, rule_name)

    def process_on(stmts: list[Statement], index: int, rule_name: str | None) -> tuple[FlowInstruction, int]:
        stmt = stmts[index]
        if not stmt.block:
            raise PackError("ON requiere ':' y un bloque indentado", stmt.line)
        on_flow = FlowInstruction(
            kind="ON",
            args=token_values(stmt),
            rule_name=rule_name,
            line=stmt.line,
            body=process_statement_list(stmt.children, rule_name),
        )

        next_index = index + 1
        if next_index < len(stmts) and stmts[next_index].name == "OFF":
            off_stmt = stmts[next_index]
            if off_stmt.args:
                raise PackError("OFF no espera argumentos", off_stmt.line)
            if not off_stmt.block:
                raise PackError("OFF requiere ':' y un bloque indentado", off_stmt.line)
            on_flow.branches.append(
                FlowInstruction(
                    kind="OFF",
                    args=(),
                    rule_name=rule_name,
                    line=off_stmt.line,
                    body=process_statement_list(off_stmt.children, rule_name),
                )
            )
            next_index += 1

        program.codegen.add_flow(on_flow, rule_name)
        return on_flow, next_index

    def process_switch(stmt: Statement, rule_name: str | None) -> FlowInstruction:
        if not stmt.args:
            raise PackError("switch espera una expresión", stmt.line)
        if not stmt.block:
            raise PackError("switch requiere ':' y un bloque indentado", stmt.line)
        if not stmt.children:
            raise PackError("switch requiere al menos un case", stmt.line)

        switch_flow = FlowInstruction(
            kind="switch",
            args=token_values(stmt),
            rule_name=rule_name,
            line=stmt.line,
        )

        for child in stmt.children:
            if child.name != "case":
                raise PackError("switch solo puede contener case directamente", child.line)
            if not child.args:
                raise PackError("case espera un valor", child.line)
            if not child.block:
                raise PackError("case requiere ':' y un bloque indentado", child.line)
            switch_flow.branches.append(
                FlowInstruction(
                    kind="case",
                    args=token_values(child),
                    rule_name=rule_name,
                    line=child.line,
                    body=process_statement_list(child.children, rule_name),
                )
            )

        program.codegen.add_flow(switch_flow, rule_name)
        return switch_flow

    def process_statement(stmt: Statement, rule_name: str | None) -> list[Any]:
        if stmt.name == "ON":
            flow, _ = process_on([stmt], 0, rule_name)
            return [flow]
        if stmt.name == "OFF":
            raise PackError("OFF solo puede aparecer inmediatamente después de un ON", stmt.line)
        if stmt.name == "switch":
            return [process_switch(stmt, rule_name)]
        if stmt.name == "case":
            raise PackError("case solo puede aparecer dentro de switch", stmt.line)
        return process_plain_statement(stmt, rule_name)

    def process_statement_list(stmts: list[Statement], rule_name: str | None) -> list[Any]:
        out: list[Any] = []
        index = 0
        while index < len(stmts):
            stmt = stmts[index]
            if stmt.name == "ON":
                flow, index = process_on(stmts, index, rule_name)
                out.append(flow)
                continue
            if stmt.name == "OFF":
                raise PackError("OFF solo puede aparecer inmediatamente después de un ON", stmt.line)
            if stmt.name == "switch":
                out.append(process_switch(stmt, rule_name))
                index += 1
                continue
            if stmt.name == "case":
                raise PackError("case solo puede aparecer dentro de switch", stmt.line)
            out.extend(process_plain_statement(stmt, rule_name))
            index += 1
        return out



    for section in program.sections.values():
        if section.name == ".rules":
            continue
        process_statement_list(section.statements, None)

    rules_sec = program.section(".rules")
    if rules_sec is None:
        program.operator_saved = {key: list(value) for key, value in Operators.saved_operators.items()}
        program.operator_bindings = {key: dict(value) for key, value in Operators.bindings.items()}
        return

    for rule in rules_sec.statements:
        process_statement_list(rule.children, rule.name)

    program.operator_saved = {key: list(value) for key, value in Operators.saved_operators.items()}
    program.operator_bindings = {key: dict(value) for key, value in Operators.bindings.items()}

def _result_items(result: Any) -> list[Any]:
    if result is None or result == 0:
        return []
    if isinstance(result, list):
        out: list[Any] = []
        for item in result:
            out.extend(_result_items(item))
        return out
    return [result]


def _record_plugin_result(program: Program, result: Any, rule_name: str | None) -> None:
    from .models import Expr

    if result is None or result == 0:
        return

    if isinstance(result, Expr):
        program.codegen.add_expr(result, rule_name)
        return

    if isinstance(result, list):
        for item in result:
            _record_plugin_result(program, item, rule_name)



def _is_identifier_name(value: str) -> bool:
    if not value:
        return False
    if not (value[0].isalpha() or value[0] == "_"):
        return False
    return all(ch.isalnum() or ch in "_-" for ch in value)


def _table_cells(tokens: list[Token], line: int) -> list[str]:
    if not tokens or tokens[0].kind != "SEP":
        raise ParseError("table line must start with separator", line)
    cells: list[list[Token]] = [[]]
    for token in tokens[1:]:
        if token.kind == "SEP":
            cells.append([])
        else:
            cells[-1].append(token)

    if cells and not cells[-1]:
        cells.pop()
    return [_cell_text(cell) for cell in cells]


def _cell_text(tokens: list[Token]) -> str:
    if not tokens:
        return ""
    return " ".join(token.value for token in tokens).strip()


def _parse_table_value(field: str, value: str) -> Any:
    field_name = field.strip().lower()
    compact = value.strip().replace("_", "")

    if field_name in {"binary", "code", "opcode", "bitspec"}:
        if compact and all(ch in "01" for ch in compact):
            return compact

    return _parse_scalar_text(value)


def _parse_scalar_text(value: str) -> Any:
    compact = value.replace("_", "")
    if compact == "":
        return ""
    try:
        if compact.startswith(("0x", "0X", "0b", "0B")) or compact.isdigit():
            return int(compact, 0)
    except ValueError:
        pass
    return value


def _token_value(token: Token) -> Any:
    if token.kind == "INT":
        return _int_arg(token, token.line)
    if token.kind == "STAR":
        return "*"
    return token.value


def _require_args(stmt: Statement, count: int) -> None:
    if len(stmt.args) != count:
        raise ParseError(f"{stmt.name} expects {count} argument(s)", stmt.line)


def _stringish(token: Token) -> str:
    if token.kind in {"STRING", "IDENT", "SECTION", "INT", "STAR"}:
        return token.value
    raise ParseError(f"invalid argument token {token.kind!r}", token.line)


def _int_arg(token: Token, line: int) -> int:
    value = token.value.replace("_", "")
    try:
        return int(value, 0)
    except ValueError as exc:
        raise ParseError(f"invalid integer {token.value!r}", line) from exc
