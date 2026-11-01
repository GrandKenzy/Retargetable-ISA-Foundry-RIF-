"""Command-line entrypoint for RIF project tools."""

from __future__ import annotations

import vendor.__bootstrap__  # From VNMA.

import argparse
import os
import sys
from pathlib import Path

from pack import create_pack
from pack_inspector import (
    MAX_REPORT_ITEMS,
    PackInspectionError,
    inspect_pack,
    render_pack_inspection,
)
from pcpi import PCPIError, load_pcpi_file
from pcpi_compiler import compile_pcpi_source_file
from rif_limits import ENV_KEY, parse_mib, write_mib
from rif_library import create_library
from store import StoreError, compile_store_file
from MIR.storage import StorageError, load_storage_file
from MIR.diagnostics import format_exception


def _print_error(error: BaseException) -> None:
    print(f"rif: error: {format_exception(error)}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rif", description="Herramientas del compilador RIF")
    parser.add_argument(
        "--pack",
        metavar="MAIN.RIF",
        help="empaqueta todos los archivos .rif del proyecto",
    )
    parser.add_argument(
        "--library",
        metavar="MAIN.RIF",
        help="crea una librería .riflib desde un .rif o exporta declaraciones desde un .pack",
    )
    parser.add_argument(
        "--comp-pcpi",
        metavar="IMAGE.PCI",
        help="compila una fuente declarativa .pci a un archivo .pcic",
    )
    parser.add_argument(
        "--comp-store",
        metavar="DATA.STORE",
        help="compila una fuente .store a un storage.bin indexado",
    )
    parser.add_argument(
        "--doctor-pcpi",
        metavar="IMAGE.PCIC",
        help="valida una PCP-I compilada sin modificarla",
    )
    parser.add_argument(
        "--doctor-storage",
        metavar="STORAGE.BIN",
        help="valida un storage.bin indexado sin modificarlo",
    )
    parser.add_argument(
        "--inspect-pack",
        metavar="TARGET.PACK",
        help="inspecciona y verifica un paquete .pack sin ejecutar su target",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emite la inspección del paquete como JSON",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="incluye instrucciones de Rules y filas de tablas en la inspección",
    )
    parser.add_argument(
        "--show-origins",
        action="store_true",
        help="muestra las rutas de origen guardadas en el manifiesto",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=MAX_REPORT_ITEMS,
        metavar="N",
        help=f"máximo de elementos repetidos por sección (1-{10_000}; default: {MAX_REPORT_ITEMS})",
    )
    parser.add_argument(
        "--backend",
        choices=("python", "aot"),
        default="aot",
        help="backend del frontend RIF; 'aot' usa el parser C de Gram",
    )
    parser.add_argument(
        "--plimit",
        metavar="MiB",
        type=parse_mib,
        help="límite de recursos por operación en MiB; también se guarda en .env",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="ARCHIVO",
        help="ruta de salida del paquete, binario o PCP-I compilada",
    )
    parser.add_argument(
        "--map",
        dest="map_output",
        metavar="MAPA.JSON",
        help="escribe un mapa opcional de símbolos, secciones, Rules y fixups",
    )
    parser.add_argument(
        "definition",
        nargs="?",
        help="definición objetivo .rif o .pack",
    )
    parser.add_argument(
        "mir",
        nargs="?",
        help="archivo MIR con la extensión declarada por linker.extension",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.inspect_pack:
        if (
            args.pack
            or args.library
            or args.comp_pcpi
            or args.comp_store
            or args.doctor_pcpi
            or args.doctor_storage
            or args.definition
            or args.mir
            or args.output
            or args.map_output
            or args.plimit is not None
        ):
            parser.error(
                "--inspect-pack no puede combinarse con otra operación, --plimit, -o ni --map"
            )
        try:
            report = inspect_pack(
                args.inspect_pack,
                verbose=args.verbose,
                max_items=args.max_items,
                show_origins=args.show_origins,
            )
        except (FileNotFoundError, OSError, ValueError, PackInspectionError) as exc:
            _print_error(exc)
            return 1
        print(render_pack_inspection(report, json_output=args.json), end="")
        return 0
    if args.plimit is not None:
        try:
            write_mib(args.plimit)
            os.environ[ENV_KEY] = str(args.plimit)
        except (OSError, ValueError) as exc:
            _print_error(exc)
            return 1
    if args.json or args.verbose or args.show_origins or args.max_items != MAX_REPORT_ITEMS:
        parser.error("--json/--verbose/--show-origins/--max-items requieren --inspect-pack")
    if args.map_output and (args.pack or args.library or args.comp_pcpi or args.comp_store or args.doctor_pcpi or args.doctor_storage):
        parser.error("--map solo puede acompañar la compilación de MIR")
    if args.library:
        if (
            args.pack
            or args.comp_pcpi
            or args.comp_store
            or args.doctor_pcpi
            or args.doctor_storage
            or args.definition
            or args.mir
        ):
            parser.error("--library no puede combinarse con otra operación")
        try:
            output = create_library(args.library, args.output)
        except (FileNotFoundError, OSError, ValueError) as exc:
            _print_error(exc)
            return 1
        print(output)
        return 0
    if args.comp_pcpi:
        if args.pack or args.comp_store or args.doctor_pcpi or args.doctor_storage or args.definition or args.mir:
            parser.error("--comp-pcpi no puede combinarse con --pack ni con una definición MIR")
        try:
            output = compile_pcpi_source_file(args.comp_pcpi, args.output)
        except (FileNotFoundError, OSError, ValueError, RuntimeError, PCPIError) as exc:
            _print_error(exc)
            return 1
        print(output)
        return 0
    if args.comp_store:
        if args.pack or args.comp_pcpi or args.doctor_pcpi or args.doctor_storage or args.definition or args.mir:
            parser.error("--comp-store no puede combinarse con --pack ni con una definición MIR")
        try:
            output = compile_store_file(args.comp_store, args.output)
        except (FileNotFoundError, OSError, ValueError, StoreError) as exc:
            _print_error(exc)
            return 1
        print(output)
        return 0
    if args.doctor_pcpi:
        if args.pack or args.comp_pcpi or args.comp_store or args.doctor_storage or args.definition or args.mir:
            parser.error("--doctor-pcpi no puede combinarse con otra operación de RIF")
        try:
            image = load_pcpi_file(args.doctor_pcpi)
        except (FileNotFoundError, OSError, ValueError, PCPIError) as exc:
            _print_error(exc)
            return 1
        print(
            "OK PCP-I"
            f" version={image.version}"
            f" signature={image.signature.decode('utf-8')}"
            f" endianness={image.endianness}"
            f" bitorder={image.bitorder}"
            f" raw_size={image.image_size}"
            f" padding={len(image.padding)}"
            f" rpad={len(image.rpad)}"
            f" pits={len(image.pits)}"
        )
        for index, pit in enumerate(image.pits):
            print(
                f"pit[{index}] address={pit.address} size={pit.size} "
                f"padding={pit.padding}"
            )
        return 0
    if args.doctor_storage:
        if args.pack or args.comp_pcpi or args.comp_store or args.doctor_pcpi or args.definition or args.mir:
            parser.error("--doctor-storage no puede combinarse con otra operación de RIF")
        try:
            image = load_storage_file(args.doctor_storage)
        except (FileNotFoundError, OSError, ValueError, StorageError) as exc:
            _print_error(exc)
            return 1
        print(
            "OK STORAGE"
            f" version={image.version}"
            f" raw_size={len(image.raw)}"
            f" entries={len(image.entries)}"
        )
        for index, entry in enumerate(image.entries):
            label = image.label(index) if entry.label_size else "-"
            print(
                f"entry[{index}] address={entry.relative_address} "
                f"size={entry.raw_size} padding={entry.padding} "
                f"label_size={entry.label_size} label={label}"
            )
        return 0
    if not args.pack:
        if not args.definition or not args.mir:
            parser.error(
                "debes indicar una definición y un MIR, por ejemplo: rif main.rif main.asm"
            )
        output = args.output
        if output is None:
            output = str(Path(args.mir).with_suffix(".bin"))
        try:
            from MIR import compile_mir_file

            compilation = compile_mir_file(
                args.definition,
                args.mir,
                output=output,
                map_output=args.map_output,
                backend=args.backend,
            )
        except (FileNotFoundError, OSError, ValueError, RuntimeError) as exc:
            print(f"rif: error: {exc}", file=sys.stderr)
            return 1
        for pit in compilation.pcpi_pit_addresses:
            print(
                f"RIF_PCPI PIT {pit.index} SECTION {pit.section} ADDRESS {pit.address}"
            )
        print(output)
        return 0

    if args.definition or args.mir:
        parser.error("--pack no puede combinarse con una definición MIR")

    try:
        output = create_pack(Path(args.pack), args.output, precompile=True)
    except (FileNotFoundError, OSError, ValueError) as exc:
        _print_error(exc)
        return 1

    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
