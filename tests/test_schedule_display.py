from __future__ import annotations

import unittest

from scripts.schedule_display import date_range, standard_display_slots, time_to_minutes, week_dates, week_start, weekday_label


class ScheduleDisplayTest(unittest.TestCase):
    def test_calendar_helpers_use_current_display_conventions(self) -> None:
        self.assertEqual(weekday_label("2026-07-01"), "周三")
        self.assertEqual(date_range("2026-07-01", "2026-07-03"), ["2026-07-01", "2026-07-02", "2026-07-03"])
        self.assertEqual(week_start("2026-07-05"), "2026-06-29")
        self.assertEqual(
            week_dates("2026-06-29"),
            [
                "2026-06-29",
                "2026-06-30",
                "2026-07-01",
                "2026-07-02",
                "2026-07-03",
                "2026-07-04",
                "2026-07-05",
            ],
        )

    def test_standard_display_slots_are_derived_from_shared_lesson_templates(self) -> None:
        self.assertEqual(
            standard_display_slots(["PM", "EVENING"]),
            [
                {
                    "id": "PM1",
                    "period": "PM",
                    "label": "下午一",
                    "start_time": "14:00",
                    "end_time": "16:00",
                },
                {
                    "id": "PM2",
                    "period": "PM",
                    "label": "下午二",
                    "start_time": "16:20",
                    "end_time": "18:20",
                },
                {
                    "id": "EVENING1",
                    "period": "EVENING",
                    "label": "晚上",
                    "start_time": "19:00",
                    "end_time": "21:00",
                },
            ],
        )

    def test_time_to_minutes_reuses_shared_time_parsing(self) -> None:
        self.assertEqual(time_to_minutes("08:30:00"), 510)
        self.assertIsNone(time_to_minutes("25:00"))


if __name__ == "__main__":
    unittest.main()
