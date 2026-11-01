"""Long-run bounce test in the small ARM7TDMI interpreter (NOT real GBA hardware)."""
from pathlib import Path
from PIL import Image
import verify_cpu as emu
from build import build

asm=build()
frame_pc=emu.ROMBASE+asm.labels['frame']
last_b=emu.ROMBASE+asm.labels['draw_ball']-4
bx_return=emu.ROMBASE+asm.labels['draw_ball']+0x4c

# 300 frames: bounces across left/right and upper/lower borders.
positions=[]
frames=[]
prev=None
max_steps=5_000_000
while len(positions)<300 and emu.cycles<max_steps:
    if emu.PC==frame_pc and prev in (last_b,bx_return):
        x,y=emu.REG[7],emu.REG[8]
        assert 0<=x<=230 and 0<=y<=150,(len(positions),x,y)
        positions.append((x,y,emu.REG[9],emu.REG[10]))
        if len(positions)%10==1 and len(frames)<20:
            # Emulated VRAM snapshot, for an illustrative GIF only.
            im=Image.new('RGB',(240,160))
            px=[]
            for i in range(0,len(emu.VRAM),2):
                val=int.from_bytes(emu.VRAM[i:i+2],'little')
                px.append(((val&31)*255//31,((val>>5)&31)*255//31,((val>>10)&31)*255//31))
            im.putdata(px)
            frames.append(im.resize((480,320),Image.Resampling.NEAREST))
    prev=emu.PC
    emu.step()
assert len(positions)==300, (len(positions),emu.cycles,hex(emu.PC))
# Ensure actual velocity direction changes due to collisions.
x_signs=set(1 if emu.s32(dx)>0 else -1 for _,_,dx,_ in positions)
y_signs=set(1 if emu.s32(dy)>0 else -1 for _,_,_,dy in positions)
assert x_signs=={1,-1} and y_signs=={1,-1}
assert emu.screen_mode==0x403
assert sum(emu.VRAM[i:i+2]==b'\xff\x7f' for i in range(0,len(emu.VRAM),2))==76
if frames:
    frames[0].save('preview_bouncing_simulated.gif',save_all=True,append_images=frames[1:],duration=100,loop=0,optimize=True)
print(f'PASS: {len(positions)} frames; {emu.cycles} ARM/Thumb instructions; x range {min(p[0] for p in positions)}..{max(p[0] for p in positions)}; y range {min(p[1] for p in positions)}..{max(p[1] for p in positions)}; x direction {x_signs}, y direction {y_signs}')
