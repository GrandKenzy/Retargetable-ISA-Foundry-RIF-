"""Builds a small GBA game using RIF for ROM emission.

The ARM7TDMI instruction encoder below uses bitfield formulas (no C compiler,
LLVM, external assembler or assembler binary is required). RIF emits the words,
Thumb variant and the geometry/data into the finalized cartridge image.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
# Override with RIF_PY=/path/to/rif.py or pass rif.py as the first argument.
RIF = Path(os.environ.get('RIF_PY', str(ROOT.parent / 'RIF-main' / 'rif.py')))
if len(sys.argv) > 1 and sys.argv[1].endswith('rif.py'):
    RIF = Path(sys.argv[1]).resolve()
ROM_BASE = 0x08000000
HEADER_SIZE = 0xC0
COND = {'eq':0, 'ne':1, 'cs':2, 'cc':3, 'mi':4,'pl':5, 'vs':6,'vc':7,'hi':8,'ls':9,'ge':10,'lt':11,'gt':12,'le':13,'al':14}
OP = {'and':0,'eor':1,'sub':2,'rsb':3,'add':4,'adc':5,'sbc':6,'rsc':7,'tst':8,'teq':9,'cmp':10,'cmn':11,'orr':12,'mov':13,'bic':14,'mvn':15}


def imm12(value: int) -> int:
    value &= 0xFFFFFFFF
    for rot in range(16):
        # ARM constant immediate = ror32(imm8, rot*2)
        shift = rot * 2
        candidate = ((value << shift) | (value >> (32-shift))) & 0xFFFFFFFF if shift else value
        if candidate <= 255:
            return (rot << 8) | candidate
    raise ValueError(f'ARM immediate not representable: 0x{value:X}')


def data_proc(opcode: str, rd: int, rn: int, op2: int, *, immediate=False, s=False, cond='al') -> int:
    assert 0 <= rd < 16 and 0 <= rn < 16
    assert cond in COND and opcode in OP
    return ((COND[cond]<<28) | ((1 if immediate else 0)<<25) | (OP[opcode]<<21) | ((1 if s else 0)<<20) | (rn<<16) | (rd<<12) | (imm12(op2) if immediate else op2))


def reg_operand(rm: int, shift=0, shift_kind=0):
    assert 0 <= rm < 16 and 0 <= shift < 32
    return (shift<<7) | (shift_kind<<5) | rm


def halfmem(rd: int, rn: int, *, load=False, offset=0, pre=True, up=True):
    assert 0 <= offset <= 255
    return 0xE00000B0 | (int(pre)<<24) | (int(up)<<23) | (1<<22) | (int(load)<<20) | (rn<<16) | (rd<<12) | ((offset>>4)<<8) | (offset&0xF)


def byte_load(rd: int, rn: int, offset=0):
    assert 0 <= offset <= 4095
    return 0xE5D00000 | (rn<<16) | (rd<<12) | offset


@dataclass
class Record:
    kind: str
    val: int
    comment: str = ''
    name: str = ''

    @property
    def length(self):
        return {'arm32':4, 'mov':4, 'byte':1, 'thumb_mov':2, 'thumb_bx':2}[self.kind]


class Asm:
    def __init__(self):
        self.rom_pos = HEADER_SIZE
        self.records: list[Record] = []
        self.labels = {}
        self.fixups = []

    def label(self, name):
        if name in self.labels:
            raise ValueError(f'duplicate label: {name}')
        self.labels[name] = self.rom_pos

    def record(self, kind, val, comment='', name=''):
        rec = Record(kind, val, comment, name)
        self.records.append(rec)
        self.rom_pos += rec.length
        return rec

    def w(self, val, comment=''):
        return self.record('arm32', val & 0xFFFFFFFF, comment)

    def movi(self, rd: int, imm: int, comment=''):
        assert imm < 256
        return self.record('mov', imm, comment, name=f'r{rd}')

    def movr(self, rd, rm, shift=0):
        return self.w(data_proc('mov', rd, 0, reg_operand(rm,shift)))

    def dpr(self, op, rd, rn, rm, shift=0, s=False, cond='al'):
        return self.w(data_proc(op, rd, rn, reg_operand(rm,shift),s=s,cond=cond))

    def dpi(self, op, rd, rn, imm, s=False, cond='al'):
        return self.w(data_proc(op,rd,rn,imm,immediate=True,s=s,cond=cond))

    def cmpi(self, rn, imm, cond='al'):
        return self.dpi('cmp',0,rn,imm,s=True,cond=cond)

    def ldr_literal(self, rd, name: str):
        rec=self.w(0, f'ldr r{rd}, [literal {name}]')
        self.fixups.append(('ldr',rec,self.rom_pos-4,name,rd))
        return rec

    def branch(self, name: str, *, cond='al', link=False):
        rec=self.w(0, f'{"bl" if link else "b"}{cond if cond!="al" else ""} {name}')
        self.fixups.append(('branch',rec,self.rom_pos-4,name,cond,link))
        return rec

    def arm_bx(self, rm):
        self.w(0xE12FFF10 | rm)

    def raw_byte(self, val, comment=''):
        assert 0 <= val < 256
        self.record('byte',val,comment)

    def align(self, alignment):
        while self.rom_pos%alignment:
            self.raw_byte(0,'alignment padding')

    def literal_value(self, name, value: int):
        self.label(name)
        self.w(value, f'literal 0x{value:08X}')

    def literal_label(self, name, target, plus=0):
        self.label(name)
        rec=self.w(0,f'literal @{target}+{plus}')
        self.fixups.append(('literal_label',rec,target,plus))

    def resolve(self):
        for f in self.fixups:
            if f[0]=='ldr':
                _,rec,loc,name,rd=f
                target=self.labels[name]
                delta=target-(loc+8)
                assert abs(delta)<=4095, (name,delta)
                rec.val=0xE51F0000|(int(delta>=0)<<23)|(rd<<12)|abs(delta)
            elif f[0]=='branch':
                _,rec,loc,name,cond,link=f
                delta=self.labels[name]-(loc+8)
                assert delta%4==0 and -(1<<25)<=delta<(1<<25), (name,delta)
                rec.val=(COND[cond]<<28) | (0b101<<25) | (int(link)<<24) | ((delta//4)&0xFFFFFF)
            elif f[0]=='literal_label':
                _,rec,target,plus=f
                rec.val=ROM_BASE+self.labels[target]+plus
            else:
                raise AssertionError(f)

    def mir(self):
        lines=['; GBA 240x160 Mode 3 with moving circle: RIF emits everything below.']
        loc=HEADER_SIZE
        for rec in self.records:
            if rec.comment:
                lines.append(f'; ROM 0x{loc:04x}: {rec.comment}')
            if rec.kind=='arm32':
                lines.append(f'arm32 {rec.val}')
            elif rec.kind=='mov':
                lines.append(f'arm_mov_imm {rec.name}, {rec.val}')
            elif rec.kind=='byte':
                lines.append(f'byte {rec.val}')
            elif rec.kind=='thumb_mov':
                lines.extend(['ENTER_thumb',f'thumb_mov_imm {rec.name}, {rec.val}','EXIT_thumb'])
            elif rec.kind=='thumb_bx':
                lines.extend(['ENTER_thumb','thumb_bx_lr','EXIT_thumb'])
            else:
                raise ValueError(rec.kind)
            loc+=rec.length
        return '\n'.join(lines)+'\n'


def build():
    a=Asm()
    # ARM entry point lives at file offset 0xC0. The cartridge header branches here.
    # ARM7TDMI interworking into Thumb and back to ARM via BX.
    a.ldr_literal(0, 'thumb_addr')
    a.dpi('add',14,15,0)       # add lr, pc, #0 -> continuation after BX
    a.arm_bx(0)                 # switch to Thumb (literal has bit0=1)
    a.branch('after_thumb_literal')
    a.literal_label('thumb_addr','thumb_init',1)
    a.label('after_thumb_literal')
    a.dpi('orr',1,1,0x400)     # r1=3 from Thumb -> DISPCNT=0x0403 (Mode3+BG2)
    a.ldr_literal(0,'dispcnt')
    a.w(halfmem(1,0), 'strh r1,[r0] set display mode 3')
    a.ldr_literal(4,'vram')
    a.ldr_literal(11,'vcount')
    a.ldr_literal(5,'green')
    a.ldr_literal(6,'white')
    a.movi(7,100,'left x=100')
    a.movi(8,60,'top y=60')
    a.movi(9,2,'dx=2')
    a.movi(10,1,'dy=1')

    # Fill all 240*160 16-bit Mode 3 pixels with BGR555 green.
    a.movr(0,4)
    a.movi(1,150)
    a.movr(1,1,8)             # r1=150<<8 = 38,400 pixels
    a.label('clear_screen')
    a.w(halfmem(5,0,pre=False,offset=2),'strh r5,[r0],#2')
    a.dpi('sub',1,1,1,s=True)
    a.branch('clear_screen',cond='ne')

    a.movr(0,6)
    a.branch('draw_ball', link=True)

    a.label('frame')
    a.label('wait_visible')
    a.w(halfmem(0,11,load=True),'ldrh r0,[VCOUNT]')
    a.cmpi(0,160)
    a.branch('wait_visible',cond='ge')
    a.label('wait_vblank')
    a.w(halfmem(0,11,load=True))
    a.cmpi(0,160)
    a.branch('wait_vblank',cond='lt')
    # Erase old ball with green, then update bounds/velocity and redraw in white.
    a.movr(0,5)
    a.branch('draw_ball',link=True)
    a.dpr('add',7,7,9)
    a.dpr('add',8,8,10)
    a.cmpi(7,230)
    a.dpi('rsb',9,9,0,cond='ge')
    a.cmpi(7,0)
    a.dpi('rsb',9,9,0,cond='le')
    a.cmpi(8,150)
    a.dpi('rsb',10,10,0,cond='ge')
    a.cmpi(8,0)
    a.dpi('rsb',10,10,0,cond='le')
    a.movr(0,6)
    a.branch('draw_ball',link=True)
    a.branch('frame')

    # Paint a filled, rounded 10x10 ball using table-derived spans.
    # r0=color r7=x r8=y r4=vram; clobbers r1,r2,r3,r12, keeps caller LR.
    a.label('draw_ball')
    a.w(0xE92D4000,'push {lr}')
    a.movi(1,0)
    a.label('row_loop')
    a.dpr('add',2,8,1)           # y + row
    a.movr(3,2,8)                # y*256
    a.dpr('sub',2,3,2,4)          # y*240
    a.dpr('add',2,2,7)            # + x
    a.ldr_literal(12,'span_address')
    a.dpr('add',3,12,1,1)         # r3=&span[row*2]
    a.w(byte_load(12,3),'ldrb r12,[r3] start-offset')
    a.dpr('add',2,2,12)
    a.w(byte_load(3,3,1),'ldrb r3,[r3,#1] count')
    a.dpr('add',2,4,2,1)          # VRAM + 2*offset
    a.label('pixels')
    a.w(halfmem(0,2,pre=False,offset=2),'strh color,[cursor],#2')
    a.dpi('sub',3,3,1,s=True)
    a.branch('pixels',cond='ne')
    a.dpi('add',1,1,1)
    a.cmpi(1,10)
    a.branch('row_loop',cond='lt')
    a.w(0xE8BD4000,'pop {lr}')
    a.arm_bx(14)

    # Data source for the filled circle. These 20 bytes are emitted by RIF byte rules.
    a.label('span_table')
    spans=[(3,4),(2,6),(1,8),(0,10),(0,10),(0,10),(0,10),(1,8),(2,6),(3,4)]
    for i,(start, count) in enumerate(spans):
        a.raw_byte(start, f'ball row {i}: start={start}, width={count}')
        a.raw_byte(count)
    # Thumb variant at the tail, called by ARM entry using real BX state switch.
    a.label('thumb_init')
    a.record('thumb_mov',3,'Thumb movs r1,#3', name='r1')
    a.record('thumb_bx',0,'Thumb bx lr to ARM state')
    a.align(4)
    # Literal constants; addresses point to GBA MMIO and palette values.
    for name, val in [('dispcnt',0x04000000),('vram',0x06000000),('vcount',0x04000006),('green',0x03E0),('white',0x7FFF)]:
        a.literal_value(name,val)
    a.literal_label('span_address', 'span_table')
    a.resolve()

    mir = '::RIF_INSERT FILE "gba_header.bin" SECTION text\n' + a.mir()
    (ROOT/'main.asm').write_text(mir)
    (ROOT/'labels.json').write_text(json.dumps({name:hex(ROM_BASE+offset) for name,offset in a.labels.items()},indent=2)+'\n')
    return a


def validate(rom:bytes,a:Asm):
    assert rom[:4]==struct.pack('<I',0xEA00002E)
    assert rom[0xB2]==0x96
    assert (sum(rom[0xA0:0xBE])+0x19)&0xFF==0
    assert rom[0xC0:0xC4]==struct.pack('<I',a.records[0].val)
    assert len(rom)==a.rom_pos
    pos=HEADER_SIZE
    for rec in a.records:
        if rec.kind=='arm32': expected=struct.pack('<I',rec.val)
        elif rec.kind=='mov': expected=struct.pack('<I',data_proc('mov',int(rec.name[1:]),0,rec.val,immediate=True))
        elif rec.kind=='byte': expected=bytes([rec.val])
        elif rec.kind=='thumb_mov': expected=struct.pack('<H',0x2000+(int(rec.name[1:])<<8)+rec.val)
        elif rec.kind=='thumb_bx': expected=bytes.fromhex('70 47')
        else: raise AssertionError(rec.kind)
        if rom[pos:pos+rec.length]!=expected:
            raise AssertionError(f'RIF mismatch at 0x{pos:X} for {rec}: actual {rom[pos:pos+rec.length].hex()}, expected {expected.hex()}')
        pos+=rec.length
    assert pos==len(rom)
    assert a.labels['thumb_init']%2==0
    # Interworking literal address and labels must point within ROM
    initlit=struct.unpack_from('<I',rom,a.labels['thumb_addr'])[0]
    assert initlit==ROM_BASE+a.labels['thumb_init']+1
    print('ROM VALID',len(rom),'bytes; ',len(a.records),'RIF records; Thumb entry',hex(initlit))
    print('GBA header checksum 0x%02X, jump to 0x%08X'%(rom[0xBD],ROM_BASE+0xC0))
    print('Data rows at',hex(ROM_BASE+a.labels['span_table']))


if __name__=='__main__':
    a=build()
    if '--no-build' not in sys.argv:
        subprocess.run([sys.executable,str(RIF),'--pack','main.rif','-o','gba.pack'],cwd=ROOT,check=True)
        subprocess.run([sys.executable,str(RIF),'gba.pack','main.asm','-o','rif_ball.gba'],cwd=ROOT,check=True)
        rom=(ROOT/'rif_ball.gba').read_bytes()
        validate(rom,a)
        # Optional padded image for loaders expecting a larger cartridge file.
        (ROOT/'rif_ball_256k.gba').write_bytes(rom + b'\xFF'*(256*1024-len(rom)))
