from __future__ import annotations

import unittest

from MIR.operations import (
    execute_operation,
    operation_abi,
    operation_c_header,
    operation_c_source,
    operation_specs,
)


class RuleOperationTests(unittest.TestCase):
    def test_operation_abi_is_closed_and_c_compatible(self) -> None:
        names = [spec.name for spec in operation_specs()]
        self.assertEqual(names, sorted(names))
        self.assertEqual(operation_abi()["version"], "1.0")
        header = operation_c_header()
        self.assertIn("rif_op_fit_unsigned", header)
        self.assertIn("rif_op_fit_signed", header)
        self.assertIn("rif_op_encode_relocation", header)
        self.assertIn('#include "rif_rule_operation_abi.h"', operation_c_source())

    def test_rule_primitives_cover_unsigned_signed_and_relocation_ranges(self) -> None:
        self.assertEqual(execute_operation("fit_unsigned", 0x1FF, 8, True), 0xFF)
        self.assertEqual(execute_operation("fit_signed", -1, 8, False), 0xFF)
        self.assertEqual(execute_operation("encode_relocation", -2, 8, "pc"), 0xFE)
        with self.assertRaises(ValueError):
            execute_operation("fit_signed", 128, 8, False)
        with self.assertRaises(ValueError):
            execute_operation("encode_relocation", 256, 8, "abs")


if __name__ == "__main__":
    unittest.main()
