from __future__ import annotations

import unittest

from scripts.field_utils import (
    normalize_excel_text,
    normalize_text,
    parse_bool,
    parse_bool_default,
    parse_enabled,
    split_pipe_values,
)


class FieldUtilsTest(unittest.TestCase):
    def test_normalize_text_preserves_falsey_non_empty_values(self) -> None:
        self.assertEqual(normalize_text(None), "")
        self.assertEqual(normalize_text("  C1  "), "C1")
        self.assertEqual(normalize_text(0), "0")

    def test_normalize_excel_text_drops_integer_float_suffixes(self) -> None:
        self.assertEqual(normalize_excel_text(None), "")
        self.assertEqual(normalize_excel_text(123.0), "123")
        self.assertEqual(normalize_excel_text(123.5), "123.5")
        self.assertEqual(normalize_excel_text("  RM001  "), "RM001")

    def test_split_pipe_values_trims_and_drops_empty_items(self) -> None:
        self.assertEqual(split_pipe_values("A | | B"), ["A", "B"])
        self.assertEqual(split_pipe_values([" A ", "", 0]), ["A", "0"])

    def test_parse_bool_recognizes_shared_true_values(self) -> None:
        self.assertTrue(parse_bool("启用"))
        self.assertTrue(parse_bool("纳入"))
        self.assertFalse(parse_bool("no"))
        self.assertFalse(parse_bool("未知"))

    def test_parse_bool_default_uses_default_only_for_empty_values(self) -> None:
        self.assertTrue(parse_bool_default("", True))
        self.assertFalse(parse_bool_default("未知", True))

    def test_parse_enabled_treats_unknown_non_empty_values_as_enabled(self) -> None:
        self.assertFalse(parse_enabled("否"))
        self.assertFalse(parse_enabled("停用"))
        self.assertTrue(parse_enabled(""))
        self.assertTrue(parse_enabled("待确认"))


if __name__ == "__main__":
    unittest.main()
