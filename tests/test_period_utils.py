from __future__ import annotations

import unittest

import scheduler
from business_class_import import infer_period
from scripts.period_utils import (
    PERIOD_ORDER,
    VALID_PERIODS,
    normalize_period,
    period_from_time_text,
    period_sort_value,
)
from scripts.sync_erp_adjusted_schedule import period_for_time


class PeriodUtilsTest(unittest.TestCase):
    def test_normalize_period_accepts_chinese_and_english_aliases(self) -> None:
        self.assertEqual(normalize_period("上午"), "AM")
        self.assertEqual(normalize_period(" pm "), "PM")
        self.assertEqual(normalize_period("晚间"), "EVENING")
        self.assertEqual(normalize_period("night"), "EVENING")
        self.assertEqual(normalize_period("", "AM"), "AM")
        self.assertIsNone(normalize_period(""))

    def test_period_sort_value_uses_shared_aliases(self) -> None:
        self.assertEqual(period_sort_value("AM"), 0)
        self.assertEqual(period_sort_value("晚上"), 2)
        self.assertEqual(period_sort_value("MIDDAY"), 99)

    def test_period_from_time_text_uses_configurable_day_evening_cutoff(self) -> None:
        self.assertEqual(period_from_time_text("08:00"), "AM")
        self.assertEqual(period_from_time_text("16:20"), "PM")
        self.assertEqual(period_from_time_text("18:20"), "PM")
        self.assertEqual(period_from_time_text("18:20", pm_end_minutes=18 * 60), "EVENING")
        self.assertEqual(period_from_time_text("坏数据"), "")

    def test_scheduler_reexports_shared_period_helpers_for_compatibility(self) -> None:
        self.assertIs(scheduler.PERIOD_ORDER, PERIOD_ORDER)
        self.assertIs(scheduler.VALID_PERIODS, VALID_PERIODS)
        self.assertIs(scheduler.period_sort_value, period_sort_value)
        self.assertEqual(scheduler.parse_period_set("AM|晚上|night", "测试"), {"AM", "EVENING"})

    def test_business_import_and_erp_sync_reuse_shared_period_rules(self) -> None:
        self.assertEqual(infer_period("晚间", "08:00"), "EVENING")
        self.assertEqual(infer_period("", "18:20"), "PM")
        self.assertEqual(infer_period("", "18:40"), "EVENING")
        self.assertEqual(period_for_time("18:20", "19:00"), ("EVENING", "EVENING-18:20-19:00", "晚上"))


if __name__ == "__main__":
    unittest.main()
