"""RIF AMD64 Linux v3: symbolic fixups, virtual addresses and ELF execution.

Run: python tests/test_relocations.py --rif-root /path/to/RIF-main
All code executed in test binaries uses only Linux syscall/write/exit.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

BASE = Path(__file__).resolve().parents[1]


def checks(rif_root: Path, gram_root: Path | None = None) -> None:
    sys.path.insert(0, str(rif_root))
    if gram_root is not None:
        sys.path.insert(0, str(gram_root))
    from MIR.external import compile_mir_source, prepare_target  # noqa: PLC0415

    checked = 0
    ex = 0
    for variant in ('main', 'main_rw'):
        pack = BASE / ('amd64.pack' if variant == 'main' else 'amd64-rw.pack')
        target = prepare_target(pack)
        assert len(target.program.rules) >= 40
        print(f'{variant}: {len(target.program.rules)} Rules; pack {pack.stat().st_size:,} bytes')

    text = prepare_target(BASE / 'amd64.pack')
    rw = prepare_target(BASE / 'amd64-rw.pack')
    hello = (BASE / 'symbols_runtime.asm').read_text()
    result = compile_mir_source(text, hello)
    symbols = result.symbols
    fixups = result.context.fixups
    assert fixups
    assert result.binary[:4] == b'\x7fELF'
    assert len(result.binary) == result.image.sections['text'].file_size
    for fixup in fixups:
        target = symbols[fixup.symbol]
        offset = result.image.section_offset(fixup.section) + fixup.offset_bits // 8
        size = fixup.width_bits // 8
        next_ip = result.image.section_virtual_base(fixup.section) + fixup.next_virtual_bits // 8
        resolved = int.from_bytes(result.binary[offset:offset+size], 'little', signed=fixup.kind.startswith('pc'))
        assert resolved == (target-next_ip if fixup.kind.startswith('pc') else target), (fixup.kind, fixup.symbol, resolved)
        checked += 1
    assert {'message', 'begin', 'answer', 'finish', 'exit_point'} <= symbols.keys()
    assert any(fixup.kind == 'pc8' for fixup in fixups)
    assert any(
        symbols[fixup.symbol]
        - (result.image.section_virtual_base(fixup.section) + fixup.next_virtual_bits // 8)
        < 0
        for fixup in fixups
        if fixup.kind.startswith('pc')
    )

    # Test absolute address and backward relative references without executing
    # intentionally arbitrary bytes that follow the exit syscall.
    abs_demo = '''_start
movaddr64 r15, data
jmp_label continue
mark data
dqaddr data
mark continue
jmp8_label data
'''
    result2 = compile_mir_source(text, abs_demo)
    symbols = result2.symbols
    for fixup in result2.context.fixups:
        off = result2.image.section_offset(fixup.section) + fixup.offset_bits // 8
        width = fixup.width_bits // 8
        next_ip = result2.image.section_virtual_base(fixup.section) + fixup.next_virtual_bits // 8
        value = int.from_bytes(result2.binary[off:off+width], 'little', signed=fixup.kind.startswith('pc'))
        assert value == (symbols[fixup.symbol] - next_ip if fixup.kind.startswith('pc') else symbols[fixup.symbol])
        checked += 1
    assert any(fixup.kind == 'abs64' for fixup in result2.context.fixups)

    # ELF64 two segments and virtual-only reservation.
    result3 = compile_mir_source(rw, (BASE/'symbols_rw.asm').read_text())
    rdata = result3.image.sections['data']
    assert rdata.virtual_base == 0x401000
    assert rdata.file_offset == 0x1000
    assert rdata.file_size == 11
    assert rdata.virtual_size == 43
    assert len(result3.binary) == 0x1000 + 11
    checked += 4
    rw_symbols = result3.symbols
    assert rw_symbols['counter'] == 0x401000
    assert rw_symbols['message'] == 0x401008
    assert rw_symbols['scratch'] == 0x40100b
    for fixup in result3.context.fixups:
        off = result3.image.section_offset(fixup.section) + fixup.offset_bits // 8
        width = fixup.width_bits // 8
        next_ip = result3.image.section_virtual_base(fixup.section) + fixup.next_virtual_bits // 8
        value = int.from_bytes(result3.binary[off:off+width], 'little', signed=fixup.kind.startswith('pc'))
        assert value == (rw_symbols[fixup.symbol] - next_ip if fixup.kind.startswith('pc') else rw_symbols[fixup.symbol])
        checked += 1

    # Bare virtual-only allocation at the end of code (p_memsz > p_filesz).
    virtual = compile_mir_source(text, '_start\nmov rax, 60\nmov rdi, 42\nsyscall\nvirtual_scratch\n')
    assert virtual.image.sections['text'].virtual_size == len(virtual.binary) + 32
    checked += 1

    # Native reservation from RIF's own syntax and patch.
    slots = compile_mir_source(text, '_start\nreserve_and_fill_demo\n')
    assert slots.binary[-2:] == bytes.fromhex('abcd')
    checked += 1

    # Inspect reservation addresses (RIF reports bit offsets, not absolute VAs).
    relative = compile_mir_source(text, '_start\nreserve_position_demo\n')
    assert int.from_bytes(relative.binary[-8:], 'big') == (len(relative.binary)-8)*8
    checked += 1

    errors = (
        ('undefined', '_start\njmp_label missing\n', 'no definido'),
        ('duplicate', '_start\nmark same\nmark same\n', 'duplicado'),
        ('short-branch-overflow', '_start\njmp8_label far\n'+'nop\n'*200+'mark far\n', 'fuera del rango'),
        ('invalid-symbol', '_start\njmp_label 123\n', 'identificador'),
    )
    for tag, src, message in errors:
        try:
            compile_mir_source(text, src)
        except Exception as exception:
            assert message in str(exception), (tag, repr(exception))
            checked += 1
        else:
            raise AssertionError(f'{tag}: debería fallar')

    binaries = tuple(BASE / name for name in ('symbols_runtime.elf', 'symbols_rw.elf'))
    if all(path.exists() for path in binaries):
        for binary in binaries:
            binary.chmod(0o755)
            program = subprocess.run([str(binary)], capture_output=True, check=False)
            assert program.returncode == 42, (binary.name, program.returncode)
            assert program.stdout == b'Hi\n', (binary.name, program.stdout)
            ex += 1
    else:
        print('SKIP: no hay ELF generados para ejecutar la regresión CPU')

    print(f'OK: {checked} verificaciones de bits, relocaciones, memoria virtual y errores; {ex} ELF ejecutados correctamente')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--rif-root', type=Path, required=True)
    parser.add_argument('--gram-root', type=Path, default=None)
    args = parser.parse_args()
    checks(args.rif_root, args.gram_root)
