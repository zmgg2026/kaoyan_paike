import csv
import tempfile
import unittest
from pathlib import Path

import data_admin_server
import scheduler
from scripts.sync_erp_adjusted_schedule import load_inherit_lookup
from scripts.schedule_modes import (
    assignment_is_shared,
    assignment_reference_class_id,
    assignment_schedule_mode,
    class_schedule_mode_display_name,
    is_shared_class_schedule,
    normalize_class_schedule_mode,
)


class ScheduleModesTest(unittest.TestCase):
    def test_normalize_class_schedule_mode_understands_current_display_fields(self) -> None:
        self.assertEqual(normalize_class_schedule_mode("共享实际排课班级"), "共享课表")
        self.assertEqual(
            normalize_class_schedule_mode("共享实际排课班级", actual_scheduled_class_id="C_SELF", class_id="C_SELF"),
            "独立排课",
        )
        self.assertEqual(normalize_class_schedule_mode("本班实际排课", actual_scheduled_class_id="C_MAIN", class_id="C_SUB"), "独立排课")
        self.assertEqual(normalize_class_schedule_mode("", actual_scheduled_class_id="C_MAIN", class_id="C_SUB"), "共享课表")
        self.assertEqual(normalize_class_schedule_mode("合班主班"), "合班主班")
        self.assertEqual(normalize_class_schedule_mode("合班实际排课班级"), "合班主班")
        self.assertFalse(is_shared_class_schedule("合班主班"))
        self.assertEqual(class_schedule_mode_display_name("合班主班"), "合班实际排课班级")

    def test_assignment_row_helpers_understand_current_and_legacy_fields(self) -> None:
        current_row = {
            "class_id": "C_SUB",
            "class_schedule_mode": "共享实际排课班级",
            "actual_scheduled_class_id": "C_MAIN",
        }
        legacy_row = {
            "class_id": "C_SUB",
            "schedule_mode": "共享课表",
            "inherit_from_class_id": "C_MAIN",
        }

        self.assertEqual(assignment_schedule_mode(current_row), "共享课表")
        self.assertEqual(assignment_reference_class_id(current_row), "C_MAIN")
        self.assertEqual(assignment_schedule_mode(legacy_row), "共享课表")
        self.assertEqual(assignment_reference_class_id(legacy_row), "C_MAIN")

    def test_current_assignment_fields_win_over_stale_legacy_fields(self) -> None:
        row = {
            "class_id": "C_SELF",
            "class_schedule_mode": "本班实际排课",
            "actual_scheduled_class_id": "C_SELF",
            "schedule_mode": "共享课表",
            "inherit_from_class_id": "C_OLD_MAIN",
            "teacher_id": "T1",
            "teacher_name": "张老师",
        }

        normalized = data_admin_server.normalize_teacher_assignment(row)

        self.assertEqual(assignment_schedule_mode(row), "独立排课")
        self.assertEqual(assignment_reference_class_id(row), "C_SELF")
        self.assertFalse(assignment_is_shared(row, class_id="C_SELF"))
        self.assertEqual(normalized["class_schedule_mode"], "本班实际排课")
        self.assertEqual(normalized["actual_scheduled_class_id"], "C_SELF")
        self.assertEqual(normalized["teacher_id"], "T1")

    def test_current_actual_class_wins_when_mode_is_blank_and_legacy_source_is_stale(self) -> None:
        row = {
            "class_id": "C_SELF",
            "class_schedule_mode": "",
            "actual_scheduled_class_id": "C_SELF",
            "schedule_mode": "",
            "inherit_from_class_id": "C_OLD_MAIN",
            "teacher_id": "T1",
            "teacher_name": "张老师",
        }

        normalized = data_admin_server.normalize_teacher_assignment(row)

        self.assertEqual(assignment_schedule_mode(row), "独立排课")
        self.assertEqual(assignment_reference_class_id(row), "C_SELF")
        self.assertFalse(assignment_is_shared(row, class_id="C_SELF"))
        self.assertEqual(normalized["class_schedule_mode"], "本班实际排课")
        self.assertEqual(normalized["actual_scheduled_class_id"], "C_SELF")
        self.assertEqual(normalized["teacher_id"], "T1")

    def test_current_actual_shared_class_wins_over_stale_legacy_source(self) -> None:
        row = {
            "class_id": "C_SUB",
            "class_schedule_mode": "",
            "actual_scheduled_class_id": "C_CURRENT_MAIN",
            "schedule_mode": "本班实际排课",
            "inherit_from_class_id": "C_OLD_MAIN",
        }

        normalized = data_admin_server.normalize_teacher_assignment(row)

        self.assertEqual(assignment_schedule_mode(row), "共享课表")
        self.assertEqual(assignment_reference_class_id(row), "C_CURRENT_MAIN")
        self.assertTrue(assignment_is_shared(row, class_id="C_SUB"))
        self.assertEqual(normalized["class_schedule_mode"], "共享实际排课班级")
        self.assertEqual(normalized["actual_scheduled_class_id"], "C_CURRENT_MAIN")

    def test_self_referenced_shared_assignment_is_current_class_schedule(self) -> None:
        row = {
            "class_id": "C_SELF",
            "class_schedule_mode": "共享实际排课班级",
            "actual_scheduled_class_id": "C_SELF",
            "teacher_id": "T1",
            "teacher_name": "张老师",
        }

        normalized = data_admin_server.normalize_teacher_assignment(row)

        self.assertEqual(assignment_schedule_mode(row), "独立排课")
        self.assertFalse(assignment_is_shared(row, class_id="C_SELF"))
        self.assertEqual(normalized["class_schedule_mode"], "本班实际排课")
        self.assertEqual(normalized["actual_scheduled_class_id"], "C_SELF")
        self.assertEqual(normalized["teacher_id"], "T1")

    def test_scheduler_and_admin_share_teacher_assignment_mode_normalization(self) -> None:
        raw_assignment = {
            "class_id": "C_SUB",
            "class_schedule_mode": "",
            "actual_scheduled_class_id": "C_MAIN",
            "teacher_id": "T1",
            "teacher_name": "张老师",
        }

        normalized = data_admin_server.normalize_teacher_assignment(raw_assignment)

        self.assertEqual(normalized["class_schedule_mode"], "共享实际排课班级")
        self.assertEqual(normalized["actual_scheduled_class_id"], "C_MAIN")
        self.assertNotIn("schedule_mode", normalized)
        self.assertNotIn("inherit_from_class_id", normalized)
        self.assertNotIn("course_module", normalized)
        self.assertEqual(normalized["teacher_id"], "")
        self.assertTrue(assignment_is_shared(normalized))

    def test_scheduler_no_longer_exposes_raw_schedule_mode_wrappers(self) -> None:
        self.assertFalse(hasattr(scheduler, "raw_schedule_mode"))
        self.assertFalse(hasattr(scheduler, "raw_assignment_is_shared"))

    def test_scheduler_load_input_understands_current_shared_assignment_fields(self) -> None:
        payload = {
            "time_slots": [
                {
                    "id": "S1",
                    "date": "2026-07-01",
                    "period": "AM",
                    "name": "上午",
                    "order": 1,
                    "duration_hours": 2,
                }
            ],
            "rooms": [{"id": "R1", "capacity": 80}],
            "products": [
                {
                    "id": "P1",
                    "name": "测试产品",
                    "requirements": [
                        {
                            "subject": "英语",
                            "stage": "基础",
                            "course_group": "阅读类",
                            "total_hours": 2,
                            "block_hours": 2,
                        }
                    ],
                }
            ],
            "classes": [
                {
                    "id": "C_MAIN",
                    "name": "实际排课班",
                    "product_id": "P1",
                    "subject": "英语",
                    "stages": ["基础"],
                    "room_ids": ["R1"],
                    "teacher_assignments": [
                        {
                            "subject": "英语",
                            "stage": "基础",
                            "course_group": "阅读类",
                            "teacher_id": "T1",
                            "teacher_name": "张老师",
                        }
                    ],
                },
                {
                    "id": "C_SUB",
                    "name": "共享课表班",
                    "product_id": "P1",
                    "subject": "英语",
                    "stages": ["基础"],
                    "room_ids": ["R1"],
                    "teacher_assignments": [
                        {
                            "subject": "英语",
                            "stage": "基础",
                            "course_group": "阅读类",
                            "class_schedule_mode": "共享实际排课班级",
                            "actual_scheduled_class_id": "C_MAIN",
                        }
                    ],
                },
            ],
        }

        schedule_input = scheduler.load_input_data(payload)

        self.assertEqual(set(schedule_input.classes), {"C_MAIN"})

    def test_scheduler_load_input_keeps_self_referenced_shared_assignment_as_schedulable(self) -> None:
        payload = {
            "time_slots": [
                {
                    "id": "S1",
                    "date": "2026-07-01",
                    "period": "AM",
                    "name": "上午",
                    "order": 1,
                    "duration_hours": 2,
                }
            ],
            "rooms": [{"id": "R1", "capacity": 80}],
            "products": [
                {
                    "id": "P1",
                    "name": "测试产品",
                    "requirements": [
                        {
                            "subject": "英语",
                            "stage": "基础",
                            "course_group": "阅读类",
                            "total_hours": 2,
                            "block_hours": 2,
                        }
                    ],
                }
            ],
            "classes": [
                {
                    "id": "C_SELF",
                    "name": "实际排课班",
                    "product_id": "P1",
                    "subject": "英语",
                    "stages": ["基础"],
                    "room_ids": ["R1"],
                    "teacher_assignments": [
                        {
                            "product_id": "P1",
                            "subject": "英语",
                            "stage": "基础",
                            "course_group": "阅读类",
                            "class_schedule_mode": "共享实际排课班级",
                            "actual_scheduled_class_id": "C_SELF",
                            "teacher_id": "T1",
                            "teacher_name": "张老师",
                        }
                    ],
                }
            ],
        }

        schedule_input = scheduler.load_input_data(payload)

        self.assertEqual(set(schedule_input.classes), {"C_SELF"})
        requirement = schedule_input.classes["C_SELF"].requirements[0]
        self.assertEqual(requirement.teacher_id, "T1")

    def test_erp_sync_inherit_lookup_uses_current_assignment_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "class_teacher_assignments.csv"
            with path.open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "class_id",
                        "subject",
                        "class_schedule_mode",
                        "actual_scheduled_class_id",
                        "schedule_mode",
                        "inherit_from_class_id",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "class_id": "C_SUB",
                        "subject": "英语",
                        "class_schedule_mode": "共享实际排课班级",
                        "actual_scheduled_class_id": "C_MAIN",
                        "schedule_mode": "",
                        "inherit_from_class_id": "",
                    }
                )
                writer.writerow(
                    {
                        "class_id": "C_SELF",
                        "subject": "英语",
                        "class_schedule_mode": "本班实际排课",
                        "actual_scheduled_class_id": "C_SELF",
                        "schedule_mode": "共享课表",
                        "inherit_from_class_id": "C_OLD_MAIN",
                    }
                )

            lookup = load_inherit_lookup(Path(temp_dir))

        self.assertEqual(lookup[("C_SUB", "英语")], ["C_MAIN"])
        self.assertNotIn(("C_SELF", "英语"), lookup)


if __name__ == "__main__":
    unittest.main()
