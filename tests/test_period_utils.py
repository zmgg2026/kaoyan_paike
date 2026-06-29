from __future__ import annotations

from datetime import datetime
import unittest

import scheduler
from business_class_import import infer_period
from scripts.build_camp_maintenance_schedule import period_for_time as maintenance_period_for_time
from scripts.import_locked_professional_schedules import period_for as locked_professional_period_for
from scripts.period_utils import (
    PERIOD_LABELS,
    PERIOD_ORDER,
    PERIOD_OPTIONS,
    VALID_PERIODS,
    normalize_period,
    period_from_minutes,
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

    def test_period_labels_are_shared_for_display_surfaces(self) -> None:
        self.assertEqual(PERIOD_OPTIONS, ["AM", "PM", "EVENING"])
        self.assertEqual(PERIOD_LABELS, {"AM": "上午", "PM": "下午", "EVENING": "晚上"})
        self.assertEqual(VALID_PERIODS, set(PERIOD_OPTIONS))
        self.assertEqual(PERIOD_ORDER, {period: index for index, period in enumerate(PERIOD_OPTIONS)})

    def test_period_from_time_text_uses_configurable_day_evening_cutoff(self) -> None:
        self.assertEqual(period_from_time_text("08:00"), "AM")
        self.assertEqual(period_from_time_text("16:20"), "PM")
        self.assertEqual(period_from_time_text("18:20"), "PM")
        self.assertEqual(period_from_time_text("18:20", pm_end_minutes=18 * 60), "EVENING")
        self.assertEqual(period_from_time_text("12:30", am_end_minutes=12 * 60, pm_end_minutes=19 * 60), "PM")
        self.assertEqual(period_from_minutes(12 * 60 - 1, am_end_minutes=12 * 60), "AM")
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
        self.assertEqual(period_for_time("19:00", "21:00"), ("EVENING", "EVENING1", "晚上一"))
        self.assertEqual(period_for_time("18:20", "19:00"), ("EVENING", "EVENING-18:20-19:00", "晚上"))

    def test_maintenance_period_for_time_reuses_shared_cutoffs(self) -> None:
        self.assertEqual(maintenance_period_for_time("12:59"), "AM")
        self.assertEqual(maintenance_period_for_time("13:00"), "PM")
        self.assertEqual(maintenance_period_for_time("17:59"), "PM")
        self.assertEqual(maintenance_period_for_time("18:00"), "EVENING")

    def test_locked_professional_import_period_for_reuses_shared_cutoffs(self) -> None:
        self.assertEqual(locked_professional_period_for(datetime(2026, 7, 1, 11, 59)), "AM")
        self.assertEqual(locked_professional_period_for(datetime(2026, 7, 1, 12, 0)), "PM")
        self.assertEqual(locked_professional_period_for(datetime(2026, 7, 1, 18, 59)), "PM")
        self.assertEqual(locked_professional_period_for(datetime(2026, 7, 1, 19, 0)), "EVENING")


if __name__ == "__main__":
    unittest.main()
