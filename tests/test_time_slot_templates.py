from __future__ import annotations

import unittest
from datetime import date

from generate_time_slots import generate_time_slots
from scripts.time_slot_templates import (
    DEFAULT_LESSON_TEMPLATES,
    adjacent_halfday_slot_map,
    default_lesson_template_rows,
    lesson_slot_order,
    period_slot_specs,
    standard_slot_specs_by_period,
)


class TimeSlotTemplatesTest(unittest.TestCase):
    def test_default_lesson_templates_define_standard_day_and_evening_slots(self) -> None:
        self.assertEqual(
            list(DEFAULT_LESSON_TEMPLATES),
            [
                {
                    "period": "AM",
                    "suffix": "1",
                    "name": "上午一",
                    "order": 1,
                    "start_time": "08:00",
                    "end_time": "10:00",
                    "duration_hours": 2,
                },
                {
                    "period": "AM",
                    "suffix": "2",
                    "name": "上午二",
                    "order": 2,
                    "start_time": "10:20",
                    "end_time": "12:20",
                    "duration_hours": 2,
                },
                {
                    "period": "PM",
                    "suffix": "1",
                    "name": "下午一",
                    "order": 1,
                    "start_time": "14:00",
                    "end_time": "16:00",
                    "duration_hours": 2,
                },
                {
                    "period": "PM",
                    "suffix": "2",
                    "name": "下午二",
                    "order": 2,
                    "start_time": "16:20",
                    "end_time": "18:20",
                    "duration_hours": 2,
                },
                {
                    "period": "EVENING",
                    "suffix": "1",
                    "name": "晚上",
                    "order": 1,
                    "start_time": "19:00",
                    "end_time": "21:00",
                    "duration_hours": 2,
                },
            ],
        )
        rows = default_lesson_template_rows()
        rows[0]["name"] = "changed"
        self.assertEqual(DEFAULT_LESSON_TEMPLATES[0]["name"], "上午一")

    def test_derived_slot_helpers_match_default_templates(self) -> None:
        self.assertEqual(
            standard_slot_specs_by_period(("AM",))["AM"],
            (
                (1, "上午一", "08:00", "10:00", 2),
                (2, "上午二", "10:20", "12:20", 2),
            ),
        )
        self.assertEqual(
            period_slot_specs(("PM",))["PM"],
            (
                ("PM1", "下午一", "14:00", "16:00"),
                ("PM2", "下午二", "16:20", "18:20"),
            ),
        )
        self.assertEqual(lesson_slot_order(), {"AM1": 0, "AM2": 1, "PM1": 2, "PM2": 3, "EVENING1": 4})
        self.assertEqual(adjacent_halfday_slot_map()["AM1"], ("AM2", "上午二", "10:20", "12:20"))
        self.assertEqual(adjacent_halfday_slot_map()["PM2"], ("PM1", "下午一", "14:00", "16:00"))

    def test_time_slot_generator_reuses_shared_templates_without_extra_suffix_field(self) -> None:
        slots = generate_time_slots(date(2026, 7, 1), date(2026, 7, 1), set(), "all")

        self.assertEqual([slot["id"] for slot in slots], [f"2026-07-01-{template['period']}-{template['suffix']}" for template in DEFAULT_LESSON_TEMPLATES])
        self.assertEqual([slot["name"] for slot in slots], [template["name"] for template in DEFAULT_LESSON_TEMPLATES])
        self.assertNotIn("suffix", slots[0])


if __name__ == "__main__":
    unittest.main()
