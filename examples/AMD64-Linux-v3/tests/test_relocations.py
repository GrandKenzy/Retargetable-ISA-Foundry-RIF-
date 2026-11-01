"""RIF AMD64 Linux v3: symbolic fixups, virtual addresses and ELF execution.

Run: python tests/test_relocations.py --rif-root /path/to/RIF-main
All code executed in test binaries uses only Linux syscall/write/exit.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import struct
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
    state = result.context.storage['__amd64_linker__']
    assert state['fixups']
    assert result.binary[:4] == b'\x7fELF'
    assert len(result.binary) == result.image.sections['text'].file_size
    for kind, offset, size, next_ip, name in state['fixups']:
        target = state['symbols'][name]
        resolved = int.from_bytes(result.binary[offset:offset+size], 'little', signed=kind.startswith('pc'))
        assert resolved == (target-next_ip if kind.startswith('pc') else target), (kind, name, resolved)
        checked += 1
    assert {'message', 'begin', 'answer', 'finish', 'exit_point'} <= state['symbols'].keys()
    assert any(kind == 'pc8' for kind, *_ in state['fixups'])
    assert any((state['symbols'][sym] - next_ip) < 0 for kind, _, _, next_ip, sym in state['fixups'] if kind.startswith('pc'))

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
    symbols = result2.context.storage['__amd64_linker__']['symbols']
    for kind, off, width, next_ip, sym in result2.context.storage['__amd64_linker__']['fixups']:
        value = int.from_bytes(result2.binary[off:off+width], 'little', signed=kind.startswith('pc'))
        assert value == (symbols[sym] - next_ip if kind.startswith('pc') else symbols[sym])
        checked += 1
    assert any(k == 'abs64' for k, *_ in result2.context.storage['__amd64_linker__']['fixups'])

    # ELF64 two segments and virtual-only reservation.
    result3 = compile_mir_source(rw, (BASE/'symbols_rw.asm').read_text())
    rdata = result3.image.sections['data']
    assert rdata.virtual_base == 0x401000
    assert rdata.file_offset == 0x1000
    assert rdata.file_size == 11
    assert rdata.virtual_size == 43
    assert len(result3.binary) == 0x1000 + 11
    assert struct.unpack_from('<Q', result3.binary, 152)[0] == 11
    assert struct.unpack_from('<Q', result3.binary, 160)[0] == 43
    checked += 6
    rwstate = result3.context.storage['__amd64_linker__']
    assert rwstate['symbols']['counter'] == 0x401000
    assert rwstate['symbols']['message'] == 0x401008
    assert rwstate['symbols']['scratch'] == 0x40100b
    for kind, off, width, next_ip, sym in rwstate['fixups']:
        value = int.from_bytes(result3.binary[off:off+width], 'little', signed=kind.startswith('pc'))
        assert value == (rwstate['symbols'][sym] - next_ip if kind.startswith('pc') else rwstate['symbols'][sym])
        checked += 1

    # Bare virtual-only allocation at the end of code (p_memsz > p_filesz).
    virtual = compile_mir_source(text, '_start\nmov rax, 60\nmov rdi, 42\nsyscall\nvirtual_scratch\n')
    assert struct.unpack_from('<Q', virtual.binary, 104)[0] == len(virtual.binary) + 32
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

    for binary_name in ('symbols_runtime.elf', 'symbols_rw.elf'):
        (BASE / binary_name).chmod(0o755)
        program = subprocess.run([str(BASE / binary_name)], capture_output=True, check=False)
        assert program.returncode == 42, (binary_name, program.returncode)
        assert program.stdout == b'Hi\n', (binary_name, program.stdout)
        ex += 1

    print(f'OK: {checked} verificaciones de bits, relocaciones, memoria virtual y errores; {ex} ELF ejecutados correctamente')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--rif-root', type=Path, required=True)
    parser.add_argument('--gram-root', type=Path, default=None)
    args = parser.parse_args()
    checks(args.rif_root, args.gram_root)
