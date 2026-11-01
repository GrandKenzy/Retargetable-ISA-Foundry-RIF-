"""Small self-contained ARM7TDMI subset emulator for verifying this RIF-produced ROM.
NOT an mGBA replacement. Emulates only the instruction subset used by the demo,
MMIO VCOUNT timing approximation and Mode 3 VRAM stores.
"""
from pathlib import Path
import struct
import sys

ROOT=Path(__file__).resolve().parent
ROM=(ROOT/'rif_ball.gba').read_bytes()
ROMBASE=0x08000000
VRAMBASE=0x06000000
VRAM=bytearray(240*160*2)
REG=[0]*16
REG[13]=0x03007F00
PC=ROMBASE
MODE='ARM'
FLAGS={'z':False,'n':False,'v':False}
scanreads=0
screen_mode=None
stack={}
cycles=0
frames=[]


def memread(address,size):
 global scanreads
 if address==0x04000006 and size==2:
  val=(scanreads//16)%228
  scanreads+=1
  return val
 if ROMBASE<=address and address+size<=ROMBASE+len(ROM):
  return int.from_bytes(ROM[address-ROMBASE:address-ROMBASE+size], 'little')
 if VRAMBASE<=address and address+size<=VRAMBASE+len(VRAM):
  return int.from_bytes(VRAM[address-VRAMBASE:address-VRAMBASE+size],'little')
 if address==0x03007EFC and size==4:
  return stack.get(address,0)
 if address in stack:
  return stack[address]
 raise ValueError(f'Unknown read at {address:#x}, size {size}, PC {PC:#x}')


def memwrite(address,size,value):
 global screen_mode
 if address==0x04000000 and size==2:
  screen_mode=value
  return
 if VRAMBASE<=address and address+size<=VRAMBASE+len(VRAM):
  VRAM[address-VRAMBASE:address-VRAMBASE+size] = value.to_bytes(size,'little')
  return
 if 0x03000000<=address<0x03008000:
  stack[address]=value
  return
 raise ValueError(f'Unknown write {address:#x}, size {size}, value={value:#x}, PC {PC:#x}')


def s32(x):
 x&=0xFFFFFFFF
 return x if x<0x80000000 else x-0x100000000


def flagcmp(a,b):
 a=s32(a);b=s32(b)
 FLAGS['z']=a==b
 FLAGS['n']=a<b
 FLAGS['v']=False


def cond_ok(cond):
 if cond==14:return True
 if cond==0:return FLAGS['z']
 if cond==1:return not FLAGS['z']
 if cond==10:return not FLAGS['n']
 if cond==11:return FLAGS['n']
 if cond==13:return FLAGS['n'] or FLAGS['z']
 raise ValueError(f'Unhandled cond {cond}')


def memreg(n, currpc):
 return currpc+8 if n==15 else REG[n]


def step():
 global PC, MODE, cycles
 cycles+=1
 cur=PC
 if MODE=='THUMB':
  half=memread(cur,2)
  if (half&0xF800)==0x2000:
   rd=(half>>8)&7; REG[rd]=half&255; PC+=2;return
  if half==0x4770:
   target=REG[14]; MODE='THUMB' if target&1 else 'ARM'; PC=target&~1;return
  raise ValueError(f'Unhandled Thumb {half:#x} at {PC:#x}')
 w=memread(cur,4)
 cond=w>>28
 if not cond_ok(cond):
  PC+=4;return
 if (w&0x0FFFFFF0)==0x012FFF10:
  target=memreg(w&15,cur)
  MODE='THUMB' if target&1 else 'ARM'; PC=target&~1;return
 if (w&0x0E000000)==0x0A000000:
  delta=(w&0xFFFFFF)<<2
  if delta&(1<<25): delta-=1<<26
  if (w>>24)&1: REG[14]=cur+4
  PC=cur+8+delta;return
 if w==0xE92D4000:
  REG[13]-=4;memwrite(REG[13],4,REG[14]);PC+=4;return
 if w==0xE8BD4000:
  REG[14]=memread(REG[13],4); REG[13]+=4;PC+=4;return
 if ((w>>25)&7)==0 and ((w>>4)&0xF)==0xB:
  rn=(w>>16)&15;rd=(w>>12)&15
  off=((w>>8)&0xf)*16+(w&15)
  P=(w>>24)&1; U=(w>>23)&1; L=(w>>20)&1
  base=memreg(rn,cur)
  address=base+(off if U else -off) if P else base
  if L:REG[rd]=memread(address,2)
  else:memwrite(address,2,REG[rd]&0xffff)
  if not P:REG[rn]=base+(off if U else -off)
  PC+=4;return
 if ((w>>26)&3)==1:
  # single data transfer LDR literal or LDRB immediate
  rn=(w>>16)&15; rd=(w>>12)&15; off=w&0xFFF
  P=(w>>24)&1; U=(w>>23)&1; B=(w>>22)&1; L=(w>>20)&1
  assert P and L
  addr=memreg(rn,cur)+(off if U else -off)
  REG[rd]=memread(addr,1 if B else 4)
  PC+=4;return
 if ((w>>26)&3)==0:
  # data processing immediate/ shifted register
  opcode=(w>>21)&15;S=(w>>20)&1;rn=(w>>16)&15;rd=(w>>12)&15
  if (w>>25)&1:
   shift=((w>>8)&15)*2
   val=w&255
   op2=((val>>shift)|(val<<(32-shift)))&0xFFFFFFFF if shift else val
  else:
   assert not (w&16),f'Unsupported register shift {w:08x}'
   shift=(w>>7)&31
   ty=(w>>5)&3
   assert ty==0
   op2=(memreg(w&15,cur)<<shift)&0xFFFFFFFF
  lhs=memreg(rn,cur)
  if opcode==2: result=(lhs-op2)&0xFFFFFFFF
  elif opcode==3: result=(op2-lhs)&0xFFFFFFFF
  elif opcode==4: result=(lhs+op2)&0xFFFFFFFF
  elif opcode==10: result=(lhs-op2)&0xFFFFFFFF
  elif opcode==12: result=lhs|op2
  elif opcode==13: result=op2
  else:raise ValueError(f'Unhandled dp op={opcode}, w={w:#x},PC {PC:#x}')
  if opcode==10 or S: flagcmp(lhs,op2)
  if opcode!=10:
   REG[rd]=result
  PC+=4;return
 raise ValueError(f'Unhandled ARM {w:#x} at {PC:#x}')


def run():
 global PC
 from build import build
 a=build()
 assert ROM[0:4]==struct.pack('<I',0xEA00002E)
 PC=ROMBASE
 frame_pc=ROMBASE+a.labels['frame']
 previous_pc=None
 redraw_return=ROMBASE+a.labels['draw_ball']+0x4c
 last_b=ROMBASE+a.labels['draw_ball']-4
 while len(frames)<4 and cycles<1500000:
  if PC==frame_pc and previous_pc in (last_b, ROMBASE+a.labels['draw_ball']+0x4c):
   x,y=REG[7],REG[8]
   white=sum(1 for i in range(0,len(VRAM),2) if VRAM[i:i+2]==b'\xff\x7f')
   green=sum(1 for i in range(0,len(VRAM),2) if VRAM[i:i+2]==b'\xe0\x03')
   assert (green,white)==(38400-76,76), (green,white,x,y)
   frames.append((x,y,white))
   print(f'Frame {len(frames)}: x={x} y={y} white={white} green={green} cycles={cycles}, scanline={(scanreads//16)%228}')
  previous_pc=PC
  step()
 assert len(frames)==4, f'Stalled after {cycles} steps; PC={PC:#x}, MODE={MODE}'
 assert frames==[(100,60,76),(102,61,76),(104,62,76),(106,63,76)],frames
 assert screen_mode==0x403, screen_mode
 # Preview of the last emulated VRAM frame; not a real emulator screenshot.
 from PIL import Image
 img=Image.new('RGB',(240,160))
 pixels=[]
 for i in range(0,len(VRAM),2):
  v=int.from_bytes(VRAM[i:i+2],'little')
  pixels.append(((v&31)*255//31,((v>>5)&31)*255//31,((v>>10)&31)*255//31))
 img.putdata(pixels)
 img.resize((960,640),Image.Resampling.NEAREST).save(ROOT/'preview_simulated.png')
 print('CPU subset simulation PASS; Mode3=',hex(screen_mode),'preview_simulated.png')

if __name__=='__main__':run()
