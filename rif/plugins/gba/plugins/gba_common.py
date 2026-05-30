from __future__ import annotations

from typing import Any

from rif import EmitChunk, EmitInstruction, Expr, Line, RuleIndicator


GBA_ROM_BASE = 0x08000000
ENTRY_OFFSET = 0x000000C0
FRAME_OFFSET = 0x00000100
ROM_SIZE = 0x00020000
SCREEN_W = 240
SCREEN_H = 160

BLACK = 0x0000
WHITE = 0x7FFF
GREEN = 0x03E0
COLORS = {
    "black": BLACK,
    "white": WHITE,
    "green": GREEN,
}

NINTENDO_LOGO = bytes.fromhex(
    "24 FF AE 51 69 9A A2 21 3D 84 82 0A 84 E4 09 AD "
    "11 24 8B 98 C0 81 7F 21 A3 52 BE 19 93 09 CE 20 "
    "10 46 4A 4A F8 27 31 EC 58 C7 E8 33 82 E3 CE BF "
    "85 F4 DF 94 CE 4B 09 C1 94 56 8A C0 13 72 A7 FC "
    "9F 84 4D 73 A3 CA 9A 61 58 97 A3 27 FC 03 98 76 "
    "23 1D C7 61 03 04 AE 56 BF 38 84 00 40 A7 0E FD "
    "FF 52 FE 03 6F 95 30 F1 97 FB C0 85 60 D6 80 25 A9 "
    "63 BE 03 01 4E 38 E2 F9 A2 34 FF BB 3E 03 44 78 00 "
    "90 CB 88 11 3A 94 65 C0 7C 63 87 F0 3C AF D6 25 "
    "E4 8B 38 0A AC 72 21 D4 F8 07"
)

FONT_5X7 = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    " ": ["00000", "00000", "00000", "00000", "00000", "00000", "00000"],
}


def u32(value: int) -> bytes:
    return int(value & 0xFFFFFFFF).to_bytes(4, "little")


def arm_b(src_addr: int, dst_addr: int, cond: int = 0xE) -> int:
    offset = (dst_addr - (src_addr + 8)) >> 2
    if not -(1 << 23) <= offset < (1 << 23):
        raise ValueError("branch fuera de rango")
    return (cond << 28) | 0x0A000000 | (offset & 0x00FFFFFF)


def arm_ldr_literal(rd: int, pc_addr: int, literal_addr: int) -> int:
    offset = literal_addr - (pc_addr + 8)
    if not 0 <= offset <= 0xFFF:
        raise ValueError("literal pool fuera de rango")
    return 0xE59F0000 | (rd << 12) | offset


def arm_strh_pre(rd: int, rn: int, imm: int = 0) -> int:
    return 0xE1C000B0 | (rn << 16) | (rd << 12) | ((imm & 0xF0) << 4) | (imm & 0x0F)


def arm_ldrh_post(rd: int, rn: int, imm: int = 0) -> int:
    return 0xE0D000B0 | (rn << 16) | (rd << 12) | ((imm & 0xF0) << 4) | (imm & 0x0F)


def arm_strh_post(rd: int, rn: int, imm: int = 0) -> int:
    return 0xE0C000B0 | (rn << 16) | (rd << 12) | ((imm & 0xF0) << 4) | (imm & 0x0F)


def arm_subs_imm(rd: int, rn: int, imm: int) -> int:
    return 0xE2500000 | (rn << 16) | (rd << 12) | (imm & 0xFF)


def make_entry_code() -> bytes:
    base = GBA_ROM_BASE + ENTRY_OFFSET
    literal_base = base + 44
    loop_addr = base + 24
    words = [
        arm_ldr_literal(4, base + 0, literal_base + 0),
        arm_ldr_literal(5, base + 4, literal_base + 4),
        arm_strh_pre(5, 4),
        arm_ldr_literal(0, base + 12, literal_base + 8),
        arm_ldr_literal(1, base + 16, literal_base + 12),
        arm_ldr_literal(2, base + 20, literal_base + 16),
        arm_ldrh_post(3, 0, 2),
        arm_strh_post(3, 1, 2),
        arm_subs_imm(2, 2, 1),
        arm_b(base + 36, loop_addr, cond=0x1),
        arm_b(base + 40, base + 40),
        0x04000000,
        0x00000403,
        GBA_ROM_BASE + FRAME_OFFSET,
        0x06000000,
        SCREEN_W * SCREEN_H,
    ]
    return b"".join(u32(word) for word in words)


def make_entry_thumb_code() -> bytes:
    base = GBA_ROM_BASE + ENTRY_OFFSET
    literal_base = base + 20
    words = [
        arm_ldr_literal(4, base + 0, literal_base + 0),
        arm_ldr_literal(5, base + 4, literal_base + 4),
        arm_strh_pre(5, 4),
        arm_ldr_literal(0, base + 12, literal_base + 8),
        0xE12FFF10, # BX R0
        0x04000000,
        0x00000403,
        base + 32 + (240 * 160 * 2) + 1, # address de la instruccion siguiente al frame + 1 para modo Thumb
    ]
    return b"".join(u32(word) for word in words)

def make_checksum_block(text: str) -> bytes:
    block = bytearray(32)
    block[0x00:0x0C] = text.upper().encode("ascii", "ignore")[:12].ljust(12, b" ")
    block[0x0C:0x10] = b"RIF0"
    block[0x10:0x12] = b"00"
    block[0x12] = 0x96
    block[0x13] = 0x00
    block[0x14] = 0x00
    block[0x1C] = 0x00
    block[0x1D] = (-(sum(block[:0x1D]) + 0x19)) & 0xFF
    return bytes(block)


def make_frame(text: str, background: int = GREEN, foreground: int = BLACK) -> bytes:
    frame = bytearray()
    for _ in range(SCREEN_W * SCREEN_H):
        frame.extend(int(background).to_bytes(2, "little"))
    x = max(0, (SCREEN_W - len(text) * 18) // 2)
    draw_text(frame, text.upper(), x=x, y=67, scale=3, color=foreground)
    return bytes(frame)


def draw_text(frame: bytearray, text: str, x: int, y: int, scale: int, color: int) -> None:
    cursor_x = x
    for ch in text:
        glyph = FONT_5X7.get(ch.upper(), FONT_5X7[" "])
        for gy, row in enumerate(glyph):
            for gx, bit in enumerate(row):
                if bit != "1":
                    continue
                for sy in range(scale):
                    py = y + gy * scale + sy
                    if not 0 <= py < SCREEN_H:
                        continue
                    for sx in range(scale):
                        px = cursor_x + gx * scale + sx
                        if not 0 <= px < SCREEN_W:
                            continue
                        off = (py * SCREEN_W + px) * 2
                        frame[off:off + 2] = int(color).to_bytes(2, "little")
        cursor_x += 6 * scale


def color(value: str, default: int) -> int:
    return COLORS.get(value.lower(), default)


def args() -> list[str]:
    Line.Advance()
    pack = [clean(item) for item in Line.Unpack(",")]
    Line.toks.clear()
    Line.expects(" ", "\n")
    return [item for item in pack if item]


def clean(value: Any) -> str:
    if hasattr(value, "value"):
        value = value.value
    return str(value).strip()


def emit_bytes(data: bytes):
    chunks = tuple(
        EmitChunk(kind="byte", value=f"{byte:08b}", width=8, byte=byte)
        for byte in data
    )
    return Expr(["emit_bits_exact", EmitInstruction(
        mode="bits",
        chunks=chunks,
        rule_name=RuleIndicator.current,
        line=getattr(Line, "line", None),
        requires_byte=True,
    )])
