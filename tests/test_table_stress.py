from __future__ import annotations

import time
import unittest

from Frontend import RIF_LANG_SESSION
from gram import lexer


def build_table(rows: int, columns: int) -> str:
    header = "| " + " | ".join(f"field_{index}" for index in range(columns)) + " |"
    lines = ["@table stress", header]

    for row_index in range(rows):
        separator_width = 2 + (row_index * 97) % 4096
        lines.append("_" * separator_width)

        values: list[str] = []
        for column_index in range(columns):
            selector = column_index % 4
            if selector == 0:
                values.append(str(row_index * columns + column_index))
            elif selector == 1:
                values.append(f"identifier_{row_index}_{column_index}")
            elif selector == 2:
                values.append(f'"row {row_index} column {column_index}"')
            else:
                values.append("true" if row_index % 2 == 0 else "false")

        lines.append("| " + " | ".join(values) + " |")

    lines.append("@end")
    return "\n".join(lines) + "\n"


class TableStressTests(unittest.TestCase):
    def test_table_separators_are_grouped_underscore_tokens(self) -> None:
        tokens = RIF_LANG_SESSION.tokenize(
            "@table grouped\n| name |\n________\n| value |\n@end\n",
            "grouped.rif",
        )
        separators = [token for token in tokens if token.value == "________"]

        self.assertEqual(len(separators), 1)
        self.assertIs(separators[0].token, lexer.Token.UNDERSCORES)

    def test_large_mixed_table_repeatedly(self) -> None:
        source = build_table(rows=25, columns=16)

        started = time.perf_counter()
        for iteration in range(2):
            RIF_LANG_SESSION.load()
            tokens = RIF_LANG_SESSION.tokenize(source, f"stress_{iteration}.rif")
            ast = RIF_LANG_SESSION.parse(tokens, f"stress_{iteration}.rif")
            self.assertIsNotNone(ast)

        elapsed = time.perf_counter() - started
        self.assertLess(elapsed, 30.0, f"El parser tardó demasiado: {elapsed:.2f}s")

    def test_extreme_separator_widths(self) -> None:
        source = "\n".join(
            [
                "@table separators",
                "| id | value |",
                "__",
                '| 1 | "short" |',
                "_" * 4096,
                '| 2 | "wide separator" |',
                "_" * 8192,
                "| 3 | final |",
                "@end",
                "",
            ]
        )

        RIF_LANG_SESSION.load()
        tokens = RIF_LANG_SESSION.tokenize(source, "extreme_separators.rif")
        ast = RIF_LANG_SESSION.parse(tokens, "extreme_separators.rif")
        self.assertIsNotNone(ast)


if __name__ == "__main__":
    unittest.main()
