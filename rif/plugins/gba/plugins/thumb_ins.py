from __future__ import annotations

from rif import Err
from rif.plugins.gba.plugins.gba_common import args, emit_bytes

def main():
    pack = args()
    if len(pack) < 1:
        return Err("thumb_ins requiere al menos el tipo de instruccion")
    
    ins_type = pack[0].lower()
    
    try:
        if ins_type == "store":
            rd = int(pack[1]) & 0x7
            imm = int(pack[2]) & 0xFF
            opcode = (0b00100 << 11) | (rd << 8) | imm
        elif ins_type == "add":
            rd = int(pack[1]) & 0x7
            rs = int(pack[2]) & 0x7
            rn = int(pack[3]) & 0x7
            opcode = (0b0001100 << 9) | (rn << 6) | (rs << 3) | rd
        elif ins_type == "or":
            rd = int(pack[1]) & 0x7
            rs = int(pack[2]) & 0x7
            opcode = (0b0100001100 << 6) | (rs << 3) | rd
        elif ins_type == "and":
            rd = int(pack[1]) & 0x7
            rs = int(pack[2]) & 0x7
            opcode = (0b0100000000 << 6) | (rs << 3) | rd
        elif ins_type == "cmp":
            rd = int(pack[1]) & 0x7
            rs = int(pack[2]) & 0x7
            opcode = (0b0100001010 << 6) | (rs << 3) | rd
        elif ins_type == "neg":
            rd = int(pack[1]) & 0x7
            rs = int(pack[2]) & 0x7
            opcode = (0b0100001001 << 6) | (rs << 3) | rd
        elif ins_type == "strh":
            rd = int(pack[1]) & 0x7
            rb = int(pack[2]) & 0x7
            ro = int(pack[3]) & 0x7
            opcode = (0b0101001 << 9) | (ro << 6) | (rb << 3) | rd
        elif ins_type == "ldrh":
            rd = int(pack[1]) & 0x7
            rb = int(pack[2]) & 0x7
            ro = int(pack[3]) & 0x7
            opcode = (0b0101101 << 9) | (ro << 6) | (rb << 3) | rd
        elif ins_type == "str":
            rd = int(pack[1]) & 0x7
            rb = int(pack[2]) & 0x7
            ro = int(pack[3]) & 0x7
            opcode = (0b0101000 << 9) | (ro << 6) | (rb << 3) | rd
        else:
            return Err(f"thumb_ins: instruccion no soportada '{ins_type}'")
            
        return emit_bytes(opcode.to_bytes(2, "little"))
    except ValueError:
        return emit_bytes(b"")
    except Exception as exc:
        return Err(f"thumb_ins error: {exc}")

def _start():
    return main()
