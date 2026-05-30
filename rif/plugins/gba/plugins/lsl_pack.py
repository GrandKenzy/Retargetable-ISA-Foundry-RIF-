from __future__ import annotations

from rif import Err
from rif.plugins.gba.plugins.gba_common import args, emit_bytes

def main():
    pack = args()
    if len(pack) != 3:
        return Err("lsl_pack requiere 3 argumentos: rd, rs, imm")
    
    try:
        rd = int(pack[0]) & 0x7
        rs = int(pack[1]) & 0x7
        imm = int(pack[2]) & 0x1F
        
        # Opcode LSL: 000_00_imm5_Rs_Rd
        # = (0 << 13) | (imm << 6) | (rs << 3) | rd
        opcode = (imm << 6) | (rs << 3) | rd
        
        # Emitir en little endian (byte bajo, byte alto)
        return emit_bytes(opcode.to_bytes(2, "little"))
    except ValueError:
        return emit_bytes(b"")
    except Exception as exc:
        return Err(str(exc))

def _start():
    return main()
