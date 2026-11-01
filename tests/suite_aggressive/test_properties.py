from __future__ import annotations

import unittest

from MIR.operations import execute_operation
from rif_tools.properties import integer_cases, run_property


class PropertyTests(unittest.TestCase):
    def test_signed_fit_round_trips_all_generated_edges(self) -> None:
        generator = integer_cases(
            minimum=-128,
            maximum=127,
            edge_values=(-128, -1, 0, 1, 127),
        )

        def property_holds(value: int) -> bool:
            encoded = execute_operation("fit_signed", value, 8, False)
            decoded = encoded - 256 if encoded & 0x80 else encoded
            return decoded == value

        self.assertEqual(
            run_property(generator, property_holds, cases=500, seed=0x524946, name="signed-fit"),
            500,
        )


if __name__ == "__main__":
    unittest.main()
