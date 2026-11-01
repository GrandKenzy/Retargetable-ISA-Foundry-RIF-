"""Regresiones raw para el pack AMD64 bare metal, sin LLVM, GAS ni NASM.

Ejecutar: python tests/test_encoding.py --rif-root /ruta/RIF-main
El oráculo de bytes x86-64 es independiente de las tablas y reglas RIF.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import struct
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parents[1]
PROBE = BASE.parents[0] / 'probe' / 'probe_amd64'
REGS = 'rax rcx rdx rbx rsp rbp rsi rdi r8 r9 r10 r11 r12 r13 r14 r15'.split()
OPS_RR = {'movrr': b'\x8b','addrr': b'\x03','subrr': b'\x2b', 'cmprr': b'\x3b',
          'xorrr': b'\x33','andrr': b'\x23','orrr': b'\x0b',
          'testrr': b'\x85','imulrr': b'\x0f\xaf'}
OPS_IMM = {'addri': 0, 'orri':1, 'andri':4, 'subri':5,'xorri':6,'cmpri':7}
OPS_SHIFT = {'shlri':4,'shrri':5,'sarri':7}


def build_tests():
    lines = ['_start']
    oracle = bytearray()
    checks = {}
    def add(line, data, family):
        lines.append(line)
        oracle.extend(data)
        checks[family] = checks.get(family, 0) + 1

    for op, code in OPS_RR.items():
        for d in range(16):
            for s in range(16):
                rex = 0x48 | ((d>>3)<<2) | (s>>3)
                modrm = 0xc0 | ((d&7)<<3) | (s&7)
                add(f'{op} {REGS[d]}, {REGS[s]}', bytes((rex,))+code+bytes((modrm,)), 'reg-reg')

    for op, grp in OPS_IMM.items():
        for d in range(16):
            for val in (0, 127, 65535):
                rex = 0x48 | (d>>3)
                modrm = 0xc0 | (grp<<3) | (d&7)
                add(f'{op} {REGS[d]}, {val}', bytes((rex,0x81,modrm))+struct.pack('<I',val),'imm32')

    for op, grp in OPS_SHIFT.items():
        for d in range(16):
            for val in (0, 1, 63):
                rex=0x48 | (d>>3)
                modrm=0xc0 | (grp<<3) | (d&7)
                add(f'{op} {REGS[d]}, {val}', bytes((rex,0xc1,modrm,val)), 'shifts')

    for op,opcode in (('load64',0x8b),('store64',0x89),('lea64',0x8d)):
        for d in range(16):
            for b in range(16):
                disp=16 if (d+b)%2 else 256
                rex=0x48 | ((d>>3)<<2) | (b>>3)
                modrm=0x80 | ((d&7)<<3) | 4
                sib=0x20 | (b&7)
                add(f'{op} {REGS[d]}, {REGS[b]}, {disp}',
                    bytes((rex,opcode,modrm,sib))+struct.pack('<i',disp),'base+disp32')

    for op,opcode in (('loadx64',0x8b),('storex64',0x89),('leax64',0x8d)):
        # Covers all 16 GPR bases; 15 possible index regs (rsp excluded), all scales.
        for d in (0,7,8,15):
            for b in range(16):
                for ix in (1,7,9,12,15):
                    for scale in (1,2,4,8):
                        disp=(ix+b+d)*4
                        rex=0x48 | ((d>>3)<<2) | ((ix>>3)<<1) | (b>>3)
                        modrm=0x80 | ((d&7)<<3) | 4
                        sib=({1:0,2:1,4:2,8:3}[scale]<<6) | ((ix&7)<<3) | (b&7)
                        add(f'{op} {REGS[d]}, {REGS[b]}, {REGS[ix]}, {scale}, {disp}',
                            bytes((rex,opcode,modrm,sib))+struct.pack('<i',disp),'indexed-SIB')

    for d in range(16):
        rex=0x40 | (d>>3)
        add(f'push64 {REGS[d]}', bytes((rex,0x50+(d&7))), 'stack')
        add(f'pop64 {REGS[d]}', bytes((rex,0x58+(d&7))), 'stack')

    for d in range(16):
        v=0x100000000 + d
        add(f'movabs {REGS[d]}, {v}', bytes((0x48|(d>>3), 0xb8+(d&7))) + struct.pack('<Q',v), 'movabs')

    for op,opcode in [('jmp32',b'\xe9'),('je32',b'\x0f\x84'),('jne32',b'\x0f\x85'),('call32',b'\xe8')]:
        for disp in (0,1,256):
            add(f'{op} {disp}',opcode+struct.pack('<i',disp),'rel32')

    regs32 = 'eax ecx edx ebx esp ebp esi edi r8d r9d r10d r11d r12d r13d r14d r15d'.split()
    for op,opcode in [('mov32rr',0x8b),('add32rr',0x03),('sub32rr',0x2b),('cmp32rr',0x3b),('xor32rr',0x33)]:
        for d in range(16):
            for src in range(16):
                rex=0x40 | ((d>>3)<<2) | (src>>3)
                modrm=0xc0 | ((d&7)<<3) | (src&7)
                add(f'{op} {regs32[d]}, {regs32[src]}',bytes((rex,opcode,modrm)),'reg32-reg32')
    for d in range(16):
        imm=1234+d
        add(f'mov32imm {regs32[d]}, {imm}',bytes((0x40 | (d>>3),0xb8+(d&7)))+struct.pack('<I',imm),'imm32-mov')

    cc='o no b ae e ne be a s ns p np l ge le g'.split()
    for c,cond in enumerate(cc):
        add(f'jcc32 {cond}, 256',bytes((0x0f,0x80+c))+struct.pack('<i',256),'conditional-branch')
        for d in range(16):
            for src in range(16):
                rex=0x48 | ((d>>3)<<2) | (src>>3)
                modrm=0xc0 | ((d&7)<<3) | (src&7)
                add(f'cmovrr {cond}, {REGS[d]}, {REGS[src]}',bytes((rex,0x0f,0x40+c,modrm)),'cmov64')
            rex=0x40 | (d>>3)
            add(f'setcc {cond}, {REGS[d]}',bytes((rex,0x0f,0x90+c,0xc0|(d&7))),'setcc8')

    for op,data in [('nop',b'\x90'), ('ret',b'\xc3'),('leave',b'\xc9'),('cqo',b'\x48\x99')]:
        add(op,data,'single')
    return '\n'.join(lines)+'\n',bytes(oracle),checks


def run(rifroot,mir,out):
    return subprocess.run([sys.executable,'rif.py',str(BASE/'amd64.pack'),str(mir),'-o',str(out)],
                          cwd=rifroot, text=True, capture_output=True)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--rif-root',type=Path,required=True)
    args=ap.parse_args()
    mir,expected,counts=build_tests()
    (PROBE/'all_encodings.mir').write_text(mir)
    t0=time.monotonic()
    p=run(args.rif_root,PROBE/'all_encodings.mir',PROBE/'all_encodings.bin')
    if p.returncode:
        sys.exit('FALLO RIF: '+p.stdout+' '+p.stderr)
    image=(PROBE/'all_encodings.bin').read_bytes()
    # This input deliberately contains only raw instruction bytes. Host image
    # headers and execution are outside this target's contract.
    actual=image
    if actual!=expected:
        import itertools
        pos=next(itertools.chain((i for i,(x,y) in enumerate(zip(actual,expected)) if x!=y),[min(len(actual),len(expected))]))
        sys.exit(f'ERROR byte {pos}: esperado={expected[pos:pos+16].hex(" ")} real={actual[pos:pos+16].hex(" ")}')
    print('OK pack:', (BASE/'amd64.pack').stat().st_size, 'bytes')
    print('OK codificaciones:',sum(counts.values()),'instrucciones;',len(actual),'bytes;',f'{time.monotonic()-t0:.1f}s')
    for family,count in counts.items():
        print(f'  {family}: {count}')
    for invalid in ('loadx64 rax, rbx, rsp, 2, 16','loadx64 rax, rbx, rcx, 3, 16','addrr rax, notregister'):
        (PROBE/'negative.mir').write_text('_start\n'+invalid+'\n')
        p=run(args.rif_root,PROBE/'negative.mir',PROBE/'negative.bin')
        if p.returncode==0:
            sys.exit('ERROR debería fallar: '+invalid)
        print('OK rechazado:',invalid)
    print('OK AMD64 bare metal raw: sin formato de objeto ni llamadas de SO')

if __name__=='__main__':
    main()
