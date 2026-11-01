from __future__ import annotations

import unittest

from MIR import BitBuffer, BitEmitter, BitField, BitLayout


class BitBufferTests(unittest.TestCase):
    def test_msb_fields_pack_across_byte_boundaries(self) -> None:
        buffer = BitBuffer()
        buffer.append_bits(0b1010, 4)
        span = buffer.append_bits(0b11110000, 8)

        self.assertEqual(buffer.bit_length, 12)
        self.assertEqual(buffer.to_bytes(), b"\xaf\x00")
        self.assertEqual(buffer.read_bits(0, 4), 0b1010)
        self.assertEqual(buffer.query(span).bits, (1, 1, 1, 1, 0, 0, 0, 0))

    def test_lsb_layout_controls_physical_bit_order(self) -> None:
        buffer = BitBuffer(BitLayout(bit_order="lsb"))
        span = buffer.append_bits(0b1011, 4)

        self.assertEqual(buffer.to_bytes(), b"\x0b")
        self.assertEqual(buffer.read_bits(span.offset, span.width), 0b1011)
        self.assertEqual(buffer.query(span).bits, (1, 1, 0, 1))

    def test_byte_order_is_separate_from_bit_order(self) -> None:
        little = BitBuffer(BitLayout(byte_order="little"))
        little.append_bits(0, 16)
        little.write_int(0, 0x1234, 16)

        big = BitBuffer(BitLayout(byte_order="big"))
        big.append_bits(0, 16)
        big.write_int(0, 0x1234, 16)

        self.assertEqual(little.to_bytes(), b"\x34\x12")
        self.assertEqual(big.to_bytes(), b"\x12\x34")
        self.assertEqual(little.read_int(0, 16), 0x1234)
        self.assertEqual(big.read_int(0, 16), 0x1234)

    def test_regions_can_be_rewritten_queried_copied_and_dropped(self) -> None:
        buffer = BitBuffer()
        region = buffer.reserve("header", 8)
        buffer.patch("header", 0xA5)

        query = buffer.query("header")
        copied = buffer.copy_region("header")

        self.assertEqual(region.width, 8)
        self.assertEqual(query.value, 0xA5)
        self.assertEqual(query.raw_bytes, b"\xA5")
        self.assertEqual(buffer.query(copied).value, 0xA5)
        dropped = buffer.drop_region("header")
        self.assertEqual(dropped.name, "header")
        self.assertEqual(buffer.query(region).value, 0xA5)

    def test_patch_is_strict_and_transaction_rolls_back(self) -> None:
        buffer = BitBuffer()
        buffer.reserve("slot", 4)
        with self.assertRaises(ValueError):
            buffer.patch("slot", 16)
        with self.assertRaises(ValueError):
            buffer.write_bits(1, 0, 4)

        before = buffer.to_bytes()
        with self.assertRaises(RuntimeError):
            with buffer.transaction():
                buffer.patch("slot", 0b1010)
                buffer.append_bits(0b1111, 4)
                raise RuntimeError("rollback")
        self.assertEqual(buffer.to_bytes(), before)
        self.assertEqual(buffer.query("slot").value, 0)


class BitEmitterTests(unittest.TestCase):
    def test_emitters_use_fixed_widths_and_reservations(self) -> None:
        emitter = BitEmitter(wordsize=16)
        emitter.nibbles("1010", "0101")
        emitter.emit(1, 0, 1, 0, 0, 1, 0, 1)
        emitter.eword(0x1234)
        emitter.reserve("patch", 8)
        emitter.write_res("patch", "11001100")
        copied = emitter.emit_res("patch")

        self.assertEqual(emitter.buffer.to_bytes(), b"\xA5\xA5\x34\x12\xCC\xCC")
        self.assertEqual(emitter.query("patch").value, 0xCC)
        self.assertEqual(emitter.query(copied).value, 0xCC)
        emitter.drop_res("patch")
        self.assertEqual(emitter.query(copied).value, 0xCC)

    def test_emitfr_validates_before_emitting(self) -> None:
        emitter = BitEmitter()
        emitter.frame((("0000", "0"), ("0000",)))
        before = emitter.buffer.to_bytes()

        with self.assertRaises(ValueError):
            emitter.frame((("0000", "2"),))
        self.assertEqual(emitter.buffer.to_bytes(), before)

    def test_fields_preserve_leading_zeroes(self) -> None:
        emitter = BitEmitter()
        emitter.nibbles("0000", "0010")
        self.assertEqual(emitter.buffer.to_bytes(), b"\x02")
        self.assertIsInstance(BitField(0, 4), BitField)


if __name__ == "__main__":
    unittest.main()
