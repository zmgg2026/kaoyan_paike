from __future__ import annotations

import unittest
from datetime import date, datetime

from scripts.field_utils import (
    display_date_text,
    is_blank_marker,
    normalize_blank_marker,
    normalize_date_text,
    normalize_excel_cell_text,
    normalize_iso_date_text,
    normalize_excel_text,
    normalize_float,
    normalize_int,
    normalize_text,
    parse_date_value,
    parse_datetime_value,
    normalize_time_text,
    parse_bool,
    parse_bool_default,
    parse_enabled,
    parse_time_minutes,
    row_value,
    split_delimited_values,
    split_pipe_values,
    split_time_range_text,
)


class FieldUtilsTest(unittest.TestCase):
    def test_normalize_text_preserves_falsey_non_empty_values(self) -> None:
        self.assertEqual(normalize_text(None), "")
        self.assertEqual(normalize_text("  C1  "), "C1")
        self.assertEqual(normalize_text(0), "0")

    def test_row_value_returns_first_non_empty_candidate(self) -> None:
        row = {"empty": " ", "zero": 0, "fallback": "C1"}
        self.assertEqual(row_value(row, "empty", "zero", "fallback"), "0")
        self.assertEqual(row_value({"flag": False}, "flag"), "False")
        self.assertEqual(row_value(row, "missing", "empty"), "")

    def test_blank_marker_helpers_share_placeholder_values(self) -> None:
        self.assertTrue(is_blank_marker("暂无"))
        self.assertTrue(is_blank_marker("N/A"))
        self.assertTrue(is_blank_marker("None"))
        self.assertEqual(normalize_blank_marker(" — "), "")
        self.assertEqual(normalize_blank_marker(" T001 "), "T001")

    def test_normalize_excel_text_drops_integer_float_suffixes(self) -> None:
        self.assertEqual(normalize_excel_text(None), "")
        self.assertEqual(normalize_excel_text(123.0), "123")
        self.assertEqual(normalize_excel_text(123.5), "123.5")
        self.assertEqual(normalize_excel_text("  RM001  "), "RM001")

    def test_normalize_excel_cell_text_handles_typed_workbook_values(self) -> None:
        self.assertEqual(normalize_excel_cell_text(None), "")
        self.assertEqual(normalize_excel_cell_text(datetime(2026, 7, 1, 8, 30)), "2026-07-01")
        self.assertEqual(normalize_excel_cell_text(date(2026, 7, 1)), "2026-07-01")
        self.assertEqual(normalize_excel_cell_text(True), "是")
        self.assertEqual(normalize_excel_cell_text(False), "否")
        self.assertEqual(normalize_excel_cell_text(123.0), "123")
        self.assertEqual(normalize_excel_cell_text(123.5), "123.5")
        self.assertEqual(normalize_excel_cell_text(123, "000000"), "000123")
        self.assertEqual(normalize_excel_cell_text("  RM001  "), "RM001")

    def test_normalize_int_and_float_handle_empty_and_invalid_values(self) -> None:
        self.assertEqual(normalize_int("4.0"), 4)
        self.assertEqual(normalize_int("", default=7), 7)
        self.assertEqual(normalize_int("坏数据", default=9), 9)
        self.assertEqual(normalize_float("2.3456"), 2.346)
        self.assertEqual(normalize_float(None, default=1.5), 1.5)

    def test_normalize_date_text_accepts_common_import_formats(self) -> None:
        self.assertEqual(normalize_date_text(None), "")
        self.assertEqual(normalize_date_text(date(2026, 7, 1)), "2026-07-01")
        self.assertEqual(normalize_date_text(datetime(2026, 7, 1, 8, 30)), "2026-07-01")
        self.assertEqual(normalize_date_text("2026/7/1"), "2026-07-01")
        self.assertEqual(normalize_date_text("2026.7.1"), "2026-07-01")
        self.assertEqual(normalize_date_text("20260701"), "2026-07-01")
        self.assertEqual(normalize_date_text("2026-07-01T08:30:00"), "2026-07-01")
        self.assertEqual(normalize_date_text("待确认"), "待确认")
        self.assertEqual(display_date_text("2026/7/1"), "2026/07/01")
        self.assertEqual(display_date_text("待确认"), "待确认")
        self.assertEqual(normalize_iso_date_text("2026.7.1"), "2026-07-01")
        self.assertEqual(normalize_iso_date_text(""), "")

    def test_parse_date_value_raises_with_label_for_invalid_values(self) -> None:
        self.assertEqual(parse_date_value("2026/7/1", "开课日期"), date(2026, 7, 1))
        with self.assertRaisesRegex(ValueError, "开课日期 日期格式无法识别: 待确认"):
            parse_date_value("待确认", "开课日期")

    def test_parse_datetime_value_accepts_common_lesson_formats(self) -> None:
        self.assertEqual(parse_datetime_value("2026/7/1 8:30", "起始时间"), datetime(2026, 7, 1, 8, 30))
        self.assertEqual(
            parse_datetime_value("2026.07.01 08:30:00", "起始时间"),
            datetime(2026, 7, 1, 8, 30),
        )
        self.assertEqual(
            parse_datetime_value("2026-07-01", "起始时间", allow_date=True),
            datetime(2026, 7, 1, 0, 0),
        )
        with self.assertRaisesRegex(ValueError, "无法解析起始时间"):
            parse_datetime_value("待确认", "起始时间")

    def test_time_helpers_normalize_import_time_text(self) -> None:
        self.assertEqual(normalize_time_text(None), "")
        self.assertEqual(normalize_time_text(datetime(2026, 7, 1, 8, 5)), "08:05")
        self.assertEqual(normalize_time_text("8:00"), "08:00")
        self.assertEqual(normalize_time_text("08:00:00"), "08:00")
        self.assertEqual(normalize_time_text("待确认"), "待确认")
        self.assertEqual(parse_time_minutes("08:30:00"), 510)
        self.assertIsNone(parse_time_minutes("25:00"))
        self.assertEqual(split_time_range_text("8:00-10:00"), ("08:00", "10:00"))
        self.assertEqual(split_time_range_text("08:00－10:00"), ("08:00", "10:00"))
        self.assertEqual(split_time_range_text("08:00"), ("08:00", ""))

    def test_split_pipe_values_trims_and_drops_empty_items(self) -> None:
        self.assertEqual(split_pipe_values("A | | B"), ["A", "B"])
        self.assertEqual(split_pipe_values("A,B，C;D；E"), ["A", "B", "C", "D", "E"])
        self.assertEqual(split_pipe_values([" A ", "", 0]), ["A", "0"])
        self.assertEqual(split_delimited_values("数学|英语，政治;语文"), ["数学", "英语", "政治", "语文"])
        self.assertEqual(split_delimited_values("A B|C"), ["A B", "C"])
        self.assertEqual(split_delimited_values("A B|C，D", include_whitespace=True), ["A", "B", "C", "D"])
        self.assertEqual(split_delimited_values("A/B、C", extra_separators="/、"), ["A", "B", "C"])
        self.assertEqual(
            split_delimited_values("A / B、C", include_whitespace=True, extra_separators="/、"),
            ["A", "B", "C"],
        )
        self.assertEqual(split_delimited_values(0), ["0"])

    def test_parse_bool_recognizes_shared_true_values(self) -> None:
        self.assertTrue(parse_bool("启用"))
        self.assertTrue(parse_bool("纳入"))
        self.assertTrue(parse_bool("锁定"))
        self.assertTrue(parse_bool("on"))
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
