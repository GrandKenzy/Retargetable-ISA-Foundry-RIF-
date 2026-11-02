from __future__ import annotations

import struct
import unittest

from MIR.storage import (
    ENTRY_SIZE,
    HEADER_SIZE,
    MAGIC,
    StorageBuilder,
    StorageError,
    parse_storage,
)


class StorageTests(unittest.TestCase):
    def test_storage_has_relative_u64_entries_and_aligned_padding(self) -> None:
        builder = StorageBuilder(alignment=8)
        first = builder.add(b"abc", label="first")
        second = builder.add(b"xy", label="second")
        image = parse_storage(builder.build())

        self.assertEqual((HEADER_SIZE, ENTRY_SIZE, MAGIC), (48, 24, b"RIFSTOR\0"))
        self.assertEqual(first.relative_address, 0)
        self.assertEqual(first.padding, 0)
        self.assertEqual(second.relative_address, 8)
        self.assertEqual(second.padding, 0)
        self.assertEqual(image.payload(0), b"abc")
        self.assertEqual(image.payload(1), b"xy")
        self.assertEqual(image.label(0), "first")
        self.assertEqual(image.payload("first"), b"abc")
        self.assertEqual(len(image.entries), 2)
        self.assertIsNone(image.value_type("first"))

    def test_storage_preserves_typed_value_metadata(self) -> None:
        builder = StorageBuilder(version=2)
        builder.add(b"\x02\x01", label="width", value_type="uint16")

        image = parse_storage(builder.build())

        self.assertEqual(image.value_type("width"), "uint16")

    def test_storage_v2_rejects_padding_that_overlaps_type_metadata(self) -> None:
        builder = StorageBuilder(alignment=131072, version=2)
        builder.add(b"first", label="first", value_type="uint8")

        with self.assertRaisesRegex(StorageError, "padding"):
            builder.add(b"second", label="second", value_type="uint8")

    def test_storage_rejects_invalid_magic(self) -> None:
        builder = StorageBuilder()
        blob = bytearray(builder.build())
        blob[:8] = b"INVALID!"
        with self.assertRaisesRegex(StorageError, "magic"):
            parse_storage(blob)

    def test_storage_rejects_negative_and_boolean_indexes(self) -> None:
        builder = StorageBuilder()
        builder.add(b"payload", label="item")
        image = parse_storage(builder.build())

        for index in (-1, True):
            with self.assertRaisesRegex(StorageError, "índice"):
                image.payload(index)
            with self.assertRaisesRegex(StorageError, "índice"):
                image.label(index)

    def test_storage_rejects_inconsistent_entry_padding(self) -> None:
        builder = StorageBuilder(alignment=8)
        builder.add(b"first")
        builder.add(b"second")
        blob = bytearray(builder.build())
        index_offset = struct.unpack_from("<Q", blob, 24)[0]
        second_entry = index_offset + ENTRY_SIZE
        struct.pack_into("<I", blob, second_entry + 16, 0)

        with self.assertRaisesRegex(StorageError, "padding"):
            parse_storage(blob)


if __name__ == "__main__":
    unittest.main()
