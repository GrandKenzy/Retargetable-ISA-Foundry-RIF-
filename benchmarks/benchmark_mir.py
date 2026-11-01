"""Compare direct external-MIR execution with the CLI entry point."""

from __future__ import annotations

import statistics
import tempfile
import time
from pathlib import Path

from MIR import compile_mir_file, compile_mir_tokens, prepare_target, tokenize_mir
from main import main as rif_main


TARGET = '''\
@block config:
    format section ".section"
    section text ""
    format section_end ":"
    entry text "_start"
    comment ";"
    format label_end ":"
    default text
    word_size 8
    address_size 8
    byte_order "little"
    case_sensitive true
    symbol_prefix "_"
    local_prefix "."
    undefined_symbols "error"
    duplicate_symbols "error"
    strict true
    allow_empty_sections false
@end
@block linker:
    extension ".asm"
    search_path ""
@end
@rule mov:
. IDENT
. eword 1
'''


def median_ms(samples: list[float]) -> float:
    return statistics.median(samples) * 1000


def main() -> int:
    repetitions = 5
    instruction_count = 1000
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        target = root / "main.rif"
        source = root / "program.asm"
        output = root / "program.bin"
        target.write_text(TARGET, encoding="utf-8")
        source.write_text("mov\n" * instruction_count, encoding="utf-8")

        prepared = prepare_target(target)
        tokens = tokenize_mir(source.read_text(encoding="utf-8"), str(source))
        direct_samples: list[float] = []
        cli_samples: list[float] = []
        direct_binary = b""
        cli_binary = b""

        for _ in range(repetitions):
            start = time.perf_counter()
            direct = compile_mir_tokens(prepared, tokens)
            direct_samples.append(time.perf_counter() - start)
            direct_binary = direct.binary

            start = time.perf_counter()
            status = rif_main([str(target), str(source), "-o", str(output)])
            cli_samples.append(time.perf_counter() - start)
            if status != 0:
                raise RuntimeError(f"La entrada CLI falló con código {status}.")
            cli_binary = output.read_bytes()

        if direct_binary != cli_binary:
            raise AssertionError("La API directa y la CLI produjeron binarios distintos.")
        expected = bytes([1]) * instruction_count
        if direct_binary != expected:
            raise AssertionError("El binario producido no coincide con el resultado esperado.")

        print(f"instructions={instruction_count}")
        print(f"direct_tokens_ms median={median_ms(direct_samples):.3f}")
        print(f"cli_file_ms median={median_ms(cli_samples):.3f}")
        print(f"binary_bytes={len(direct_binary)}")
        print("direct_vs_cli=match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
