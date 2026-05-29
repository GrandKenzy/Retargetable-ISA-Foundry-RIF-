"""Módulo de compilación y codificación del framework RIF.

Este módulo implementa el motor de compilación que procesa las reglas del
Instruction Set Architecture (ISA), evalúa las expresiones DSL de los plugins,
realiza la resolución de operandos, gestiona el diseño de memoria de datos, y
emite la representación binaria empaquetada final.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import PackError
from .expr import UnresolvedExpression, eval_int_expr
from .models import (
    CompileResult,
    EmitChunk,
    EmitInstruction,
    Err,
    Expr,
    FlowInstruction,
    GLOBAL_STATE_LOCK,
    Line,
    MemoryRegion,
    OperandValue,
    Operators,
    Placeholder,
    PluginContext,
    Program,
    REG,
    RuleIndicator,
    Relocation,
    Statement,
    Table,
    TableRow,
    TYPES_MAP,
    TypeDefinition,
    TypeInfo,
)
from .memory import memory_region_from_values
from .parser import Parser, load_plugins, parse_packer_config, run_precompilers
from .resolver import PlaceholderResolver


@dataclass
class _Runtime:
    """Estado de ejecución dinámico durante la compilación de una instrucción.

    Mantiene los enlaces de variables, la secuencia acumulada de bits emitidos,
    así como los placeholders y expresiones pendientes de resolución.
    """
    rule_name: str
    source: str
    bindings: dict[str, OperandValue]
    bits: str = ""
    bit_values: dict[str, str] | None = None
    placeholders: list[Placeholder] | None = None
    relocations: list[Relocation] | None = None
    expressions: list[Any] | None = None
    stack: list[str] | None = None
    base_offset_bits: int = 0
    labels: dict[str, int] | None = None

    def __post_init__(self) -> None:
        if self.bit_values is None:
            self.bit_values = {}
        if self.placeholders is None:
            self.placeholders = []
        if self.relocations is None:
            self.relocations = []
        if self.expressions is None:
            self.expressions = []
        if self.stack is None:
            self.stack = []
        if self.labels is None:
            self.labels = {}


class _EndInstruction(Exception):
    """Señal interna de control de flujo para detener la compilación de la regla actual.

    Esta excepción es lanzada al procesar el comando DSL `end_instruction` para abortar
    el procesamiento de la línea inmediatamente.
    """


class Compiler:
    """Compilador del set de instrucciones de RIF.

    Traduce líneas de código ensamblador que coinciden con las reglas definidas en el
    archivo `.pack`, aplicando semántica DSL y delegación a plugins dinámicos para
    generar bits empaquetados coherentes.
    """

    def __init__(self, program: Program):
        """Inicializa el compilador a partir de un programa RIF previamente parseado.

        Args:
            program: Estructura AST de la definición del ISA cargada en memoria.
        """
        self.program = program
        with GLOBAL_STATE_LOCK:
            self.config = parse_packer_config(program)
            self._type_map = dict(program.type_map)
            self._activate_type_map()
            run_precompilers(program, self.config)
            self.plugins = load_plugins(program, self.config)
            Operators.set_program(program)
            Operators.saved_operators.clear()
            Operators.saved_operators.update({key: list(value) for key, value in program.operator_saved.items()})
            Operators.bindings.clear()
            Operators.bindings.update({key: dict(value) for key, value in program.operator_bindings.items()})
            self._saved_operators = {key: list(value) for key, value in program.operator_saved.items()}
            self._operator_bindings = {key: dict(value) for key, value in program.operator_bindings.items()}
        self.labels: dict[str, int] = {}

    @classmethod
    def from_file(cls, source_path: str | Path) -> "Compiler":
        """Crea una instancia del compilador a partir de la ruta de un archivo .pack.

        Args:
            source_path: Ruta al archivo que contiene la definición del ISA.

        Returns:
            Una instancia configurada del Compilador.
        """
        path = Path(source_path)
        program = Parser(path.read_text(encoding="utf-8"), path).parse()
        return cls(program)

    def compile_line(self, source: str) -> CompileResult:
        """Compila una única línea de instrucción de lenguaje ensamblador RIF.

        Args:
            source: Línea de texto con la instrucción a compilar.

        Returns:
            Un objeto CompileResult que contiene los bits generados o placeholders diferidos.
        """
        with GLOBAL_STATE_LOCK:
            return self._compile_line_at(source, 0, self.labels)

    def _compile_line_at(self, source: str, base_offset_bits: int, labels: dict[str, int]) -> CompileResult:
        """Compila una instrucción en un desplazamiento de bits y contexto de etiquetas específico.

        Args:
            source: Línea de instrucción.
            base_offset_bits: Posición base en bits dentro de la sección actual.
            labels: Diccionario de etiquetas resueltas y sus desplazamientos en bytes.

        Returns:
            Resultado detallado de la compilación.
        """
        self._activate()
        tokens = _split_instruction(source)
        if not tokens:
            raise PackError("instrucción vacía")

        data_result = self._compile_data_definition(source, base_offset_bits)
        if data_result is not None:
            return data_result

        rule_name = tokens[0]
        rule = self._rule(rule_name)
        if rule is None:
            memory_result = self._compile_memory_definition(source)
            if memory_result is not None:
                return memory_result
            raise PackError(f'regla desconocida "{rule_name}"')

        bindings, consumed = self._match_rule(rule_name, tokens[1:])
        if consumed != len(tokens) - 1:
            rest = " ".join(tokens[1 + consumed:])
            raise PackError(f'tokens sobrantes después de matchear {rule_name}: {rest}')

        runtime = _Runtime(
            rule_name=rule_name,
            source=source,
            bindings=bindings,
            base_offset_bits=base_offset_bits,
            labels=labels,
        )
        try:
            self._execute_rule_body(rule_name, runtime)
        except _EndInstruction:
            pass
        resolution = PlaceholderResolver(self.program, labels).resolve_all(runtime.placeholders)
        runtime.placeholders = list(resolution.unresolved)

        data = None
        if not runtime.placeholders:
            if len(runtime.bits) % 8 != 0:
                raise PackError(f"la emisión final no está alineada a byte: {len(runtime.bits)} bits")
            data = bytes(int(runtime.bits[i:i + 8], 2) for i in range(0, len(runtime.bits), 8))

        return CompileResult(
            rule_name=rule_name,
            source=source,
            data=data,
            bits=runtime.bits,
            placeholders=list(runtime.placeholders),
            expressions=list(runtime.expressions),
            resolved_placeholders=list(resolution.resolved),
            relocations=list(runtime.relocations or []),
        )

    def _activate(self) -> None:
        """Restaura y activa el estado de registro y bindings de operadores del programa.

        Esto garantiza que las expresiones de operadores se evalúen con el contexto correcto.
        """
        Operators.set_program(self.program)
        self._activate_type_map()
        Operators.saved_operators.clear()
        Operators.saved_operators.update({key: list(value) for key, value in self._saved_operators.items()})
        Operators.bindings.clear()
        Operators.bindings.update({key: dict(value) for key, value in self._operator_bindings.items()})

    def _activate_type_map(self) -> None:
        TYPES_MAP.clear()
        TYPES_MAP.update(self._type_map)

    def compile_lines(self, source: str) -> list[CompileResult]:
        """Compila múltiples líneas de ensamblador RIF en una sola pasada lógica.

        Primero realiza un análisis preliminar de etiquetas y definiciones de datos
        para resolver referencias hacia adelante, y luego compila cada instrucción
        de forma definitiva.

        Args:
            source: Cadena multilínea con el código ensamblador.

        Returns:
            Lista de resultados de compilación para cada instrucción válida.
        """
        with GLOBAL_STATE_LOCK:
            return self._compile_lines_locked(source)

    def _compile_lines_locked(self, source: str) -> list[CompileResult]:
        lines = [_strip_source_comment(raw).strip() for raw in source.splitlines()]
        lines = [line for line in lines if line]

        labels: dict[str, int] = {}
        offset_bits = 0
        for line in lines:
            label = _label_from_line(line)
            if label is not None:
                if offset_bits % 8 != 0:
                    raise PackError(f'la etiqueta "{label}" no cae en límite de byte')
                labels[label] = offset_bits // 8
                continue
            data_result = self._compile_data_definition(line, offset_bits)
            if data_result is not None:
                offset_bits += len(data_result.bits)
                continue
            memory_result = self._compile_memory_definition(line)
            if memory_result is not None:
                continue
            result = self._compile_line_at(line, offset_bits, labels)
            offset_bits += len(result.bits)

        self.labels = labels
        out: list[CompileResult] = []
        offset_bits = 0
        for line in lines:
            label = _label_from_line(line)
            if label is not None:
                continue
            result = self._compile_line_at(line, offset_bits, labels)
            out.append(result)
            offset_bits += len(result.bits)
        return out

    def compile_bytes(self, source: str) -> bytes:
        """Compila código ensamblador multilínea directamente a una secuencia de bytes empaquetados.

        Lanza PackError si existen placeholders sin resolver (como etiquetas o variables libres).

        Args:
            source: Código ensamblador.

        Returns:
            Representación binaria final en bytes.
        """
        results = self.compile_lines(source)
        missing = [ph.name for result in results for ph in result.placeholders]
        if missing:
            raise PackError("no se puede emitir bytes finales con placeholders: " + ", ".join(missing))
        return b"".join(result.data or b"" for result in results)

    def _compile_memory_definition(self, source: str) -> CompileResult | None:
        """Procesa y compila definiciones de regiones de memoria como pila (stack) o montón (heap).

        Args:
            source: Línea de instrucción con la definición de memoria.

        Returns:
            CompileResult si se compiló con éxito, o None si no corresponde a una definición de memoria.
        """
        tokens = _split_instruction(source)
        if not tokens:
            return None
        kind = tokens[0].lower()
        if kind not in {"stack", "heap"}:
            return None
        if len(tokens) < 3:
            raise PackError(f"{kind} usa: {kind} NAME TYPE [COUNT] [SECTION] [ALIGN] [FILL]")

        name = tokens[1]
        if not _is_label_name(name):
            raise PackError(f'nombre de {kind} invalido "{name}"')

        values: dict[str, Any] = {
            "NAME": name,
            "TYPE": tokens[2],
        }
        if len(tokens) > 3:
            values["COUNT"] = tokens[3]
        if len(tokens) > 4:
            values["SECTION"] = tokens[4]
        if len(tokens) > 5:
            values["ALIGN"] = tokens[5]
        if len(tokens) > 6:
            values["FILL"] = tokens[6]
        if len(tokens) > 7:
            raise PackError(f"{kind} tiene demasiados argumentos")

        region = memory_region_from_values(kind, name, values, 0, self.program)
        self._register_memory_region(region)
        return CompileResult(kind, source, b"", "")

    def _compile_data_definition(self, source: str, base_offset_bits: int) -> CompileResult | None:
        """Compila una declaración de inicialización de datos estáticos en memoria (e.g., 'var_name type = valor').

        Args:
            source: Línea con la declaración de datos.
            base_offset_bits: Desplazamiento base acumulado en bits.

        Returns:
            CompileResult de la definición de datos si matchea el formato, o None en caso contrario.
        """
        if not self.program.data_definition.pattern:
            return None

        tokens = _split_instruction(source)
        if len(tokens) < 4:
            return None

        name, type_token, literal = tokens[0], tokens[1], tokens[2]
        if literal != "=":
            return None
        if not _is_label_name(name):
            return None

        parsed_type = _parse_type_token(type_token, self.program)
        if parsed_type is None:
            return None
        type_def, requested_size, dimensions = parsed_type

        value_token = " ".join(tokens[3:]).strip()
        allow_string = _type_allows_string(type_def, self.program)
        immediate = _parse_immediate_value(value_token, allow_string=allow_string)
        if immediate is None:
            raise PackError(f'data definition "{source}" necesita VALUE valido')

        type_size = requested_size if requested_size is not None else type_def.bits
        value_bits = str(immediate["binary"])
        value_size = int(immediate["size"])

        if type_size is not None:
            strict = _truthy(type_def.values.get("strictsize"))
            if value_size > type_size:
                raise PackError(f'VALUE de {value_size} bits no cabe en TYPE {type_def.name} de {type_size} bits')
            if strict and value_size != type_size:
                raise PackError(f'TYPE {type_def.name} exige {type_size} bits exactos; VALUE tiene {value_size}')
            value_bits = value_bits.rjust(type_size, "0")

        if len(value_bits) % 8 != 0:
            raise PackError("data definition debe emitir un numero completo de bytes")

        offset = base_offset_bits // 8
        data = bytes(int(value_bits[i:i + 8], 2) for i in range(0, len(value_bits), 8))
        row_values = {
            "NAME": name,
            "TYPE": type_def.name,
            "TYPE_RAW": type_token,
            "PRIVTYPE": "symbol",
            "raw": immediate["raw"],
            "size": len(value_bits),
            "bits": len(value_bits),
            "binary": value_bits,
            "addrs": offset,
            "VALUE": immediate.get("value"),
            "SOURCE_DATA": True,
            "SECTION_OFFSET": offset,
        }
        if dimensions:
            row_values["dimensions"] = dimensions
        self._register_data_row(name, row_values)
        index_option = self.program.data_definition.options.get("index") or ["false"]
        if dimensions and _truthy(index_option[0]):
            count = 1
            for item in dimensions:
                count *= item
            element_bits = type_def.bits
            if element_bits is None and count and len(value_bits) % count == 0:
                element_bits = len(value_bits) // count
            if element_bits is not None and element_bits % 8 == 0:
                for index in range(count):
                    start = index * element_bits
                    end = start + element_bits
                    child_name = f"{name}[{index}]"
                    child_values = dict(row_values)
                    child_values["NAME"] = child_name
                    child_values["parent"] = name
                    child_values["index"] = index
                    child_values["size"] = element_bits
                    child_values["bits"] = element_bits
                    child_values["binary"] = value_bits[start:end]
                    child_values["addrs"] = offset + (start // 8)
                    child_values["SECTION_OFFSET"] = offset + (start // 8)
                    self._register_data_row(child_name, child_values)

        return CompileResult("data", source, data, value_bits)

    def _register_data_row(self, name: str, values: dict[str, Any]) -> None:
        """Registra un nuevo símbolo de datos en la tabla global y sección `.data` del programa.

        Args:
            name: Nombre del símbolo.
            values: Atributos y metadatos del símbolo de datos.
        """
        row = TableRow(name=name, values=values, line=0, section=".data")
        self.program.objects[name] = row
        table = self.program.tables.get(".data")
        if table is not None:
            table.rows[name] = row

    def _register_memory_region(self, region: MemoryRegion) -> None:
        """Registra una región de memoria (stack o heap) dentro del AST y su respectiva tabla global.

        Args:
            region: Objeto de tipo MemoryRegion que encapsula la definición.
        """
        section_name = f".{region.kind}s"
        table = self.program.tables.get(section_name)
        if table is None:
            fields = ["NAME", "TYPE", "COUNT", "SECTION", "ALIGN", "FILL"]
            table = Table(section=section_name, fields=fields)
            self.program.tables[section_name] = table

        row = TableRow(name=region.name, values=region.values, line=region.line or 0, section=section_name)
        table.rows[region.name] = row
        self.program.objects[region.name] = row
        self.program.memory.add(region)

    def _rule(self, rule_name: str) -> Statement | None:
        """Busca y retorna la declaración de regla correspondiente en la sección `.rules`.

        Args:
            rule_name: Nombre de la regla del ISA.

        Returns:
            El nodo Statement de la regla, o None si no se encuentra.
        """
        rules = self.program.section(".rules")
        if rules is None:
            return None
        return next((stmt for stmt in rules.statements if stmt.name == rule_name), None)

    def _match_rule(self, rule_name: str, tokens: list[str]) -> tuple[dict[str, OperandValue], int]:
        """Compara y mapea tokens de ensamblador con la plantilla de operandos exigida por una regla.

        Args:
            rule_name: Nombre de la regla a emparejar.
            tokens: Lista de tokens proporcionados en la instrucción del ensamblador.

        Returns:
            Una tupla con el diccionario de operandos enlazados (bindings) y la cantidad de tokens consumidos.
        """
        exprs = self.program.codegen.expressions_by_rule.get(rule_name, [])
        bindings: dict[str, OperandValue] = {}
        index = 0

        for expr in exprs:
            if not expr.elements:
                continue
            kind = expr.elements[0]

            if kind == "need_literal":
                if index >= len(tokens):
                    raise PackError(f'se esperaba literal "{expr.elements[1]}"')
                expected = str(expr.elements[1])
                got = tokens[index]
                if got != expected:
                    raise PackError(f'se esperaba literal "{expected}", se encontró "{got}"')
                index += 1
                continue

            if kind == "need":
                if index >= len(tokens):
                    raise PackError("faltan operandos para la regla")
                valid_types = list(expr.elements[1])
                target = str(expr.elements[2])
                bindings[target] = self._resolve_operand(tokens[index], valid_types, rule_name)
                index += 1
                continue

        return bindings, index

    def _resolve_operand(self, token: str, valid_types: list[Any], rule_name: str) -> OperandValue:
        """Resuelve semánticamente un token de operando detectando su tipo exacto.

        Detecta si el token es un registro, un tipo del ISA, un valor inmediato,
        una región de memoria, una etiqueta o un símbolo.

        Args:
            token: Cadena de texto del operando.
            valid_types: Tipos de operandos esperados/permitidos por la regla.
            rule_name: Nombre de la regla del ISA de origen.

        Returns:
            Un objeto OperandValue con los metadatos y estado del operando.
        """
        valid_names = {str(item) for item in valid_types}

        reg = self._find_register(token)
        if reg is not None:
            priv = "register" if reg.is_parent else "subregister"
            allowed = (priv == "register" and ".regs" in valid_names) or (priv == "subregister" and ".regs.subs" in valid_names)
            if allowed:
                info = TypeInfo(reg.values.copy())
                info.setdefault("NAME", reg.name)
                info["NAME"] = reg.name
                info["bits"] = reg.bits
                info["PRIVTYPE"] = priv
                return OperandValue(name=token, type=info, resolved=True)

        if "TYPE" in valid_names:
            type_operand = self._resolve_type_operand(token)
            if type_operand is not None:
                return type_operand

        if "VALUE" in valid_names:
            value_operand = self._resolve_value_operand(token)
            if value_operand is not None:
                return value_operand

        if {"STACK", "HEAP", "MEMORY"} & valid_names:
            memory_operand = self._resolve_memory_operand(token, valid_names, rule_name)
            if memory_operand is not None:
                return memory_operand

        if "SYMBOL" in valid_names:
            row = self.program.objects.get(token)
            if row is not None and (row.section == ".data" or row.values.get("PRIVTYPE") in {"stack", "heap"}):
                info = TypeInfo(row.values.copy())
                info.setdefault("NAME", row.name)
                info.setdefault("PRIVTYPE", "symbol" if row.section == ".data" else row.values.get("PRIVTYPE"))
                ph = Placeholder(target=token, kind="symbol", reason="símbolo diferido", rule_name=rule_name)
                return OperandValue(name=token, type=info, resolved=False, placeholder=ph)

            ph = Placeholder(target=token, kind="symbol", reason="símbolo no resuelto", rule_name=rule_name)
            info = TypeInfo({"NAME": token, "PRIVTYPE": "symbol", "bits": None})
            return OperandValue(name=token, type=info, resolved=False, placeholder=ph)

        if "LABEL" in valid_names:
            if token in self.labels:
                info = TypeInfo({"NAME": token, "PRIVTYPE": "label", "addrs": self.labels[token], "bits": None})
                return OperandValue(name=token, type=info, resolved=True)
            ph = Placeholder(target=token, kind="label", reason="etiqueta no resuelta", rule_name=rule_name)
            info = TypeInfo({"NAME": token, "PRIVTYPE": "label", "bits": None})
            return OperandValue(name=token, type=info, resolved=False, placeholder=ph)

        ph = Placeholder(target=token, kind="unknown", reason="operando no conocido", rule_name=rule_name)
        info = TypeInfo({"NAME": token, "PRIVTYPE": "unknown", "bits": None})
        return OperandValue(name=token, type=info, resolved=False, placeholder=ph)

    def _find_register(self, token: str):
        """Busca un registro en el programa a través de su nombre o alias.

        Args:
            token: Nombre o alias del registro.

        Returns:
            El objeto registro correspondiente, o None si no se encuentra.
        """
        return next((r for r in self.program.regs.registers if r.name == token or r.alias == token), None)

    def _resolve_type_operand(self, token: str) -> OperandValue | None:
        """Intenta resolver el token como un operando de definición de tipo.

        Args:
            token: Token a analizar.

        Returns:
            OperandValue si es un tipo válido, o None en caso contrario.
        """
        parsed = _parse_type_token(token, self.program)
        if parsed is None:
            return None
        definition, requested_size, dimensions = parsed
        info = TypeInfo(definition.values.copy())
        info["NAME"] = definition.name
        info["TYPE"] = "TYPE"
        info["PRIVTYPE"] = "type"
        info["raw"] = token
        info["SIZE"] = requested_size if requested_size is not None else definition.size
        info["size"] = requested_size if requested_size is not None else definition.size
        if requested_size is not None:
            info["bits"] = requested_size
        elif definition.bits is not None:
            info["bits"] = definition.bits
        if dimensions:
            info["dimensions"] = dimensions
        return OperandValue(name=token, type=info, resolved=True)

    def _resolve_value_operand(self, token: str) -> OperandValue | None:
        """Intenta resolver el token como un operando de valor numérico inmediato.

        Args:
            token: Token a analizar.

        Returns:
            OperandValue si es un valor inmediato numérico válido, o None en caso contrario.
        """
        value = _parse_immediate_value(token, allow_string=False)
        if value is None:
            return None
        info = TypeInfo({
            "NAME": token,
            "TYPE": "VALUE",
            "PRIVTYPE": "value",
            "raw": value["raw"],
            "size": value["size"],
            "bits": value["size"],
            "binary": value["binary"],
            "value": value.get("value"),
        })
        return OperandValue(name=token, type=info, resolved=True)

    def _resolve_memory_operand(self, token: str, valid_names: set[str], rule_name: str) -> OperandValue | None:
        """Intenta resolver el token como un operando de región de memoria del AST.

        Args:
            token: Token a analizar.
            valid_names: Conjunto de tipos esperados de operando.
            rule_name: Nombre de la regla origen.

        Returns:
            OperandValue si se trata de una región de memoria válida, o None.
        """
        region = self.program.memory.get(token)
        if region is None:
            return None
        if "MEMORY" not in valid_names:
            if region.kind == "stack" and "STACK" not in valid_names:
                return None
            if region.kind == "heap" and "HEAP" not in valid_names:
                return None

        info = TypeInfo(region.values.copy())
        info.setdefault("NAME", region.name)
        info.setdefault("PRIVTYPE", region.kind)
        ph = Placeholder(target=token, kind=region.kind, reason=f"{region.kind} diferido", rule_name=rule_name)
        return OperandValue(name=token, type=info, resolved=False, placeholder=ph)

    def _execute_rule_body(self, rule_name: str, runtime: _Runtime) -> None:
        """Ejecuta secuencialmente el cuerpo del bloque AST perteneciente a una regla.

        Args:
            rule_name: Nombre de la regla a ejecutar.
            runtime: Entorno de ejecución y estado de compilación dinámico.
        """
        if rule_name in runtime.stack:
            chain = " -> ".join(runtime.stack + [rule_name])
            raise PackError(f"call recursivo detectado: {chain}")
        rule = self._rule(rule_name)
        if rule is None:
            raise PackError(f'regla desconocida "{rule_name}"')
        runtime.stack.append(rule_name)
        try:
            self._execute_statements(rule.children, runtime, rule_name)
        finally:
            runtime.stack.pop()

    def _execute_statements(self, stmts: list[Statement], runtime: _Runtime, rule_name: str) -> None:
        """Evalúa una lista de sentencias/comandos DSL dentro de un contexto de ejecución.

        Args:
            stmts: Lista de sentencias AST a ejecutar.
            runtime: Entorno de ejecución dinámico.
            rule_name: Nombre de la regla origen en ejecución.
        """
        index = 0
        while index < len(stmts):
            stmt = stmts[index]

            if stmt.name == "need":
                index += 1
                continue

            if stmt.name == "end_instruction":
                runtime.expressions.append(Expr(["end_instruction"]))
                raise _EndInstruction()

            if stmt.name == "ON":
                index = self._execute_on_off(stmts, index, runtime, rule_name)
                continue

            if stmt.name == "OFF":
                index += 1
                continue

            if stmt.name == "switch":
                self._execute_switch(stmt, runtime, rule_name)
                index += 1
                continue

            if stmt.name == "case":
                raise PackError("case solo puede ejecutarse dentro de switch")

            if stmt.name in self.plugins:
                under_call = len(runtime.stack) > 1
                res = self._run_plugin(stmt, rule_name, under_call=under_call)
                self._execute_result(res, runtime, rule_name)
                index += 1
                continue

            ph = Placeholder(
                target=stmt.name,
                kind="instruction",
                reason="instrucción no conocida por el compiler",
                rule_name=rule_name,
                line=stmt.line,
            )
            runtime.placeholders.append(ph)
            runtime.expressions.append(Expr(["placeholder", ph]))
            index += 1

    def _execute_on_off(self, stmts: list[Statement], index: int, runtime: _Runtime, rule_name: str) -> int:
        stmt = stmts[index]
        off_stmt = stmts[index + 1] if index + 1 < len(stmts) and stmts[index + 1].name == "OFF" else None
        next_index = index + 2 if off_stmt is not None else index + 1

        condition = self._eval_condition(stmt, runtime, rule_name)
        if isinstance(condition, Placeholder):
            runtime.placeholders.append(condition)
            runtime.expressions.append(Expr(["placeholder", condition]))
            return next_index

        if condition:
            self._execute_statements(stmt.children, runtime, rule_name)
        elif off_stmt is not None:
            self._execute_statements(off_stmt.children, runtime, rule_name)
        return next_index

    def _eval_condition(self, stmt: Statement, runtime: _Runtime, rule_name: str) -> bool | Placeholder:
        tokens = self._condition_tokens(stmt)
        if not tokens:
            return True

        comparator_index = self._condition_comparator_index(tokens)
        if comparator_index is not None:
            op = tokens[comparator_index]
            left = " ".join(tokens[:comparator_index]).strip()
            right = " ".join(tokens[comparator_index + 1:]).strip()
            if not left or not right:
                raise PackError("ON tiene una comparacion incompleta", stmt.line)
            left_value = self._condition_value(left, runtime)
            right_value = self._condition_value(right, runtime)
            if isinstance(left_value, Placeholder):
                return left_value
            if isinstance(right_value, Placeholder):
                return right_value
            return self._compare_condition_values(left_value, op, right_value, stmt.line)

        expr = " ".join(tokens).strip()
        literal = self._condition_literal(expr)
        if literal is not None:
            return literal

        value = self._condition_value(expr, runtime, allow_bare_string=False)
        if isinstance(value, Placeholder):
            return value
        return self._truthy_condition(value)

    def _condition_tokens(self, stmt: Statement) -> list[str]:
        tokens = [token.value for token in stmt.args if token.value != ","]
        normalized: list[str] = []
        index = 0
        while index < len(tokens):
            current = tokens[index]
            next_value = tokens[index + 1] if index + 1 < len(tokens) else None
            if current == "=" and next_value == "=":
                normalized.append("==")
                index += 2
                continue
            if current in {"<", ">", "!"} and next_value == "=":
                normalized.append(current + "=")
                index += 2
                continue
            normalized.append(current)
            index += 1
        return normalized

    def _condition_comparator_index(self, tokens: list[str]) -> int | None:
        for index, token in enumerate(tokens):
            if token in {"==", "!=", "<", "<=", ">", ">="}:
                return index
        return None

    def _condition_value(self, expr: str, runtime: _Runtime, allow_bare_string: bool = True) -> Any:
        expr = expr.strip()
        literal = self._condition_literal(expr)
        if literal is not None:
            return literal

        if expr in runtime.bindings or ("." in expr and expr != "."):
            value = self._eval_value(expr, runtime)
            if isinstance(value, Placeholder):
                return value
            if isinstance(value, OperandValue):
                return value.type.get("value", value.type.get("binary", value.name))
            return value

        if self._looks_numeric_condition(expr, runtime):
            value = self._eval_int(expr, runtime, kind="condition")
            if not isinstance(value, Placeholder):
                return value
            if not allow_bare_string:
                return value

        if allow_bare_string:
            return expr
        return Placeholder(target=expr, kind="condition", reason="condicion ON diferida", rule_name=runtime.rule_name)

    def _looks_numeric_condition(self, expr: str, runtime: _Runtime) -> bool:
        compact = expr.strip().replace("_", "")
        if not compact:
            return False
        if compact.startswith(("0x", "0X", "0b", "0B")):
            return True
        if compact[0].isdigit():
            return True
        if any(op in expr for op in ("+", "-", "*", "/", "%", "<<", ">>", "&", "|", "^", "~", "(", ")")):
            return True
        return expr in runtime.bit_values or expr in runtime.labels or expr in self.program.vars or expr in self.program.objects

    def _condition_literal(self, expr: str) -> bool | None:
        text = expr.strip().lower()
        if text in {"true", "yes", "on", "1", "enabled"}:
            return True
        if text in {"false", "no", "off", "0", "disabled", "impossible", "never", "none", "null"}:
            return False
        return None

    def _truthy_condition(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value != 0
        if isinstance(value, OperandValue):
            return True
        if isinstance(value, str):
            literal = self._condition_literal(value)
            if literal is not None:
                return literal
            try:
                return int(value.replace("_", ""), 0) != 0
            except ValueError:
                return bool(value)
        return bool(value)

    def _compare_condition_values(self, left: Any, op: str, right: Any, line: int | None) -> bool:
        left_cmp, right_cmp = self._coerce_condition_pair(left, right)
        if op == "==":
            return left_cmp == right_cmp
        if op == "!=":
            return left_cmp != right_cmp
        if not isinstance(left_cmp, int) or not isinstance(right_cmp, int):
            raise PackError("ON solo permite < <= > >= con valores numericos", line)
        if op == "<":
            return left_cmp < right_cmp
        if op == "<=":
            return left_cmp <= right_cmp
        if op == ">":
            return left_cmp > right_cmp
        if op == ">=":
            return left_cmp >= right_cmp
        raise PackError(f"comparador ON no soportado: {op}", line)

    def _coerce_condition_pair(self, left: Any, right: Any) -> tuple[Any, Any]:
        left_int = self._condition_int(left)
        right_int = self._condition_int(right)
        if left_int is not None and right_int is not None:
            return left_int, right_int
        return str(left), str(right)

    def _condition_int(self, value: Any) -> int | None:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            text = value.strip().replace("_", "")
            try:
                return int(text, 0)
            except ValueError:
                if len(text) > 1 and all(ch in "01" for ch in text):
                    return int(text, 2)
        return None

    def _execute_switch(self, stmt: Statement, runtime: _Runtime, rule_name: str) -> None:
        """Ejecuta una sentencia condicional de tipo `switch` evaluando sus casos correspondientes.

        Args:
            stmt: Nodo AST del switch.
            runtime: Estado de compilación dinámico.
            rule_name: Nombre de la regla en ejecución.
        """
        expr = " ".join(token.value for token in stmt.args).strip()
        value = self._eval_value(expr, runtime)
        if isinstance(value, Placeholder):
            runtime.placeholders.append(value)
            runtime.expressions.append(Expr(["placeholder", value]))
            return

        expected = str(value)
        for child in stmt.children:
            if child.name != "case":
                continue
            case_value = " ".join(token.value for token in child.args).strip()
            if case_value == expected:
                self._execute_statements(child.children, runtime, rule_name)
                return

        return

    def _run_plugin(self, stmt: Statement, rule_name: str, under_call: bool = False) -> Any:
        """Invoca dinámicamente el plugin especificado por la sentencia.

        Controla si se realiza bajo el flujo de una llamada `call` de regla o la entrada
        principal a través de `_start` si estuviera definida.

        Args:
            stmt: Nodo AST que invoca el plugin.
            rule_name: Nombre de la regla actual.
            under_call: Indica si se ejecuta como resultado de un comando `call` DSL.

        Returns:
            El resultado retornado por la ejecución del plugin (generalmente objetos de tipo Expr).
        """
        mod = self.plugins[stmt.name]
        tokens = [stmt.name] + stmt.arg_values()
        Line.set_tokens(tokens)
        Line.line = stmt.line
        RuleIndicator.current = rule_name
        context = PluginContext(
            program=self.program,
            phase="compile",
            config=self.config,
            rule_name=rule_name,
            statement=stmt,
            compiler=self,
            line=stmt.line,
        )
        try:
            if hasattr(mod, "set_context"):
                mod.set_context(context)
            setattr(mod, "CONTEXT", context)
            if under_call:
                res = mod.main()
            elif hasattr(mod, "_start"):
                res = mod._start()
            else:
                res = mod.main()
            if isinstance(res, Err):
                raise PackError(f"Plugin {stmt.name} error: {res.message}", stmt.line)
            return res
        finally:
            RuleIndicator.current = None
            Line.clear()

    def _execute_result(self, result: Any, runtime: _Runtime, rule_name: str) -> None:
        """Procesa y ejecuta de manera recursiva el resultado producido por un plugin.

        Args:
            result: Objeto o colección retornado por el plugin (puede ser Expr, list, etc.).
            runtime: Entorno de ejecución de la compilación.
            rule_name: Nombre de la regla actual.
        """
        if result is None or result == 0:
            return
        if isinstance(result, list):
            for item in result:
                self._execute_result(item, runtime, rule_name)
            return
        if isinstance(result, Expr):
            runtime.expressions.append(result)
            self._execute_expr(result, runtime, rule_name)
            return
        if isinstance(result, FlowInstruction):
            for item in result.body:
                self._execute_result(item, runtime, rule_name)
            return

    def _execute_expr(self, expr: Expr, runtime: _Runtime, rule_name: str) -> None:
        """Interpreta y ejecuta una expresión semántica DSL de RIF.

        Procesa mandatos DSL fundamentales como `fits`, `exists`, `emit`, `call`,
        comparaciones de bits, predicados de tamaño, extensiones y desplazamientos relativos.

        Args:
            expr: Objeto Expr que contiene la operación y sus argumentos.
            runtime: Estado de compilación dinámico.
            rule_name: Nombre de la regla actual.
        """
        if not expr.elements:
            return
        kind = expr.elements[0]

        if kind in {"need", "need_literal"}:
            return

        if kind == "fits":
            self._check_fits(str(expr.elements[1]), str(expr.elements[2]), runtime)
            return

        if kind == "exists":
            target = expr.elements[1]
            self._check_exists(target, runtime, rule_name)
            return

        if kind in {"emit", "emit_bits_exact"}:
            instruction = expr.elements[1]
            if isinstance(instruction, EmitInstruction):
                self._emit(instruction, runtime)
            return

        if kind == "call":
            target_rule = str(expr.elements[1])
            self._execute_rule_body(target_rule, runtime)
            return

        if kind in {"eq", "neq"}:
            self._check_bit_compare(str(expr.elements[1]), str(expr.elements[2]), kind == "eq", runtime)
            return

        if kind in {"bitsize", "bitfit"}:
            width = self._eval_int(str(expr.elements[2]), runtime, kind="number")
            if isinstance(width, Placeholder):
                runtime.placeholders.append(width)
                runtime.expressions.append(Expr(["placeholder", width]))
                return
            self._check_bit_predicate(kind, str(expr.elements[1]), width, runtime)
            return

        if kind in {"lt", "lte", "gt", "gte"}:
            self._check_numeric_compare(kind, str(expr.elements[1]), str(expr.elements[2]), runtime)
            return

        if kind in {"bitcat", "trunc", "zext", "sext"}:
            self._execute_bit_transform(expr, runtime)
            return

        if kind == "emit_address":
            self._emit_address(expr.elements[1], runtime, rule_name)
            return

        if kind == "reldis":
            width = expr.elements[3] if len(expr.elements) > 3 else None
            self._reldis(str(expr.elements[1]), str(expr.elements[2]), runtime, rule_name, width)
            return

        if kind == "align":
            n = self._eval_int(str(expr.elements[1]), runtime, kind="number")
            if isinstance(n, Placeholder):
                runtime.placeholders.append(n)
                runtime.expressions.append(Expr(["placeholder", n]))
                return
            self._align(n, runtime)
            return

        if kind == "pad":
            n = self._eval_int(str(expr.elements[1]), runtime, kind="number")
            if isinstance(n, Placeholder):
                runtime.placeholders.append(n)
                runtime.expressions.append(Expr(["placeholder", n]))
                return
            self._pad(n, runtime)
            return

        if kind == "placeholder":
            ph = expr.elements[1]
            if isinstance(ph, Placeholder):
                runtime.placeholders.append(ph)
            return

        if kind == "reloc":
            self._reloc(expr, runtime)
            return

    def _check_fits(self, left: str, right: str, runtime: _Runtime) -> None:
        """Verifica que el tamaño en bits de dos operandos coincida perfectamente.

        Lanza PackError si hay incompatibilidad de tamaño una vez resueltos.

        Args:
            left: Nombre de la variable u operando izquierdo.
            right: Nombre de la variable u operando derecho.
            runtime: Estado de compilación dinámico.
        """
        left_op = runtime.bindings.get(left)
        right_op = runtime.bindings.get(right)
        if left_op is None or right_op is None:
            ph = Placeholder(target=f"{left},{right}", kind="fits", reason="operando no ligado", rule_name=runtime.rule_name)
            runtime.placeholders.append(ph)
            return

        bits_left = left_op.type.get("bits")
        bits_right = right_op.type.get("bits")
        if bits_left is None or bits_right is None:
            ph = Placeholder(target=f"{left}.bits,{right}.bits", kind="fits", reason="tamaño diferido", rule_name=runtime.rule_name)
            runtime.placeholders.append(ph)
            return

        if int(bits_left) != int(bits_right):
            raise PackError("El operador origen no cabe en el operador destino")

    def _check_exists(self, target: Any, runtime: _Runtime, rule_name: str) -> None:
        """Verifica la existencia física de un registro o símbolo definido.

        Lanza PackError si se confirma que el registro especificado no existe en el hardware.

        Args:
            target: Identificador del operando o variable.
            runtime: Estado de compilación dinámico.
            rule_name: Nombre de la regla origen.
        """
        if isinstance(target, Placeholder):
            if target.target in runtime.bindings:
                self._check_exists(target.target, runtime, rule_name)
                return
            runtime.placeholders.append(target)
            return

        name = str(target)
        op = runtime.bindings.get(name)
        if op is None:
            runtime.placeholders.append(Placeholder(target=name, kind="unknown", reason="existencia diferida", rule_name=rule_name))
            return

        privtype = op.type.get("PRIVTYPE")
        if privtype == "symbol":
            runtime.placeholders.append(op.placeholder or Placeholder(target=op.name, kind="symbol", rule_name=rule_name))
            return

        if privtype in {"register", "subregister"}:
            if not REG.exists(op.type.get("NAME", op.name)):
                raise PackError("El registro no existe")
            return

        if not op.resolved:
            runtime.placeholders.append(op.placeholder or Placeholder(target=op.name, kind="unknown", rule_name=rule_name))

    def _check_bit_compare(self, left: str, right: str, expect_equal: bool, runtime: _Runtime) -> None:
        """Compara la equivalencia o no-equivalencia de bits entre dos operandos.

        Args:
            left: Operando izquierdo.
            right: Operando derecho.
            expect_equal: Si es True, evalúa equivalencia (eq); si es False, evalúa desigualdad (neq).
            runtime: Estado de compilación dinámico.
        """
        left_bits = self._resolve_bits_operand(left, runtime)
        right_bits = self._resolve_bits_operand(right, runtime)

        if isinstance(left_bits, Placeholder):
            runtime.placeholders.append(left_bits)
            runtime.expressions.append(Expr(["placeholder", left_bits]))
            return
        if isinstance(right_bits, Placeholder):
            runtime.placeholders.append(right_bits)
            runtime.expressions.append(Expr(["placeholder", right_bits]))
            return

        if len(left_bits) != len(right_bits):
            raise PackError("eq/neq solo compara valores del mismo tamaño")

        equal = left_bits == right_bits
        if expect_equal and not equal:
            raise PackError("eq falló: los bits no son iguales")
        if not expect_equal and equal:
            raise PackError("neq falló: los bits son iguales")

    def _check_bit_predicate(self, kind: str, value_ref: str, width: int, runtime: _Runtime) -> None:
        """Chequea predicados sobre el tamaño u holgura en bits de un operando (bitsize, bitfit).

        Lanza PackError si el predicado falla tras la resolución.

        Args:
            kind: Tipo de predicado ("bitsize" o "bitfit").
            value_ref: Nombre del operando o variable.
            width: Ancho esperado en bits.
            runtime: Estado de compilación dinámico.
        """
        if width < 0:
            raise PackError(f"{kind} no acepta tamanos negativos")

        bits = self._resolve_bits_operand(value_ref, runtime)
        if isinstance(bits, Placeholder):
            if kind == "bitfit":
                numeric = self._resolve_numeric_operand(value_ref, runtime)
                if not isinstance(numeric, Placeholder):
                    fits = numeric == 0 if width == 0 else 0 <= numeric < (1 << width)
                    if not fits:
                        raise PackError(f"bitfit fallo: {value_ref} no cabe en {width} bits")
                    return
            runtime.placeholders.append(bits)
            runtime.expressions.append(Expr(["placeholder", bits]))
            return

        if kind == "bitsize":
            if len(bits) != width:
                raise PackError(f"bitsize fallo: {value_ref} tiene {len(bits)} bits, no {width}")
            return

        value = self._resolve_bitfit_value(value_ref, bits, runtime)
        if isinstance(value, Placeholder):
            runtime.placeholders.append(value)
            runtime.expressions.append(Expr(["placeholder", value]))
            return
        fits = value == 0 if width == 0 else 0 <= value < (1 << width)
        if not fits:
            raise PackError(f"bitfit fallo: {value_ref} no cabe en {width} bits")

    def _check_numeric_compare(self, kind: str, left: str, right: str, runtime: _Runtime) -> None:
        """Realiza comparaciones numéricas (lt, lte, gt, gte) entre dos operandos.

        Args:
            kind: Tipo de comparación lógica ("lt", "lte", "gt", "gte").
            left: Operando numérico izquierdo.
            right: Operando numérico derecho.
            runtime: Estado de compilación dinámico.
        """
        left_value = self._resolve_numeric_operand(left, runtime)
        right_value = self._resolve_numeric_operand(right, runtime)

        if isinstance(left_value, Placeholder):
            runtime.placeholders.append(left_value)
            runtime.expressions.append(Expr(["placeholder", left_value]))
            return
        if isinstance(right_value, Placeholder):
            runtime.placeholders.append(right_value)
            runtime.expressions.append(Expr(["placeholder", right_value]))
            return

        ok = {
            "lt": left_value < right_value,
            "lte": left_value <= right_value,
            "gt": left_value > right_value,
            "gte": left_value >= right_value,
        }[kind]
        if not ok:
            raise PackError(f"{kind} fallo: {left_value} y {right_value} no cumplen la comparacion")

    def _execute_bit_transform(self, expr: Expr, runtime: _Runtime) -> None:
        """Ejecuta transformaciones a nivel de bit como bitcat, trunc, zext o sext.

        Args:
            expr: Expresión AST que describe la transformación.
            runtime: Estado de compilación dinámico.
        """
        kind = str(expr.elements[0])
        target = expr.elements[1]
        args = [str(item) for item in expr.elements[2:]]

        if kind == "bitcat":
            pieces: list[str] = []
            for arg in args:
                bits = self._resolve_bits_operand(arg, runtime)
                if isinstance(bits, Placeholder):
                    runtime.placeholders.append(bits)
                    runtime.expressions.append(Expr(["placeholder", bits]))
                    return
                pieces.append(bits)
            result = "".join(pieces)
        else:
            value_ref = args[0]
            width = self._eval_int(args[1], runtime, kind="number")
            if isinstance(width, Placeholder):
                runtime.placeholders.append(width)
                runtime.expressions.append(Expr(["placeholder", width]))
                return
            bits = self._resolve_bits_operand(value_ref, runtime)
            if isinstance(bits, Placeholder):
                runtime.placeholders.append(bits)
                runtime.expressions.append(Expr(["placeholder", bits]))
                return
            result = _transform_bits(kind, bits, width)

        if target is not None:
            runtime.bit_values[str(target)] = result
        runtime.expressions.append(Expr([f"{kind}_value", target, result]))

    def _eval_int(self, expr: str, runtime: _Runtime, kind: str = "number") -> int | Placeholder:
        def resolve(name: str) -> Any:
            if name in runtime.bit_values:
                return int(runtime.bit_values[name] or "0", 2)
            if name in self.program.vars:
                return int(self.program.vars[name].bits, 2)
            if name in runtime.labels:
                return runtime.labels[name]
            if "." in name:
                target, field = name.split(".", 1)
                operand = runtime.bindings.get(target)
                if operand is not None:
                    value = operand.type.get(field)
                    if value not in (None, ""):
                        return value
                row = self.program.objects.get(target)
                if row is not None:
                    value = row.values.get(field)
                    if value not in (None, ""):
                        return value
            operand = runtime.bindings.get(name)
            if operand is not None:
                value = operand.type.get("value", operand.type.get("bits"))
                if value not in (None, ""):
                    return value
            row = self.program.objects.get(name)
            if row is not None:
                value = row.values.get("addrs", row.values.get("VALUE"))
                if value not in (None, ""):
                    return value
            raise UnresolvedExpression(name)

        try:
            return eval_int_expr(expr, resolve)
        except UnresolvedExpression as exc:
            return Placeholder(target=exc.name, kind=kind, reason="expresion diferida", rule_name=runtime.rule_name)
        except SyntaxError as exc:
            raise PackError(f'expresion numerica invalida "{expr}"') from exc
        except ValueError as exc:
            raise PackError(f'expresion numerica invalida "{expr}"') from exc

    def _resolve_numeric_operand(self, name: str, runtime: _Runtime) -> int | Placeholder:
        """Resuelve un operando interpretándolo como un entero de 64 bits.

        Args:
            name: Nombre de la variable, campo o literal numérico.
            runtime: Estado de compilación dinámico.

        Returns:
            El valor numérico como int, o un objeto Placeholder si es diferido.
        """
        token = name.strip()
        if not token:
            return Placeholder(target=name, kind="number", reason="valor vacio", rule_name=runtime.rule_name)

        value = self._eval_int(token, runtime, kind="number")
        if not isinstance(value, Placeholder):
            return value
        if any(op in token for op in "+-*/%<>&|^~()"):
            return value

        if "." in token and token != ".":
            target, field = token.split(".", 1)
            operand = runtime.bindings.get(target)
            if operand is None:
                return Placeholder(target=target, field=field, kind="number", reason="operador no ligado", rule_name=runtime.rule_name)
            value = operand.type.get(field)
            if value in (None, ""):
                return Placeholder(target=target, field=field, kind=operand.type.get("PRIVTYPE", "unknown"), reason="campo diferido", rule_name=runtime.rule_name)
            try:
                return int(str(value).replace("_", ""), 0)
            except ValueError:
                return int(_value_to_bits(value), 2)

        bits = self._resolve_bits_operand(token, runtime)
        if isinstance(bits, Placeholder):
            return bits
        return int(bits or "0", 2)

    def _resolve_bitfit_value(self, name: str, bits: str, runtime: _Runtime) -> int | Placeholder:
        """Obtiene el valor numérico absoluto correspondiente a un chequeo bitfit.

        Args:
            name: Identificador del operando.
            bits: Secuencia de bits pre-resuelta del operando.
            runtime: Estado de compilación dinámico.

        Returns:
            Valor numérico entero o un Placeholder.
        """
        try:
            return int(name.strip().replace("_", ""), 0)
        except ValueError:
            pass

        return int(bits or "0", 2)

    def _resolve_bits_operand(self, name: str, runtime: _Runtime) -> str | Placeholder:
        """Obtiene la secuencia de bits (cadena binaria de ceros y unos) de un operando.

        Args:
            name: Nombre del operando o variable.
            runtime: Estado de compilación dinámico.

        Returns:
            Cadena binaria o un Placeholder si los bits aún no están disponibles.
        """
        token = name.strip()
        if not token:
            return Placeholder(target=name, kind="bits", reason="valor vacío", rule_name=runtime.rule_name)

        if all(ch in "01" for ch in token):
            return token

        if runtime.bit_values and token in runtime.bit_values:
            return runtime.bit_values[token]

        if token in self.program.vars:
            return self.program.vars[token].bits

        if "." in token and token != ".":
            target, field = token.split(".", 1)
            operand = runtime.bindings.get(target)
            if operand is None:
                return Placeholder(target=target, field=field, kind="bits", reason="operador no ligado", rule_name=runtime.rule_name)
            value = operand.type.get(field)
            if value in (None, ""):
                return Placeholder(target=target, field=field, kind=operand.type.get("PRIVTYPE", "unknown"), reason="campo diferido", rule_name=runtime.rule_name)
            return _value_to_bits(value)

        operand = runtime.bindings.get(token)
        if operand is not None:
            value = operand.type.get("binary")
            if value in (None, ""):
                if operand.placeholder is not None:
                    return Placeholder(target=operand.placeholder.target, kind=operand.placeholder.kind, reason="bits diferidos", rule_name=runtime.rule_name)
                return Placeholder(target=token, kind=operand.type.get("PRIVTYPE", "unknown"), reason="bits diferidos", rule_name=runtime.rule_name)
            return _value_to_bits(value)

        return Placeholder(target=token, kind="bits", reason="valor no resuelto", rule_name=runtime.rule_name)

    def _emit_address(self, value: Any, runtime: _Runtime, rule_name: str) -> None:
        """Emite una dirección absoluta de memoria dentro de la instrucción empaquetada como placeholder.

        Args:
            value: Nombre del símbolo, etiqueta u operando que representa la dirección.
            runtime: Estado de compilación dinámico.
            rule_name: Nombre de la regla del ISA de origen.
        """
        if isinstance(value, Placeholder):
            target = value.target
            line = value.line
        else:
            target = str(value).strip()
            line = None

        operand = runtime.bindings.get(target)
        if operand is not None:
            target = str(operand.type.get("NAME", operand.name))
            if operand.placeholder is not None:
                target = operand.placeholder.target

        runtime.placeholders.append(
            Placeholder(target=target, kind="address", reason="direccion de memoria diferida", rule_name=rule_name, line=line)
        )
        return

    def _reloc(self, expr: Expr, runtime: _Runtime) -> None:
        if len(expr.elements) < 4:
            raise PackError("reloc espera tipo, destino y ancho")
        kind = str(expr.elements[1])
        target = str(expr.elements[2])
        width = self._eval_int(str(expr.elements[3]), runtime, kind="number")
        if isinstance(width, Placeholder):
            runtime.placeholders.append(width)
            runtime.expressions.append(Expr(["placeholder", width]))
            return
        addend = 0
        if len(expr.elements) > 4 and expr.elements[4] not in (None, ""):
            addend_value = self._eval_int(str(expr.elements[4]), runtime, kind="number")
            if isinstance(addend_value, Placeholder):
                runtime.placeholders.append(addend_value)
                runtime.expressions.append(Expr(["placeholder", addend_value]))
                return
            addend = addend_value
        runtime.relocations.append(
            Relocation(
                kind=kind,
                target=target,
                offset_bits=runtime.base_offset_bits + len(runtime.bits),
                width=width,
                addend=addend,
                signed=kind in {"rel", "reldis", "relative"},
                byteorder=self._byteorder(),
                rule_name=runtime.rule_name,
                source=runtime.source,
            )
        )
        runtime.bits += "0" * width

    def _reldis(self, source: str, target: str, runtime: _Runtime, rule_name: str, width: Any = None) -> None:
        """Calcula y emite el desplazamiento de dirección relativo entre un origen y un destino.

        Args:
            source: Símbolo o posición de memoria origen.
            target: Símbolo o posición de memoria destino.
            runtime: Estado de compilación dinámico.
            rule_name: Nombre de la regla actual.
            width: Ancho en bits para empaquetar el desplazamiento (e.g., 8, 16, 32, 64).
        """
        width_int = None
        if width not in (None, ""):
            evaluated_width = self._eval_int(str(width), runtime, kind="number")
            if isinstance(evaluated_width, Placeholder):
                runtime.placeholders.append(evaluated_width)
                runtime.expressions.append(Expr(["placeholder", evaluated_width]))
                return
            width_int = evaluated_width
        if width_int is not None and width_int not in (8, 16, 32, 64):
            raise PackError("reldis solo acepta tamaños 8, 16, 32 o 64")

        start = self._memory_point(source, runtime, rule_name)
        end = self._memory_point(target, runtime, rule_name)

        if isinstance(start, Placeholder):
            relocation_offset = runtime.base_offset_bits + len(runtime.bits)
            runtime.placeholders.append(
                Placeholder(
                    target=start.target,
                    kind=start.kind,
                    field=start.field,
                    reason=start.reason,
                    rule_name=start.rule_name,
                    line=start.line,
                    width=width_int,
                )
            )
            runtime.expressions.append(Expr(["placeholder", start]))
            if width_int is not None:
                runtime.relocations.append(
                    Relocation(
                        kind="reldis",
                        target=target,
                        relative_to=source,
                        offset_bits=relocation_offset,
                        width=width_int,
                        signed=True,
                        byteorder=self._byteorder(),
                        rule_name=rule_name,
                        source=runtime.source,
                    )
                )
                runtime.bits += "0" * width_int
            return
        if isinstance(end, Placeholder):
            relocation_offset = runtime.base_offset_bits + len(runtime.bits)
            runtime.placeholders.append(
                Placeholder(
                    target=end.target,
                    kind=end.kind,
                    field=end.field,
                    reason=end.reason,
                    rule_name=end.rule_name,
                    line=end.line,
                    width=width_int,
                )
            )
            runtime.expressions.append(Expr(["placeholder", end]))
            if width_int is not None:
                runtime.relocations.append(
                    Relocation(
                        kind="reldis",
                        target=end.target,
                        relative_to=source,
                        offset_bits=relocation_offset,
                        width=width_int,
                        signed=True,
                        byteorder=self._byteorder(),
                        rule_name=rule_name,
                        source=runtime.source,
                    )
                )
                runtime.bits += "0" * width_int
            return

        origin = start
        if width_int is not None:
            origin += width_int // 8
        distance = end - origin
        runtime.expressions.append(Expr(["reldis_value", source, target, distance, width_int]))
        if width_int is not None:
            runtime.bits += _signed_int_to_bits(distance, width_int, self._byteorder())

    def _byteorder(self) -> str:
        """Determina la ordenación de bytes (endianness) configurada en el diseño del ISA.

        Returns:
            La cadena "big" o "little".
        """
        raw = self.program.world.values.get("endianness", self.program.world.values.get("endianess", "little"))
        if isinstance(raw, int):
            return "big" if raw else "little"
        text = str(raw).strip().lower()
        if text in {"big", "be", "1"}:
            return "big"
        return "little"

    def _memory_point(self, token: str, runtime: _Runtime, rule_name: str) -> int | Placeholder:
        """Calcula el offset numérico en bytes de un punto en memoria o etiqueta.

        Args:
            token: Símbolo o etiqueta a evaluar.
            runtime: Estado de compilación dinámico.
            rule_name: Nombre de la regla actual.

        Returns:
            El desplazamiento absoluto en bytes o un Placeholder si es diferido.
        """
        token = token.strip()
        if token == ".":
            current_bits = runtime.base_offset_bits + len(runtime.bits)
            if current_bits % 8 != 0:
                return Placeholder(target=".", kind="reldis", reason="posición actual no alineada a byte", rule_name=rule_name)
            return current_bits // 8

        if token in runtime.labels:
            return runtime.labels[token]

        obj = self.program.objects.get(token)
        if obj is not None:
            value = obj.values.get("addrs")
            if value not in (None, ""):
                try:
                    return int(value)
                except ValueError:
                    return Placeholder(target=token, kind="reldis", reason="dirección inválida", rule_name=rule_name)

        operand = runtime.bindings.get(token)
        if operand is not None:
            value = operand.type.get("addrs")
            if value not in (None, ""):
                try:
                    return int(value)
                except ValueError:
                    return Placeholder(target=token, kind="reldis", reason="dirección inválida", rule_name=rule_name)
            if operand.placeholder is not None:
                return Placeholder(target=operand.placeholder.target, kind="reldis", reason="dirección diferida", rule_name=rule_name)

        return Placeholder(target=token, kind="reldis", reason="etiqueta o dirección no resuelta", rule_name=rule_name)

    def _align(self, n: int, runtime: _Runtime) -> None:
        """Alinea el desplazamiento de bits de la emisión a un múltiplo de 'n' bytes.

        Rellena con ceros hasta alcanzar la frontera de alineación.

        Args:
            n: Cantidad de bytes a la cual alinear.
            runtime: Estado de compilación dinámico.
        """
        if n <= 0:
            raise PackError("align espera un número mayor que cero")
        current_bits = runtime.base_offset_bits + len(runtime.bits)
        if current_bits % 8 != 0:
            raise PackError("align requiere que la posición actual esté en límite de byte")
        current_byte = current_bits // 8
        missing = (-current_byte) % n
        if missing:
            runtime.bits += "0" * (missing * 8)

    def _pad(self, n: int, runtime: _Runtime) -> None:
        """Introduce un relleno físico de 'n' bytes con ceros en la instrucción actual.

        Args:
            n: Número de bytes de relleno.
            runtime: Estado de compilación dinámico.
        """
        if n < 0:
            raise PackError("pad no acepta números negativos")
        if n:
            runtime.bits += "0" * (n * 8)

    def _emit(self, instruction: EmitInstruction, runtime: _Runtime) -> None:
        """Concatena y añade los fragmentos (chunks) binarios de una directiva `emit` a los bits de salida.

        Args:
            instruction: Objeto EmitInstruction con los fragmentos a empaquetar.
            runtime: Estado de compilación dinámico.
        """
        bits = ""
        for chunk in instruction.chunks:
            resolved = self._resolve_chunk(chunk, runtime, instruction)
            if isinstance(resolved, Placeholder):
                runtime.placeholders.append(resolved)
                runtime.expressions.append(Expr(["placeholder", resolved]))
                continue
            bits += resolved

        if instruction.requires_byte and len(bits) % 8 != 0:
            raise PackError(f"emit produjo {len(bits)} bits; se esperaba múltiplo de 8")

        runtime.bits += bits

    def _resolve_chunk(self, chunk: EmitChunk, runtime: _Runtime, instruction: EmitInstruction) -> str | Placeholder:
        """Resuelve un único fragmento (EmitChunk) de bits o valor del operando mapeado.

        Args:
            chunk: El fragmento a resolver.
            runtime: Estado de compilación dinámico.
            instruction: Instrucción de emisión origen.

        Returns:
            Secuencia binaria en cadena de texto o un Placeholder si es diferido.
        """
        if chunk.kind in {"bits", "byte"}:
            return chunk.value

        if chunk.kind == "bits_ref":
            resolved = self._resolve_bits_operand(chunk.value, runtime)
            if isinstance(resolved, Placeholder):
                return Placeholder(
                    target=resolved.target,
                    field=resolved.field,
                    kind="emit",
                    reason=resolved.reason,
                    rule_name=runtime.rule_name,
                    line=instruction.line,
                )
            return resolved

        if chunk.kind != "placeholder":
            return Placeholder(target=chunk.value, kind="emit", reason="chunk desconocido", rule_name=runtime.rule_name, line=instruction.line)

        target = chunk.target or ""
        field = chunk.field or ""
        operand = runtime.bindings.get(target)
        if operand is None:
            return Placeholder(target=target, field=field, kind="emit", reason="operador no ligado", rule_name=runtime.rule_name, line=instruction.line)

        value = operand.type.get(field)
        if value in (None, ""):
            return Placeholder(target=target, field=field, kind=operand.type.get("PRIVTYPE", "unknown"), reason="campo diferido", rule_name=runtime.rule_name, line=instruction.line)

        return _value_to_bits(value)

    def _eval_value(self, expr: str, runtime: _Runtime) -> Any:
        """Evalúa un identificador de operando, propiedad de registro o cadena RIF DSL.

        Args:
            expr: Operación o cadena del operando.
            runtime: Estado de compilación dinámico.

        Returns:
            El valor final evaluado o un Placeholder.
        """
        expr = expr.strip()
        if "." in expr:
            target, field = expr.split(".", 1)
            operand = runtime.bindings.get(target)
            if operand is None:
                return Placeholder(target=target, field=field, kind="eval", reason="operador no ligado", rule_name=runtime.rule_name)
            value = operand.type.get(field)
            if value is None and field == "TYPE":
                value = operand.type.get("PRIVTYPE")
                if value is not None:
                    return str(value).upper()
            if value is None:
                return Placeholder(target=target, field=field, kind="eval", reason="campo no resuelto", rule_name=runtime.rule_name)
            return value
        if expr in runtime.bindings:
            return runtime.bindings[expr]
        return expr


def compile_instruction(program_or_path: Program | str | Path, source: str) -> CompileResult:
    """Función de conveniencia para compilar una sola instrucción.

    Args:
        program_or_path: Un objeto Program pre-parseado, o la ruta de archivo .pack.
        source: Línea de instrucción ensamblador.

    Returns:
        Objeto CompileResult con el binario generado y metadatos.
    """
    if isinstance(program_or_path, Program):
        compiler = Compiler(program_or_path)
    else:
        compiler = Compiler.from_file(program_or_path)
    return compiler.compile_line(source)


def _split_instruction(source: str) -> list[str]:
    """Divide una línea de instrucción en tokens léxicos respetando comillas y delimitadores.

    Args:
        source: Cadena de texto de la instrucción ensamblador.

    Returns:
        Lista de tokens resultantes.
    """
    out: list[str] = []
    current: list[str] = []
    quote = False
    escaped = False

    def push() -> None:
        if current:
            out.append("".join(current))
            current.clear()

    for ch in source.strip():
        if escaped:
            current.append(ch)
            escaped = False
            continue
        if ch == "\\" and quote:
            escaped = True
            continue
        if ch == '"':
            quote = not quote
            continue
        if quote:
            current.append(ch)
            continue
        if ch.isspace():
            push()
            continue
        if ch in {",", "=", ":"}:
            push()
            out.append(ch)
            continue
        current.append(ch)
    push()
    return out


def _strip_source_comment(raw: str) -> str:
    """Elimina los comentarios que comienzan con punto y coma (;) respetando cadenas con comillas.

    Args:
        raw: Línea de código fuente ensamblador.

    Returns:
        Línea limpia sin comentario.
    """
    quote = False
    escaped = False
    out: list[str] = []
    for ch in raw:
        if escaped:
            out.append(ch)
            escaped = False
            continue
        if ch == "\\" and quote:
            out.append(ch)
            escaped = True
            continue
        if ch == '"':
            out.append(ch)
            quote = not quote
            continue
        if ch == ";" and not quote:
            break
        out.append(ch)
    return "".join(out).rstrip()


def _label_from_line(line: str) -> str | None:
    """Determina si la línea especificada corresponde a la definición de una etiqueta.

    Args:
        line: Línea de instrucción ensamblador.

    Returns:
        Nombre de la etiqueta si se matchea el patrón (e.g., 'label:'), o None.
    """
    tokens = _split_instruction(line)
    if len(tokens) == 2 and tokens[1] == ":" and _is_label_name(tokens[0]):
        return tokens[0]
    return None


def _is_label_name(value: str) -> bool:
    """Valida si la cadena proporcionada cumple con las reglas sintácticas para nombres de etiquetas.

    Args:
        value: Cadena a validar.

    Returns:
        True si el nombre es válido, False en caso contrario.
    """
    if not value:
        return False
    if not (value[0].isalpha() or value[0] == "_"):
        return False
    return all(ch.isalnum() or ch in "_-" for ch in value)


def _transform_bits(kind: str, bits: str, width: int) -> str:
    """Aplica una transformación específica de extensión o truncamiento sobre una cadena binaria.

    Args:
        kind: Tipo de transformación ("trunc", "zext", "sext").
        bits: Cadena binaria original.
        width: Ancho objetivo en bits.

    Returns:
        Cadena binaria transformada.
    """
    if width < 0:
        raise PackError(f"{kind} no acepta tamanos negativos")

    if kind == "trunc":
        if width == 0:
            return ""
        return bits[-width:]

    if len(bits) > width:
        raise PackError(f"{kind} no puede reducir de {len(bits)} a {width} bits")

    if kind == "zext":
        return bits.rjust(width, "0")

    if kind == "sext":
        sign = bits[0] if bits else "0"
        return bits.rjust(width, sign)

    raise PackError(f"transformacion de bits desconocida: {kind}")


def _parse_type_token(token: str, program: Program) -> tuple[TypeDefinition, int | None, list[int]] | None:
    """Parseará el tipo de dato especificado en ensamblador, detectando dimensiones y tamaño total.

    Args:
        token: Token del tipo (e.g., 'u32', 'i8[10]', etc.).
        program: El AST de configuración global RIF.

    Returns:
        Tupla con la definición del tipo, el tamaño total calculado y las dimensiones si las hay, o None.
    """
    raw = token.strip()
    if not raw:
        return None

    name = raw
    dimensions: list[int] = []
    if "[" in raw and raw.endswith("]"):
        name, rest = raw.split("[", 1)
        rest = rest[:-1].strip()
        if rest:
            for item in rest.split(","):
                item = item.strip()
                if not item:
                    return None
                try:
                    dimensions.append(int(item.replace("_", ""), 0))
                except ValueError:
                    return None

    definition = program.type_defs.get(name)
    if definition is None:
        return None

    requested_size = definition.bits
    if dimensions and definition.bits is not None:
        count = 1
        for item in dimensions:
            count *= item
        requested_size = definition.bits * count
    return definition, requested_size, dimensions


def _parse_immediate_value(token: str, allow_string: bool = True) -> dict[str, Any] | None:
    """Parseará un valor numérico inmediato o literal (soporta decimal, binario 0b, hex 0x, strings).

    Args:
        token: Token del valor inmediato.
        allow_string: Indica si se permite decodificar como cadena binaria UTF-8 en caso de no ser numérico.

    Returns:
        Diccionario con la secuencia binaria calculada y metadatos, o None si es inválido.
    """
    raw = token.strip()
    if not raw:
        return None

    compact = raw.replace("_", "")
    try:
        value = int(compact, 0)
    except ValueError:
        if not allow_string:
            return None
        data = raw.encode("utf-8")
        bits = "".join(format(byte, "08b") for byte in data)
        return {"raw": raw, "value": raw, "size": len(bits), "binary": bits}

    if value < 0:
        return None

    if compact.startswith(("0b", "0B")):
        bits = compact[2:]
        if not bits or any(ch not in "01" for ch in bits):
            return None
        return {"raw": raw, "value": value, "size": len(bits), "binary": bits}

    if compact.startswith(("0x", "0X")):
        body = compact[2:]
        if not body or any(ch not in "0123456789abcdefABCDEF" for ch in body):
            return None
        width = len(body) * 4
        bits = format(value, f"0{width}b")
        return {"raw": raw, "value": value, "size": width, "binary": bits}

    width = max(1, value.bit_length())
    bits = format(value, f"0{width}b")
    return {"raw": raw, "value": value, "size": width, "binary": bits}


def _type_allows_string(type_def: TypeDefinition, program: Program) -> bool:
    """Determina si una definición de tipo específica admite la asignación directa de strings literales.

    Args:
        type_def: Estructura del tipo a evaluar.
        program: El AST de configuración global RIF.

    Returns:
        True si admite inicialización con string, False en caso contrario.
    """
    supported = program.data_definition.options.get("supportstring", [])
    if type_def.name in {str(item) for item in supported}:
        return True
    return str(type_def.values.get("string", "")).strip().lower() not in {"", "no", "false", "0"}


def _truthy(value: Any) -> bool:
    """Evalúa de forma robusta la veracidad de un valor procedente de las tablas o configuración.

    Args:
        value: Objeto a evaluar.

    Returns:
        True o False.
    """
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


def _signed_int_to_bits(value: int, width: int, byteorder: str) -> str:
    """Convierte un entero con signo a una cadena binaria de ancho fijo aplicando orden de bytes.

    Args:
        value: Entero a codificar.
        width: Cantidad de bits final (8, 16, 32, 64).
        byteorder: Orden de bytes ("big" o "little").

    Returns:
        Secuencia de bits.
    """
    minimum = -(1 << (width - 1))
    maximum = (1 << (width - 1)) - 1
    if value < minimum or value > maximum:
        raise PackError(f"reldis {value} no cabe en {width} bits")
    encoded = value.to_bytes(width // 8, byteorder=byteorder, signed=True)
    return "".join(format(byte, "08b") for byte in encoded)


def _value_to_bits(value: Any) -> str:
    """Convierte un valor genérico o número no signado a su correspondiente representación de bits.

    Args:
        value: Valor de cualquier tipo.

    Returns:
        Cadena binaria.
    """
    if isinstance(value, int):
        if value < 0:
            raise PackError("no se pueden emitir enteros negativos como bits")
        width = max(1, value.bit_length())
        return format(value, f"0{width}b")

    text = str(value).strip()
    if not text:
        raise PackError("campo vacío no puede convertirse a bits")
    if all(ch in "01" for ch in text):
        return text
    if text.startswith(("0b", "0B")):
        body = text[2:]
        if body and all(ch in "01" for ch in body):
            return body
    if text.startswith(("0x", "0X")):
        value_int = int(text, 16)
        width = max(4, ((value_int.bit_length() + 3) // 4) * 4)
        return format(value_int, f"0{width}b")
    raise PackError(f'campo "{text}" no es binario')
