from __future__ import annotations

import unittest

import scheduler
from scripts import build_camp_maintenance_schedule as maintenance
from scripts.compare_history_remaining_changes import (
    consumed_hours_by_requirement,
    requirement_rows,
)


def requirement() -> scheduler.Requirement:
    return scheduler.Requirement(
        subject_category="公共课",
        subject="英语",
        quarter="暑假",
        stage="基础",
        course_module="词汇",
        course_group="阅读类",
        teacher_id="T1",
        teacher_name="老师1",
        total_hours=8,
        block_hours=2,
    )


def schedule_input_with_requirement(req: scheduler.Requirement) -> scheduler.ScheduleInput:
    cls = scheduler.SchoolClass(
        id="C1",
        name="测试班",
        product_id="P1",
        product_name="测试产品",
        size=30,
        room_ids=None,
        start_date=None,
        start_period=None,
        end_date=None,
        end_period=None,
        first_lesson_date=None,
        first_lesson_period=None,
        stage_order={"基础": 0},
        requirements=[req],
    )
    return scheduler.ScheduleInput(
        time_slots=[],
        rooms={},
        classes={"C1": cls},
        conflict_groups={},
        class_conflict_groups={},
        locked_assignments=[],
    )


class RequirementKeyTest(unittest.TestCase):
    def test_product_requirement_parsing_prefers_current_window_name_field(self) -> None:
        rule = scheduler.ScheduleRule(
            subject=None,
            stage=None,
            course_module=None,
            course_group=None,
            start_date=None,
            end_date=None,
            allowed_periods=None,
            allowed_weekdays=None,
            excluded_weekdays=None,
            block_hours=2,
            window_names={"暑假"},
        )

        requirement = scheduler.parse_product_requirement(
            "P1",
            {
                "subject_category": "公共课",
                "subject": "英语",
                "window_name": "暑假",
                "quarter": "旧窗口",
                "stage": "基础",
                "course_module": "词汇",
                "course_group": "阅读类",
                "total_hours": 2,
            },
            [rule],
        )

        self.assertEqual(requirement.quarter, "暑假")
        self.assertEqual(requirement.block_hours, 2)

    def test_class_requirement_selection_prefers_current_selected_stages_field(self) -> None:
        product = scheduler.Product(
            id="P1",
            name="测试产品",
            requirements=[
                scheduler.ProductRequirement("公共课", "英语", "暑假", "基础", "词汇", "阅读类", 2, 2),
                scheduler.ProductRequirement("公共课", "英语", "暑假", "强化", "阅读", "阅读类", 2, 2),
            ],
        )

        selected = scheduler.select_product_requirements_for_class(
            "C1",
            product,
            {
                "id": "C1",
                "subject": "英语",
                "selected_stages": "基础",
                "stages": "强化",
            },
        )

        self.assertEqual([item.stage for item in selected], ["基础"])

    def test_mapping_object_and_history_keys_share_core_requirement_key(self) -> None:
        row = {
            "subject": "英语",
            "stage": "基础",
            "course_module": "词汇",
            "course_group": "阅读类",
        }
        req = requirement()

        self.assertEqual(scheduler.requirement_mapping_key(row), scheduler.requirement_object_key(req))
        self.assertEqual(maintenance.history_requirement_key(row), scheduler.requirement_object_key(req))

    def test_history_remaining_compare_uses_core_requirement_key(self) -> None:
        rows = [
            {
                "class_id": "C1",
                "date": "2026-06-20",
                "subject": "英语",
                "stage": "基础",
                "course_module": "词汇",
                "course_group": "阅读类",
                "duration_hours": "2",
            },
            {
                "class_id": "C1",
                "date": "2026-07-02",
                "subject": "英语",
                "stage": "基础",
                "course_module": "词汇",
                "course_group": "阅读类",
                "duration_hours": "2",
            },
        ]
        consumed = consumed_hours_by_requirement(rows, "2026-07-01", ["C1"])
        req = requirement()
        diff_rows = requirement_rows(
            schedule_input_with_requirement(req),
            {"C1": {"name": "测试班", "suite_code": "S1", "sub_product": "无忧秋"}},
            {},
            consumed,
        )

        self.assertEqual(consumed[("C1", scheduler.requirement_object_key(req))], 2)
        self.assertEqual(len(diff_rows), 1)
        self.assertEqual(diff_rows[0]["old_remaining_hours"], 8)
        self.assertEqual(diff_rows[0]["new_remaining_hours"], 6)


if __name__ == "__main__":
    unittest.main()
