from __future__ import annotations

import unittest
from collections import Counter

from scripts import export_erp_adjusted_lesson_import
from scripts import export_erp_lesson_import
from scripts import sync_erp_adjusted_schedule
from scripts.build_failed_erp_class_schedule_review import lesson_text


class ErpScheduleWindowFieldTest(unittest.TestCase):
    def test_export_remark_prefers_current_window_name_field(self) -> None:
        row = {
            "class_id": "C1",
            "subject": "英语",
            "window_name": "暑假",
            "quarter": "旧窗口",
            "stage": "基础",
            "course_module": "词汇",
            "course_group": "阅读类",
        }
        shared_keys = {("C1", "英语", "暑假", "阅读类"): "C0"}

        self.assertEqual(export_erp_lesson_import.schedule_window_name(row), "暑假")
        self.assertEqual(export_erp_lesson_import.remark(row), "暑假/基础/词汇")
        self.assertTrue(export_erp_lesson_import.is_shared_merge_row(row, shared_keys))
        self.assertTrue(export_erp_adjusted_lesson_import.is_shared_merge_row(row, shared_keys))

    def test_adjusted_sync_outputs_current_window_name_and_fills_legacy_current_rows(self) -> None:
        self.assertIn("window_name", sync_erp_adjusted_schedule.FIELDNAMES)
        self.assertNotIn("quarter", sync_erp_adjusted_schedule.FIELDNAMES)
        row = {
            "date": "2026-07-01",
            "start_time": "08:00",
            "end_time": "10:00",
            "class_id": "C1",
            "subject": "英语",
        }
        current = {
            "quarter": "暑假",
            "stage": "基础",
            "course_module": "词汇",
            "course_group": "阅读类",
            "course_code": "ENG-VOC",
            "course_name": "英语词汇",
            "teacher_id": "T1",
            "teacher_name": "张老师",
            "room_id": "R1",
            "room_name": "101",
        }

        sync_erp_adjusted_schedule.fill_shared_rows_from_donors(
            [row],
            {("C1", "2026-07-01", "08:00", "10:00"): current},
            {},
            [],
            Counter(),
        )

        self.assertEqual(row["window_name"], "暑假")
        self.assertEqual(row["course_code"], "ENG-VOC")

    def test_failed_review_display_prefers_current_window_name_field(self) -> None:
        text = lesson_text(
            {
                "class_id": "C1",
                "subject": "英语",
                "window_name": "暑假",
                "quarter": "旧窗口",
                "stage": "基础",
                "course_module": "词汇",
                "teacher_name": "张老师",
                "room_name": "101",
                "course_name": "英语词汇",
            },
            is_failed=True,
        )

        self.assertIn("暑假/基础/词汇", text)
        self.assertNotIn("旧窗口", text)


if __name__ == "__main__":
    unittest.main()
