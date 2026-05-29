from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

from .errors import PackError
from .expr import UnresolvedExpression, eval_int_expr
from .lexer import Lexer
from .models import BinaryLinkResult, HeaderBlock, LinkBlock, MemoryRegion, PackedResult, PackerConfig, PluginContext, Program, TableRow, Placeholder
from .parser import Parser, parse_packer_config, run_precompilers


class Linker:
    """Linker genérico impulsado y gobernado por la configuración `.pack`.

    Este linker no conoce nombres de sección específicos de una arquitectura particular.
    En su lugar, infiere qué fragmentos de código son legales y válidos mediante las
    directivas `definesec`, `setpre` y `needsect`, fusiona los payloads seleccionados,
    y re-parsea la fuente ensamblada final de forma que las fases subsiguientes
    del compilador operen en el programa consolidado.
    """

    def __init__(self, source_path: str | Path):
        """Inicializa el Linker con la ruta al archivo fuente principal.

        Args:
            source_path: Ruta al archivo fuente original.
        """
        self.source_path = Path(source_path)

    def link(self, output_path: str | Path | None = None, write: bool = True) -> PackedResult:
        """Realiza el proceso de enlace (link) fusionando fragmentos externos al archivo fuente.

        Args:
            output_path: Ruta opcional de salida para escribir el código fusionado.
            write: Si es True, guarda el archivo en disco.

        Returns:
            Un objeto PackedResult con la información del enlace y el programa parseado final.
        """
        if not self.source_path.exists():
            raise PackError(f"source file does not exist: {self.source_path}")

        source = self.source_path.read_text(encoding="utf-8")
        initial_program = Parser(source, self.source_path).parse()
        link_config = parse_packer_config(initial_program)

        output = Path(output_path) if output_path is not None else self.source_path.with_name(self.source_path.name + ".temp")

        fragments: list[Path] = []
        linked_source = source
        if link_config.enabled and link_config.fsystem != 0:
            fragments = self._find_fragments(link_config, initial_program)
            linked_source = self._merge(source, link_config, fragments)

        if write:
            output.write_text(linked_source, encoding="utf-8")

        linked_program = Parser(linked_source, output).parse()
        final_config = parse_packer_config(linked_program)
        return PackedResult(
            source_path=self.source_path,
            output_path=output,
            fragments=fragments,
            program=linked_program,
            config=final_config,
            linked_source=linked_source,
            initial_program=initial_program,
        )

    def _find_fragments(self, config: PackerConfig, program: Program) -> list[Path]:
        """Localiza en el filesystem los fragmentos de código válidos que deben ser enlazados.

        Busca archivos en el directorio del fuente que sigan el patrón '{fuente}.{subprefijo}{extensión}'.

        Args:
            config: Configuración de empaquetado y enlazado.
            program: AST del programa inicial.

        Returns:
            Lista de rutas de archivos de fragmentos candidatos válidos.
        """
        if config.fsystem != 1 or config.subpre is None:
            return []

        base = self.source_path.stem
        root = self.source_path.parent
        pattern = f"{base}.*{config.ext}"
        candidates = sorted(root.rglob(pattern))

        out: list[Path] = []
        for path in candidates:
            if path.resolve() == self.source_path.resolve():
                continue
            if path.name == self.source_path.name + ".temp":
                continue
            if path.suffix != config.ext:
                continue

            subprefix = self._subprefix(path, base, config.ext)
            if subprefix is None:
                continue
            if config.subpre != "*" and subprefix != config.subpre:
                continue
            if subprefix not in config.prefix_to_section:
                continue

            target = config.prefix_to_section[subprefix]
            if config.defined_sections and target not in config.defined_sections:
                continue
            if subprefix in config.required_prefixes and not program.has_section(target):
                continue

            out.append(path)
        return out

    def _subprefix(self, path: Path, base: str, ext: str) -> str | None:
        """Determina y valida el subprefijo del nombre de un archivo de fragmento.

        Args:
            path: Ruta del fragmento.
            base: Nombre base del archivo principal.
            ext: Extensión de archivos esperada.

        Returns:
            El subprefijo como cadena si es válido, o None en caso contrario.
        """
        name = path.name
        prefix = f"{base}."
        if not name.startswith(prefix) or not name.endswith(ext):
            return None
        middle = name[len(prefix):-len(ext)]
        if not middle or "." in middle:
            return None
        return middle

    def _merge(self, source: str, config: PackerConfig, fragments: list[Path]) -> str:
        """Fusiona el contenido de todos los fragmentos con el archivo fuente base.

        Args:
            source: Contenido original del archivo principal.
            config: Configuración del empaquetador.
            fragments: Lista de rutas de fragmentos a mezclar.

        Returns:
            Código fuente unificado y enlazado.
        """
        buckets: dict[str, list[str]] = {}
        base = self.source_path.stem

        for fragment in fragments:
            subprefix = self._subprefix(fragment, base, config.ext)
            if subprefix is None:
                continue
            target = config.prefix_to_section.get(subprefix)
            if target is None:
                continue

            body = self._fragment_body(fragment, target)
            if body.strip():
                buckets.setdefault(target, []).append(body.rstrip())

        if not buckets:
            return source

        return self._append_to_sections(source, config, buckets)

    def _fragment_body(self, path: Path, target: str) -> str:
        """Extrae el contenido pertinente de un archivo de fragmento.

        Si el fragmento contiene declaraciones de secciones explícitas, aísla únicamente
        el cuerpo de la sección destino.

        Args:
            path: Ruta del archivo de fragmento.
            target: Nombre de la sección destino.

        Returns:
            Texto con el cuerpo del fragmento extraído.
        """
        text = path.read_text(encoding="utf-8")

        if not _contains_section_header(text):
            return text

        parsed = Parser(text, path).parse()
        section = parsed.section(target)
        if section is None:
            return ""
        return "\n".join(raw for _, raw in section.body_lines)

    def _append_to_sections(
        self,
        source: str,
        config: PackerConfig,
        buckets: dict[str, list[str]],
    ) -> str:
        """Inserta los fragmentos agrupados en sus correspondientes secciones dentro del código fuente.

        Args:
            source: Código fuente original.
            config: Configuración del empaquetador.
            buckets: Diccionario de fragmentos agrupados por sección destino.

        Returns:
            Código fuente final con los fragmentos insertados en los límites de sección.
        """
        lines = source.splitlines()
        ranges = _section_ranges(lines)
        output_lines = list(lines)

        sort_key = lambda item: ranges.get(item[0], (10**12, 10**12))[1]
        for section, fragments in sorted(buckets.items(), key=sort_key, reverse=True):
            if section in ranges:
                _, end = ranges[section]
                output_lines[end:end] = [""] + _flat_fragments(fragments)
            else:
                header = _section_header(config, section)
                output_lines.extend(["", header])
                output_lines.extend(_flat_fragments(fragments))

        return "\n".join(output_lines).rstrip() + "\n"

    def build_binary(
        self,
        source: str = "",
        output_path: str | Path | None = None,
        write: bool = True,
    ) -> BinaryLinkResult:
        """Enlaza las fuentes y genera directamente el archivo ejecutable binario.

        Args:
            source: Código ensamblador complementario opcional a compilar.
            output_path: Ruta destino para escribir los bytes.
            write: Si es True, escribe los bytes del binario en el archivo.

        Returns:
            El resultado detallado BinaryLinkResult del enlazado binario.
        """
        linked = self.link(write=False)
        return BinaryLinker(linked.program).build(source, output_path, write=write)


class BinaryLinker:
    """Linker binario genérico para programas RIF parseados.

    El núcleo del linker comprende primitivas de diseño y ordenación neutras
    (`link:offset`, `link:size`, `link:count`, `link:each`, etc.). Nombres de
    propiedades específicos de cada arquitectura (como `amd64:entry`) se delegan
    a ganchos (hooks) opcionales de compiladores plugins o se registran como placeholders.
    """

    def __init__(self, program: Program):
        """Inicializa el linker binario a partir del AST de un programa parseado.

        Args:
            program: Estructura de datos AST del programa.
        """
        self.program = program
        self.config = parse_packer_config(program)
        run_precompilers(program, self.config)
        self.plugin_modules = self._load_plugin_compilers()
        self.blocks: dict[str, LinkBlock] = {}
        self.placeholders: list[Placeholder] = []
        self.relocations: list[Any] = []

    def build(self, source: str = "", output_path: str | Path | None = None, write: bool = True) -> BinaryLinkResult:
        """Construye y enlaza la imagen binaria final a partir del AST del programa y código fuente adicional.

        Lleva a cabo la planeación de bloques, asignación recursiva de offsets físicos/virtuales,
        reubicación de símbolos de datos, materialización de cabeceras estructuradas y ensamblado.

        Args:
            source: Código ensamblador fuente adicional para compilar y linkear.
            output_path: Ruta del archivo binario de salida.
            write: Si es True, guarda el binario compilado en disco.

        Returns:
            El resultado del enlazado binario BinaryLinkResult.
        """
        self.placeholders.clear()
        self.relocations.clear()
        blocks = self._plan_blocks(source)
        self._assign_offsets(blocks)
        self._relocate_source_data(blocks)
        self._relocate_memory_regions(blocks)
        self._materialize_headers(blocks)
        self._assign_offsets(blocks)
        self._relocate_source_data(blocks)
        self._relocate_memory_regions(blocks)
        self._materialize_headers(blocks)

        data = self._assemble_data(blocks)
        result = BinaryLinkResult(self.program, blocks, data, list(self.placeholders), list(self.relocations))

        if write and output_path is not None:
            Path(output_path).write_bytes(result.data)

        return result

    def _assemble_data(self, blocks: list[LinkBlock]) -> bytes:
        """Ensambla secuencialmente la lista de bloques de enlace en una cadena de bytes física continua.

        Args:
            blocks: Lista de bloques de enlace planeados.

        Returns:
            bytes correspondientes al contenido binario completo.
        """
        out = bytearray()
        for block in blocks:
            if block.kind == "nobits" or not block.data:
                continue
            if len(out) < block.physical_offset:
                out.extend(b"\x00" * (block.physical_offset - len(out)))
            out[block.physical_offset:block.physical_offset + len(block.data)] = block.data
        return bytes(out)

    def _load_plugin_compilers(self) -> dict[str, Any]:
        """Carga dinámicamente los módulos compiladores de plugins declarados en el .pack.

        Returns:
            Diccionario de módulos de plugins cargados por nombre.
        """
        loaded: dict[str, Any] = {}
        if not self.config.plugins and not self.config.precompilers:
            return loaded

        base_dir = Path.cwd()
        if self.program.source_path:
            base_dir = Path(self.program.source_path).parent
        plugins_root = base_dir / "plugins"

        for plugin_name in dict.fromkeys([*self.config.plugins, *self.config.precompilers]):
            path = plugins_root / plugin_name / "compiler.py"
            if not path.exists():
                continue
            module_name = f"rif.linker.{plugin_name}.compiler"
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = mod
            spec.loader.exec_module(mod)
            loaded[plugin_name] = mod
        return loaded

    def _plan_blocks(self, source: str) -> list[LinkBlock]:
        """Planifica la disposición secuencial de secciones de cabecera, código y datos.

        Args:
            source: Código fuente ensamblador complementario.

        Returns:
            Lista de LinkBlocks inicializados de acuerdo al diseño del programa.
        """
        blocks: list[LinkBlock] = []
        source_sections = self._compile_source(source) if source.strip() else {}

        for name in self._top_header_names():
            header = self.program.headers.blocks[name]
            data = self._initial_header_data(header)
            block = LinkBlock(name=name, kind="header", data=data, physical_size=len(data), virtual_size=len(data))
            self.blocks[name] = block
            blocks.append(block)

        table = self.program.tables.get(".sections")
        if table is not None:
            for row in sorted(table.rows.values(), key=_row_order):
                emit = str(row.values.get("emit", "yes")).strip().lower()
                kind = str(row.values.get("type", "section")).strip().lower()
                emit_physical = emit not in {"no", "false", "0"} and kind != "nobits"
                data, section_virtual_size = self._section_payload(
                    row,
                    source_sections if emit_physical else {},
                    kind,
                    emit_physical,
                )
                align = _intish(row.values.get("align", 1), 1)
                valign = _intish(row.values.get("valign", align), align)
                block = LinkBlock(
                    name=row.name,
                    kind="nobits" if kind == "nobits" else "section",
                    data=data,
                    physical_size=len(data) if kind != "nobits" else 0,
                    virtual_size=section_virtual_size,
                    align=align,
                    row=row,
                )
                block.virtual_offset = 0
                block.align = max(1, align)
                block.row.values.setdefault("psize", block.physical_size)
                block.row.values.setdefault("vsize", block.virtual_size)
                self.blocks[block.name] = block
                blocks.append(block)

        return blocks

    def _compile_source(self, source: str) -> dict[str, bytes]:
        """Compila dinámicamente código fuente adicional usando el compilador de RIF.

        Args:
            source: Líneas de ensamblador complementarias.

        Returns:
            Diccionario que asocia el nombre de la sección con sus bytes compilados.
        """
        from .compiler import Compiler

        results = Compiler(self.program).compile_lines(source)
        missing = [ph.name for result in results for ph in result.placeholders]
        self.relocations.extend(relocation for result in results for relocation in result.relocations)
        if missing:
            raise PackError("no se puede linkear source con placeholders: " + ", ".join(missing))

        code_section = self._payload_section("code")
        data_section = self._payload_section("data")
        sections: dict[str, bytearray] = {code_section: bytearray(), data_section: bytearray()}
        data_offsets: dict[str, int] = {data_section: 0}
        for result in results:
            payload = result.data or b""
            if result.rule_name == "data":
                name = _source_symbol_name(result.source)
                if name is not None:
                    offset = data_offsets.setdefault(data_section, 0)
                    self._update_source_data_offsets(name, data_section, offset)
                sections[data_section].extend(payload)
                data_offsets[data_section] = data_offsets.get(data_section, 0) + len(payload)
            elif result.rule_name in {"stack", "heap"}:
                continue
            else:
                sections[code_section].extend(payload)

        return {name: bytes(data) for name, data in sections.items() if data}

    def _section_payload(self, row: TableRow, source_sections: dict[str, bytes], kind: str, emit_physical: bool) -> tuple[bytes, int]:
        """Calcula el payload (datos físicos y tamaño virtual) perteneciente a una sección.

        Args:
            row: Fila del objeto sección en la tabla.
            source_sections: Secciones de datos/código compiladas.
            kind: Tipo de sección.
            emit_physical: Si es True, indica que emite bytes reales.

        Returns:
            Una tupla con los bytes físicos de la sección y su tamaño virtual total.
        """
        static = _bytes_from_hexish(row.values.get("raw", row.values.get("hex", ""))) if emit_physical else b""
        compiled = source_sections.get(row.name, b"")
        if compiled:
            self._place_source_data(row.name, len(static))
        data = bytearray(static + compiled)
        base_size = len(data)
        memory_data, memory_virtual = self._memory_payload(row.name, base_size, emit_physical=emit_physical)
        if emit_physical:
            data.extend(memory_data)
        return bytes(data), max(len(data), base_size + memory_virtual)

    def _memory_payload(self, section_name: str, start_offset: int, emit_physical: bool) -> tuple[bytes, int]:
        """Calcula y rellena las regiones de memoria (stack o heap) asignadas a una sección.

        Args:
            section_name: Nombre de la sección.
            start_offset: Desplazamiento inicial en bytes.
            emit_physical: Si es True, rellena físicamente las regiones de memoria.

        Returns:
            Tupla con los bytes de relleno físico y el tamaño virtual neto de la memoria.
        """
        out = bytearray()
        current = start_offset
        for region_name in self.program.memory.by_section.get(section_name, []):
            region = self.program.memory.regions[region_name]
            aligned = _align_to(current, max(1, region.align))
            gap = aligned - current
            if emit_physical and gap:
                out.extend(b"\x00" * gap)

            row = self.program.objects.get(region.name)
            if row is not None:
                row.values["SECTION_OFFSET"] = aligned
                row.values["psize"] = region.bytes if emit_physical else 0
                row.values["vsize"] = region.bytes
                row.values["addrs"] = aligned
                row.values["paddrs"] = aligned if emit_physical else None
            region.values["SECTION_OFFSET"] = aligned
            region.values["psize"] = region.bytes if emit_physical else 0
            region.values["vsize"] = region.bytes

            if emit_physical and region.bytes:
                fill = _bytes_from_fill(region.fill) or b"\x00"
                out.extend((fill * ((region.bytes // len(fill)) + 1))[:region.bytes])
            current = aligned + region.bytes
        return bytes(out), current - start_offset

    def _payload_section(self, payload: str) -> str:
        """Determina a qué sección del layout corresponde un tipo de payload (código o datos).

        Args:
            payload: El tipo de payload ("code" o "data").

        Returns:
            Nombre de la sección correspondiente.
        """
        table = self.program.tables.get(".sections")
        if table is None or not table.rows:
            return ".text" if payload == "code" else ".data"

        rows = list(table.rows.values())
        if payload == "code":
            for row in rows:
                kind = str(row.values.get("type", "")).strip().lower()
                perms = str(row.values.get("perms", "")).strip().lower()
                if kind in {"code", "text"} or "x" in perms or row.name in {".text", "text"}:
                    return row.name
        else:
            for row in rows:
                kind = str(row.values.get("type", "")).strip().lower()
                perms = str(row.values.get("perms", "")).strip().lower()
                if kind == "data" or row.name in {".data", "data"} or ("w" in perms and "x" not in perms):
                    return row.name

        return rows[0].name

    def _update_source_data_offsets(self, name: str, section: str, data_offset: int) -> None:
        """Actualiza y alinea los desplazamientos de símbolos de datos del código compilado dinámicamente.

        Args:
            name: Nombre del símbolo base.
            section: Sección destino.
            data_offset: Desplazamiento actual de inserción.
        """
        row = self.program.objects.get(name)
        if row is None or not row.values.get("SOURCE_DATA"):
            return
        current = _intish(row.values.get("SECTION_OFFSET", row.values.get("addrs", 0)), 0)
        delta = data_offset - current
        for candidate in self.program.objects.values():
            if candidate.section != ".data" or not candidate.values.get("SOURCE_DATA"):
                continue
            if candidate.name != name and candidate.values.get("parent") != name:
                continue
            rel = _intish(candidate.values.get("SECTION_OFFSET", candidate.values.get("addrs", 0)), 0)
            candidate.values["SECTION"] = section
            candidate.values["COMPILED_SECTION_OFFSET"] = rel + delta
            candidate.values["SECTION_OFFSET"] = rel + delta
            candidate.values["addrs"] = rel + delta

    def _place_source_data(self, section: str, base_offset: int) -> None:
        """Ubica los datos estáticos compilados en sus respectivos offsets relativos.

        Args:
            section: Nombre de la sección.
            base_offset: Desplazamiento base a aplicar.
        """
        for row in self.program.objects.values():
            if row.section != ".data" or not row.values.get("SOURCE_DATA"):
                continue
            if row.values.get("SECTION") != section:
                continue
            compiled_offset = _intish(row.values.get("COMPILED_SECTION_OFFSET", row.values.get("SECTION_OFFSET", 0)), 0)
            row.values["SECTION_OFFSET"] = base_offset + compiled_offset
            row.values["addrs"] = row.values["SECTION_OFFSET"]

    def _top_header_names(self) -> list[str]:
        """Retorna la lista ordenada de bloques de cabecera a generar.

        Returns:
            Lista de nombres de bloques de cabecera.
        """
        table = self.program.tables.get(".headers")
        if table is not None:
            return list(table.rows)
        return [name for name in self.program.headers.order if self.program.headers.blocks[name].size is not None]

    def _initial_header_data(self, header: HeaderBlock) -> bytes:
        """Crea el buffer de bytes inicial de una cabecera rellenándola con su patrón correspondiente.

        Args:
            header: Objeto cabecera.

        Returns:
            Buffer de bytes inicial de la cabecera.
        """
        size = self._header_size(header)
        fill = _bytes_from_fill(header.fill)
        if not fill:
            fill = b"\x00"
        data = bytearray((fill * ((size // len(fill)) + 1))[:size])
        raw = _bytes_from_hexish(header.hex)
        data[:len(raw)] = raw[:size]
        return bytes(data)

    def _header_size(self, header: HeaderBlock) -> int:
        """Calcula el tamaño final en bytes que requiere una sección de cabecera.

        Args:
            header: Estructura del bloque de cabecera.

        Returns:
            Ancho físico neto en bytes.
        """
        if header.size not in (None, "", "*"):
            return _intish(header.size, 0)

        for stmt in header.statements:
            args = stmt.arg_values()
            if stmt.name == "link:each" and len(args) >= 2:
                collection = self._collection_rows(args[0])
                template = self.program.headers.blocks.get(args[1])
                if template is None:
                    return 0
                return len(collection) * self._template_size(template)
            if stmt.name == "link:align" and args:
                align = _intish(args[0], 1)
                current = sum(block.physical_size for block in self.blocks.values() if block.kind == "header")
                return (-current) % align

        if header.table is not None:
            return self._template_size(header)
        return 0

    def _template_size(self, header: HeaderBlock) -> int:
        """Obtiene la suma del tamaño acumulado de campos descritos en una plantilla de cabecera.

        Args:
            header: Bloque de cabecera del que se evalúa la plantilla.

        Returns:
            Tamaño virtual de la cabecera en bytes.
        """
        if header.size not in (None, "", "*"):
            return _intish(header.size, 0)
        if header.table is None:
            return 0
        end = 0
        for row in header.table.rows.values():
            end = max(end, _intish(row.values.get("OFFSET", 0), 0) + _intish(row.values.get("SIZE", 0), 0))
        return end

    def _assign_offsets(self, blocks: list[LinkBlock]) -> None:
        """Asigna de forma secuencial y ordenada las direcciones físicas y virtuales de cada bloque.

        Args:
            blocks: Lista de bloques de enlace en planeación.
        """
        physical = 0
        virtual = 0
        for block in blocks:
            if block.kind in {"section", "nobits"}:
                physical = _align_to(physical, block.align)
                valign = _intish(block.row.values.get("valign", block.align), block.align) if block.row else block.align
                virtual = _align_to(virtual, max(1, valign))

            block.physical_offset = physical
            block.virtual_offset = virtual
            block.physical_size = len(block.data) if block.kind != "nobits" else 0
            block.virtual_size = max(block.virtual_size, len(block.data))

            physical += block.physical_size
            virtual += block.virtual_size

    def _relocate_source_data(self, blocks: list[LinkBlock]) -> None:
        """Relocaliza las variables de datos enlazándolas con sus direcciones de ejecución virtuales finales.

        Args:
            blocks: Lista de bloques de enlace.
        """
        for row in self.program.objects.values():
            if row.section != ".data" or not row.values.get("SOURCE_DATA"):
                continue
            section = str(row.values.get("SECTION", self._payload_section("data")))
            data_block = next((block for block in blocks if block.name == section), None)
            if data_block is None:
                continue
            section_offset = _intish(row.values.get("SECTION_OFFSET", row.values.get("addrs", 0)), 0)
            row.values["addrs"] = data_block.virtual_offset + section_offset

    def _relocate_memory_regions(self, blocks: list[LinkBlock]) -> None:
        """Relocaliza direcciones de pila, montón y buffers de memoria en base a sus offsets de bloque asignados.

        Args:
            blocks: Lista de bloques de enlace.
        """
        for region in self.program.memory.regions.values():
            row = self.program.objects.get(region.name)
            block = self.blocks.get(region.section)
            if row is None or block is None:
                continue
            section_offset = _intish(row.values.get("SECTION_OFFSET", 0), 0)
            row.values["addrs"] = block.virtual_offset + section_offset
            row.values["paddrs"] = block.physical_offset + section_offset if block.kind != "nobits" else None
            region.values["addrs"] = row.values["addrs"]
            region.values["paddrs"] = row.values["paddrs"]
            self._materialize_memory_symbols(region, row)

    def _materialize_memory_symbols(self, region: MemoryRegion, row: TableRow) -> None:
        """Materializa y registra símbolos y offsets auxiliares relativos a regiones de memoria (base, limit, sp, cursor).

        Args:
            region: Objeto región de memoria.
            row: Fila del objeto de memoria en la tabla.
        """
        base = _intish(row.values.get("addrs", 0), 0)
        limit = base + region.bytes
        physical = row.values.get("paddrs")

        self._upsert_memory_symbol(region, "base", base, physical)
        self._upsert_memory_symbol(region, "limit", limit, None if physical in (None, "") else _intish(physical, 0) + region.bytes)

        if region.kind == "stack":
            growth = str(row.values.get("GROWTH", row.values.get("growth", "down"))).strip().lower()
            sp = limit if growth in {"down", "desc", "descending", "-"} else base
            self._upsert_memory_symbol(region, "sp", sp, None)
        elif region.kind == "heap":
            self._upsert_memory_symbol(region, "cursor", base, physical)

    def _upsert_memory_symbol(self, region: MemoryRegion, suffix: str, addrs: int, paddrs: Any) -> None:
        """Crea o actualiza de forma segura un sub-símbolo de memoria en la base de objetos del programa.

        Args:
            region: Objeto de memoria base.
            suffix: Sufijo del sub-símbolo (e.g., 'limit').
            addrs: Dirección virtual.
            paddrs: Dirección física.
        """
        name = f"{region.name}.{suffix}"
        values = {
            "NAME": name,
            "PRIVTYPE": region.kind,
            "KIND": region.kind,
            "parent": region.name,
            "ROLE": suffix,
            "TYPE": region.type_name,
            "TYPE_RAW": region.type_token,
            "SECTION": region.section,
            "bytes": 0,
            "bits": 0,
            "addrs": addrs,
            "paddrs": paddrs,
            "psize": 0,
            "vsize": 0,
        }
        self.program.objects[name] = TableRow(name=name, values=values, line=region.line or 0, section=f".{region.kind}s")

    def _materialize_headers(self, blocks: list[LinkBlock]) -> None:
        """Evalúa y serializa los campos de cada cabecera calculando sus offsets finales de bloque.

        Args:
            blocks: Lista de bloques de enlace.
        """
        self.placeholders.clear()
        for block in blocks:
            if block.kind != "header":
                continue
            header = self.program.headers.blocks.get(block.name)
            if header is None:
                continue
            block.data = self._render_header(header, block)
            block.physical_size = len(block.data)
            block.virtual_size = len(block.data)

    def _render_header(self, header: HeaderBlock, block: LinkBlock, context: dict[str, Any] | None = None) -> bytes:
        """Renderiza y serializa a binario las plantillas y campos pertenecientes a una cabecera.

        Args:
            header: Estructura del bloque cabecera.
            block: Bloque de enlace donde se inyectarán los datos renderizados.
            context: Diccionario de contexto opcional para resolver colecciones dinámicas.

        Returns:
            La secuencia de bytes renderizada para la cabecera.
        """
        if header.statements:
            for stmt in header.statements:
                args = stmt.arg_values()
                if stmt.name == "link:each" and len(args) >= 2:
                    rows = self._collection_rows(args[0])
                    template = self.program.headers.blocks.get(args[1])
                    if template is None:
                        return block.data
                    parts = [
                        self._render_header(template, LinkBlock(template.name, "header", data=self._initial_header_data(template)), {"section": row})
                        for row in rows
                    ]
                    return b"".join(parts)
                if stmt.name == "link:align" and args:
                    align = _intish(args[0], 1)
                    before = sum(b.physical_size for b in self.blocks.values() if b.kind == "header" and b.name != block.name)
                    return b"\x00" * ((-before) % align)

        data = bytearray(block.data)
        if header.table is None:
            return bytes(data)

        minimum = self._template_size(header)
        if len(data) < minimum:
            data.extend(b"\x00" * (minimum - len(data)))

        for row in header.table.rows.values():
            offset = _intish(row.values.get("OFFSET", 0), 0)
            size = _intish(row.values.get("SIZE", 0), 0)
            endian = str(row.values.get("ENDIAN", "le")).strip().lower()
            value = row.values.get("VALUE", 0)
            encoded = self._encode_field(value, size, endian, context or {})
            data[offset:offset + size] = encoded[:size].ljust(size, b"\x00")
        return bytes(data)

    def _encode_field(self, value: Any, size: int, endian: str, context: dict[str, Any]) -> bytes:
        """Codifica un valor de campo de cabecera a su representación binaria correspondiente.

        Args:
            value: El valor a codificar (número, símbolo o directiva).
            size: Tamaño físico del campo en bytes.
            endian: Ordenación de bytes ("le", "be", "raw").
            context: Contexto dinámico de resolución.

        Returns:
            Bytes codificados que caben exactamente en el tamaño del campo.
        """
        if size <= 0:
            return b""

        if isinstance(value, str):
            value = value.strip()
            if value.startswith("link:"):
                resolved = self._resolve_link_value(value, context)
                if isinstance(resolved, Placeholder):
                    self.placeholders.append(resolved)
                    return b"\x00" * size
                value = resolved
            elif "." in value and not value.startswith(("0x", "0X")):
                resolved = self._resolve_context_value(value, context)
                if resolved is not None:
                    value = resolved
            if isinstance(value, str) and _looks_expression(value):
                resolved_expr = self._eval_link_expr(value, context)
                if isinstance(resolved_expr, Placeholder):
                    self.placeholders.append(resolved_expr)
                    return b"\x00" * size
                value = resolved_expr

        if endian == "raw":
            if isinstance(value, bytes):
                return value[:size].ljust(size, b"\x00")
            if isinstance(value, int):
                return value.to_bytes(size, "big", signed=False)
            return _raw_bytes(str(value), size)

        byteorder = "big" if endian in {"be", "big"} else "little"
        numeric = _intish(value, 0)
        return numeric.to_bytes(size, byteorder, signed=False)

    def _resolve_link_value(self, expr: str, context: dict[str, Any]) -> Any:
        """Resuelve dinámicamente el valor de una directiva o función de enlace RIF DSL (`link:*`).

        Args:
            expr: Expresión de directiva de enlace (e.g., 'link:offset .text').
            context: Contexto dinámico de resolución.

        Returns:
            El valor resuelto (entero, bytes, etc.) o un objeto Placeholder en caso de diferirse.
        """
        parts = expr.split()
        op = parts[0]
        args = parts[1:]

        hook_context = {**context, "linker": self}
        for mod in self.plugin_modules.values():
            resolver = getattr(mod, "resolve_link_value", None)
            if resolver is None:
                continue
            plugin_context = PluginContext(
                program=self.program,
                phase="link",
                config=self.config,
                linker=self,
            )
            if hasattr(mod, "set_context"):
                mod.set_context(plugin_context)
            setattr(mod, "CONTEXT", plugin_context)
            value = resolver(self.program, op, args, hook_context)
            if value is not None:
                return value

        if op == "link:count" and args:
            return len(self._collection_rows(args[0]))
        if op == "link:expr" and args:
            return self._eval_link_expr(" ".join(args), context)
        if op in {"link:size", "link:psize"}:
            return sum(self._physical_size(arg, context) for arg in args)
        if op == "link:vsize":
            return sum(self._virtual_size(arg, context) for arg in args)
        if op == "link:offset" and args:
            block = self._block_for(args[0], context)
            if block is not None:
                return block.physical_offset
            row = self._object_for(args[0], context)
            if row is not None and row.values.get("paddrs") not in (None, ""):
                return row.values["paddrs"]
            return self._placeholder(args[0], "offset")
        if op == "link:voffset" and args:
            block = self._block_for(args[0], context)
            if block is not None:
                return block.virtual_offset
            row = self._object_for(args[0], context)
            if row is not None and row.values.get("addrs") not in (None, ""):
                return row.values["addrs"]
            return self._placeholder(args[0], "voffset")
        if op == "link:name" and args:
            width = self._eval_link_expr(args[1], context) if len(args) > 1 else 0
            if isinstance(width, Placeholder):
                return width
            raw = self._name_value(args[0], context)
            return _raw_bytes(raw, width)
        if op == "link:raw" and args:
            block = self._block_for(args[0], context)
            if block is not None:
                return block.data
            row = self._object_for(args[0], context)
            if row is not None:
                return _bytes_from_hexish(row.values.get("raw", row.values.get("hex", row.values.get("binary", ""))))
            return self._placeholder(args[0], "raw")

        return self._placeholder(" ".join([op, *args]), "link")

    def _eval_link_expr(self, expr: str, context: dict[str, Any]) -> int | Placeholder:
        def resolve(name: str) -> Any:
            if name == "headers":
                return self._physical_size(name, context)
            if name == "image":
                return self._virtual_size(name, context)
            if "." in name:
                target, field = name.split(".", 1)
                row = self._object_for(target, context)
                if row is not None:
                    value = row.values.get(field)
                    if value not in (None, ""):
                        return value
                block = self._block_for(target, context)
                if block is not None:
                    values = {
                        "offset": block.physical_offset,
                        "voffset": block.virtual_offset,
                        "psize": block.physical_size,
                        "vsize": block.virtual_size,
                        "size": block.physical_size,
                    }
                    if field in values:
                        return values[field]
            row = self._object_for(name, context)
            if row is not None:
                value = row.values.get("VALUE", row.values.get("addrs"))
                if value not in (None, ""):
                    return value
            block = self._block_for(name, context)
            if block is not None:
                return block.physical_offset
            raise UnresolvedExpression(name)

        try:
            return eval_int_expr(expr, resolve)
        except UnresolvedExpression as exc:
            return self._placeholder(exc.name, "expr")
        except SyntaxError as exc:
            raise PackError(f'expresion de link invalida "{expr}"') from exc
        except ValueError as exc:
            raise PackError(f'expresion de link invalida "{expr}"') from exc

    def _collection_rows(self, name: str) -> list[TableRow]:
        """Obtiene la colección de filas de objetos asociados a un nombre de tabla o cabeceras globales.

        Args:
            name: Nombre de la colección.

        Returns:
            Lista de objetos TableRow correspondientes.
        """
        if name == "headers":
            return [
                TableRow(block.name, {"NAME": block.name, "SIZE": block.physical_size}, 0, ".headers")
                for block in self.blocks.values()
                if block.kind == "header"
            ]
        table = self.program.tables.get(name)
        if table is not None:
            return list(table.rows.values())
        return []

    def _physical_size(self, name: str, context: dict[str, Any]) -> int:
        """Determina el tamaño físico (ocupado por bytes reales) de un bloque, sección u objeto.

        Args:
            name: Nombre del objeto a evaluar.
            context: Contexto de resolución dinámico.

        Returns:
            Ancho físico en bytes.
        """
        block = self._block_for(name, context)
        if block is not None:
            return block.physical_size
        if name == "headers":
            return sum(block.physical_size for block in self.blocks.values() if block.kind == "header")
        if name == "image":
            return sum(block.physical_size for block in self.blocks.values())
        row = self._object_for(name, context)
        if row is not None:
            return _intish(row.values.get("psize", row.values.get("bytes", row.values.get("SIZE", 0))), 0)
        return 0

    def _virtual_size(self, name: str, context: dict[str, Any]) -> int:
        """Determina el tamaño virtual (en memoria durante ejecución) de un bloque, sección o región.

        Args:
            name: Nombre del objeto a evaluar.
            context: Contexto de resolución dinámico.

        Returns:
            Ancho virtual en bytes.
        """
        block = self._block_for(name, context)
        if block is not None:
            return block.virtual_size
        if name == "headers":
            return sum(block.virtual_size for block in self.blocks.values() if block.kind == "header")
        if name == "image":
            return sum(block.virtual_size for block in self.blocks.values())
        row = self._object_for(name, context)
        if row is not None:
            return _intish(row.values.get("vsize", row.values.get("bytes", row.values.get("SIZE", 0))), 0)
        return 0

    def _block_for(self, name: str, context: dict[str, Any]) -> LinkBlock | None:
        """Recupera el bloque de enlace LinkBlock correspondiente de forma directa o por contexto.

        Args:
            name: Identificador del bloque.
            context: Contexto dinámico.

        Returns:
            El objeto LinkBlock, o None si no se encuentra.
        """
        if name in context:
            row = context[name]
            if isinstance(row, TableRow):
                return self.blocks.get(row.name)
        if name == "section" and "section" in context:
            row = context["section"]
            if isinstance(row, TableRow):
                return self.blocks.get(row.name)
        return self.blocks.get(name)

    def _object_for(self, name: str, context: dict[str, Any]) -> TableRow | None:
        """Recupera la fila de datos TableRow correspondiente al objeto indicado.

        Args:
            name: Nombre del objeto.
            context: Contexto dinámico.

        Returns:
            La fila de la tabla TableRow o None.
        """
        if name in context and isinstance(context[name], TableRow):
            return context[name]
        if name == "section" and isinstance(context.get("section"), TableRow):
            return context["section"]
        return self.program.objects.get(name)

    def _name_value(self, name: str, context: dict[str, Any]) -> str:
        """Deduce el nombre absoluto del objeto en evaluación.

        Args:
            name: Identificador del operando.
            context: Contexto dinámico.

        Returns:
            El nombre como cadena de texto.
        """
        if name in context and isinstance(context[name], TableRow):
            return context[name].name
        if name == "section" and isinstance(context.get("section"), TableRow):
            return context["section"].name
        return name

    def _resolve_context_value(self, value: str, context: dict[str, Any]) -> Any | None:
        """Resuelve propiedades dinámicas asociadas a objetos dentro del contexto.

        Args:
            value: La cadena de la propiedad (e.g., 'section.NAME').
            context: Contexto de resolución dinámico.

        Returns:
            El valor asignado a la propiedad, o None.
        """
        target, field = value.split(".", 1)
        item = context.get(target)
        if isinstance(item, TableRow):
            return item.values.get(field)
        return None

    def _placeholder(self, target: str, kind: str) -> Placeholder:
        """Crea un objeto Placeholder para marcar referencias y offsets diferidos.

        Args:
            target: Nombre o destino de la referencia no resuelta.
            kind: Tipo o rol del placeholder.

        Returns:
            El objeto Placeholder.
        """
        return Placeholder(target=target, kind=kind, reason="linker placeholder")


def link_file(source_path: str | Path, output_path: str | Path | None = None, write: bool = True) -> PackedResult:
    """Función de conveniencia global para realizar el enlace de un archivo de origen.

    Args:
        source_path: Ruta del fuente original.
        output_path: Ruta de destino opcional.
        write: Si es True, escribe el resultado del enlace en disco.

    Returns:
        El objeto PackedResult del enlace.
    """
    return Linker(source_path).link(output_path, write=write)


def build_file(
    source_path: str | Path,
    output_path: str | Path | None = None,
    source: str = "",
    write: bool = True,
) -> BinaryLinkResult:
    """Función de conveniencia global para construir el binario a partir de un archivo de origen.

    Args:
        source_path: Ruta al archivo fuente original.
        output_path: Ruta del archivo binario final.
        source: Ensamblador complementario.
        write: Si es True, guarda el binario compilado en disco.

    Returns:
        El resultado detallado BinaryLinkResult.
    """
    return Linker(source_path).build_binary(source, output_path, write=write)


def _contains_section_header(text: str) -> bool:
    """Valida si el texto especificado contiene alguna cabecera o declaración de sección.

    Args:
        text: Texto a escanear.

    Returns:
        True si encuentra alguna directiva de sección, False en caso contrario.
    """
    for raw in text.splitlines():
        if _section_name_from_raw(raw) is not None:
            return True
    return False


def _section_ranges(lines: list[str]) -> dict[str, tuple[int, int]]:
    """Mapea y calcula los límites (línea de inicio y fin) de cada sección dentro del fuente.

    Args:
        lines: Lista de líneas del código fuente.

    Returns:
        Diccionario que mapea nombres de sección con sus rangos de línea en tuplas (inicio, fin).
    """
    ranges: dict[str, tuple[int, int]] = {}
    current: str | None = None
    current_start = 0

    for index, raw in enumerate(lines):
        section = _section_name_from_raw(raw)

        if section is not None:
            if current is not None:
                ranges[current] = (current_start, index)
            current = section
            current_start = index

    if current is not None:
        ranges[current] = (current_start, len(lines))

    return ranges


def _section_name_from_raw(raw: str) -> str | None:
    """Analiza una línea para comprobar si corresponde a la declaración de inicio de una sección.

    Args:
        raw: Línea a analizar.

    Returns:
        El nombre de la sección si es una declaración, o None.
    """
    try:
        tokens = Lexer(raw).lex_line(raw, 1)
    except Exception:
        return None
    if len(tokens) in (1, 2) and tokens[0].kind == "SECTION":
        if len(tokens) == 1 or tokens[1].kind == "BLOCK":
            return tokens[0].value
    if len(tokens) in (2, 3) and tokens[0].kind == "IDENT" and tokens[1].kind == "SECTION":
        if len(tokens) == 2 or tokens[2].kind == "BLOCK":
            return tokens[1].value
    return None


def _section_header(config: PackerConfig, section: str) -> str:
    """Genera la declaración de cabecera de sección ensambladora con su prefijo adecuado.

    Args:
        config: Configuración del packer.
        section: Nombre de la sección.

    Returns:
        Línea de declaración de la sección ensambladora.
    """
    if config.sectpre:
        return f"{config.sectpre} {section}"
    return section


def _flat_fragments(fragments: list[str]) -> list[str]:
    """Aplana una lista de fragmentos multilínea en una lista consolidada de líneas individuales.

    Args:
        fragments: Lista de fragmentos.

    Returns:
        Lista consolidada de líneas de ensamblador.
    """
    out: list[str] = []
    for fragment in fragments:
        out.extend(fragment.splitlines())
        out.append("")
    if out and out[-1] == "":
        out.pop()
    return out


def _row_order(row: TableRow) -> tuple[int, str]:
    """Genera la clave de ordenación para una sección en base a su propiedad 'order'.

    Args:
        row: Fila del objeto sección.

    Returns:
        Tupla con el valor del orden y el nombre.
    """
    return (_intish(row.values.get("order", 0), 0), row.name)


def _source_symbol_name(source: str) -> str | None:
    """Obtiene el identificador principal o nombre de símbolo de una línea de ensamblador.

    Args:
        source: Línea de ensamblador.

    Returns:
        Nombre del símbolo como cadena o None.
    """
    stripped = source.strip()
    if not stripped:
        return None
    head = stripped.split(None, 1)[0]
    return head or None


def _looks_expression(value: str) -> bool:
    text = value.strip()
    if not text or text.startswith(("0x", "0X", "0b", "0B")):
        return False
    return any(op in text for op in ("+", "-", "*", "/", "%", "<<", ">>", "&", "|", "^", "~", "(", ")"))


def _intish(value: Any, default: int = 0) -> int:
    """Convierte de forma segura un valor de cualquier tipo a un entero.

    Soporta decimales y notaciones hexadecimales (e.g., '0x10').

    Args:
        value: Valor a convertir.
        default: Valor por defecto en caso de error.

    Returns:
        Valor entero resultante.
    """
    if value in (None, "", "*"):
        return default
    if isinstance(value, int):
        return value
    text = str(value).strip().replace("_", "")
    try:
        return int(text, 0)
    except ValueError:
        return default


def _align_to(value: int, align: int) -> int:
    """Alinea un desplazamiento numérico al múltiplo superior más cercano de 'align'.

    Args:
        value: Desplazamiento actual.
        align: Múltiplo de alineación.

    Returns:
        Desplazamiento alineado.
    """
    if align <= 1:
        return value
    return value + ((-value) % align)


def _bytes_from_hexish(value: Any) -> bytes:
    """Convierte de forma flexible un valor en formato hexadecimal a un buffer de bytes.

    Args:
        value: Valor en formato hex, bytes o número entero.

    Returns:
        Buffer de bytes.
    """
    if value in (None, ""):
        return b""
    if isinstance(value, bytes):
        return value
    if isinstance(value, int):
        width = max(1, (value.bit_length() + 7) // 8)
        return value.to_bytes(width, "big")
    text = str(value).strip()
    if not text:
        return b""
    compact = text.replace(" ", "").replace("_", "")
    if compact.startswith(("0x", "0X")):
        compact = compact[2:]
    if len(compact) % 2:
        compact = "0" + compact
    try:
        return bytes.fromhex(compact)
    except ValueError:
        return text.encode("utf-8")


def _bytes_from_fill(value: Any) -> bytes:
    """Genera el buffer de bytes a utilizar como relleno.

    Args:
        value: Valor representativo del patrón de relleno.

    Returns:
        Buffer de bytes de relleno.
    """
    raw = _bytes_from_hexish(value)
    return raw or b"\x00"


def _raw_bytes(value: str, width: int) -> bytes:
    """Obtiene y trunca o rellena un buffer de bytes a un ancho exacto predefinido.

    Args:
        value: Cadena original.
        width: Ancho objetivo.

    Returns:
        Buffer de bytes de ancho exacto.
    """
    raw = _bytes_from_hexish(value)
    if width <= 0:
        return raw
    return raw[:width].ljust(width, b"\x00")
