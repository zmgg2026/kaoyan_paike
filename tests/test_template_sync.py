from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import data_admin_server
import formal_template
from scripts.csv_utils import read_csv_rows
from scripts.sync_template_workbook_to_admin_data import enrich_rows, output_fields_for_key, standard_output_rows, write_csv


class TemplateSyncTest(unittest.TestCase):
    def test_class_teacher_assignment_sync_outputs_current_fields_only(self) -> None:
        rows = enrich_rows(
            "class_teacher_assignments",
            [
                {
                    "class_id": "C_SUB",
                    "class_name": "共享从班",
                    "product_id": "P1",
                    "product_name": "产品1",
                    "subject": "英语",
                    "stage": "基础",
                    "course_module": "词汇",
                    "course_group": "阅读类",
                    "schedule_mode": "共享课表",
                    "inherit_from_class_id": "C_MAIN",
                    "teacher_available_slots": ["OLD_SLOT"],
                    "teacher_id": "T_OLD",
                    "teacher_name": "旧老师",
                    "notes": "共享主班课表",
                },
                {
                    "class_id": "C_SELF",
                    "class_name": "本班",
                    "product_id": "P1",
                    "subject": "英语",
                    "stage": "强化",
                    "course_group": "阅读类",
                    "class_schedule_mode": "",
                    "actual_scheduled_class_id": "",
                    "teacher_id": "T1",
                    "teacher_name": "张老师",
                },
                {
                    "class_id": "C_SUB_NEW",
                    "class_name": "新版共享从班",
                    "product_id": "P1",
                    "subject": "英语",
                    "stage": "强化",
                    "course_group": "阅读类",
                    "class_schedule_mode": "",
                    "actual_scheduled_class_id": "C_CURRENT_MAIN",
                    "schedule_mode": "本班实际排课",
                    "inherit_from_class_id": "C_OLD_MAIN",
                    "teacher_id": "T_STALE",
                    "teacher_name": "旧字段老师",
                },
                {
                    "class_id": "C_MAIN",
                    "class_name": "合班实际排课班级",
                    "product_id": "P1",
                    "subject": "英语",
                    "stage": "强化",
                    "course_group": "阅读类",
                    "class_schedule_mode": "合班实际排课班级",
                    "actual_scheduled_class_id": "C_MAIN",
                    "teacher_id": "T_MAIN",
                    "teacher_name": "主班老师",
                },
            ],
        )

        for row in rows:
            for old_field in ("schedule_mode", "inherit_from_class_id", "teacher_available_slots", "course_module"):
                self.assertNotIn(old_field, row)

        self.assertEqual(rows[0]["class_schedule_mode"], "共享实际排课班级")
        self.assertEqual(rows[0]["actual_scheduled_class_id"], "C_MAIN")
        self.assertEqual(rows[0]["teacher_id"], "")
        self.assertEqual(rows[0]["teacher_name"], "")
        self.assertEqual(rows[1]["class_schedule_mode"], "本班实际排课")
        self.assertEqual(rows[1]["actual_scheduled_class_id"], "C_SELF")
        self.assertEqual(rows[1]["teacher_id"], "T1")
        self.assertEqual(rows[2]["class_schedule_mode"], "共享实际排课班级")
        self.assertEqual(rows[2]["actual_scheduled_class_id"], "C_CURRENT_MAIN")
        self.assertEqual(rows[2]["teacher_id"], "")
        self.assertEqual(rows[3]["class_schedule_mode"], "合班实际排课班级")
        self.assertEqual(rows[3]["actual_scheduled_class_id"], "C_MAIN")
        self.assertEqual(rows[3]["teacher_id"], "T_MAIN")

    def test_template_sync_drops_legacy_duplicate_fields(self) -> None:
        classes = enrich_rows(
            "classes",
            [
                {
                    "id": "C1",
                    "name": "英语1班",
                    "selected_stages": [],
                    "stages": ["基础"],
                    "is_schedule_locked": True,
                    "actual_schedule_window_ids": ["2026暑假"],
                }
            ],
        )
        mappings = enrich_rows(
            "business_product_mappings",
            [
                {
                    "business_product_id": "100",
                    "canonical_product_id": "P1",
                    "match_status": "已匹配",
                }
            ],
        )
        product_courses = enrich_rows(
            "product_courses",
            [
                {
                    "product_id": "P1",
                    "quarter": "暑假",
                    "course_module": "词汇",
                    "module_priority": 3,
                    "block_hours": 4,
                    "teaching_area_ids": ["A1"],
                }
            ],
        )
        product_rules = enrich_rows(
            "product_schedule_rules",
            [
                {
                    "rule_id": "RULE1",
                    "rule_name": "旧规则名",
                    "scope_type": "product_ids",
                    "product_ids": ["P1"],
                    "product_name_keywords": ["无忧"],
                    "subject": "英语",
                    "stage": "基础",
                    "course_module": "词汇",
                    "course_group": "阅读类",
                    "start_date": "2026-07-01",
                    "end_date": "2026-08-31",
                    "excluded_weekdays": ["周日"],
                    "exception_weekdays": [],
                    "block_hours_override": 4,
                }
            ],
        )

        self.assertNotIn("actual_schedule_window_ids", classes[0])
        self.assertNotIn("stages", classes[0])
        self.assertNotIn("is_schedule_locked", classes[0])
        self.assertEqual(classes[0]["selected_stages"], ["基础"])
        self.assertTrue(classes[0]["is_manual_schedule_locked"])
        self.assertEqual(mappings[0]["local_product_id"], "P1")
        self.assertNotIn("canonical_product_id", mappings[0])
        self.assertEqual(product_courses[0]["window_name"], "暑假")
        self.assertEqual(product_courses[0]["module_priority_in_group"], 3)
        for old_field in ("quarter", "module_priority", "block_hours", "teaching_area_ids"):
            self.assertNotIn(old_field, product_courses[0])
        self.assertEqual(product_rules[0]["product_id"], "P1")
        self.assertEqual(product_rules[0]["block_hours"], 4)
        for old_field in (
            "rule_name",
            "scope_type",
            "product_ids",
            "product_name_keywords",
            "subject",
            "stage",
            "course_module",
            "course_group",
            "start_date",
            "end_date",
            "excluded_weekdays",
            "exception_weekdays",
            "block_hours_override",
        ):
            self.assertNotIn(old_field, product_rules[0])

    def test_template_sync_standard_output_uses_admin_fieldnames(self) -> None:
        rows = enrich_rows(
            "product_schedule_rules",
            [
                {
                    "rule_id": "RULE1",
                    "product_id": "P1",
                    "product_name": "产品1",
                    "window_name": "暑假",
                    "allowed_weekdays": ["周一"],
                    "allowed_periods": ["AM"],
                    "block_hours": 4,
                    "unexpected": "不要写出",
                }
            ],
        )

        output = standard_output_rows("product_schedule_rules", rows, csv_export=True)

        self.assertEqual(output_fields_for_key("product_schedule_rules", csv_export=True), data_admin_server.PRODUCT_RULE_FIELDNAMES)
        self.assertLessEqual(set(output[0]), set(data_admin_server.PRODUCT_RULE_FIELDNAMES))
        self.assertNotIn("unexpected", output[0])

    def test_teacher_sync_outputs_current_template_fields_only(self) -> None:
        rows = enrich_rows(
            "teachers",
            [
                {
                    "id": "T_LEGACY",
                    "employee_id": "100001",
                    "name": "张老师",
                    "teacher_role": "教师",
                    "identity": "旧身份",
                    "employment_type": "全职",
                    "teacher_type": "旧教师类型",
                }
            ],
        )

        self.assertEqual(rows[0]["employee_id"], "100001")
        self.assertEqual(rows[0]["teacher_role"], "教师")
        self.assertEqual(rows[0]["employment_type"], "全职")
        for old_field in ("id", "identity", "teacher_type"):
            self.assertNotIn(old_field, rows[0])

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "teachers.csv"
            write_csv(path, rows)
            header = path.read_text(encoding="utf-8-sig").splitlines()[0].split(",")

        for old_field in ("id", "identity", "teacher_type"):
            self.assertNotIn(old_field, header)
        self.assertIn("employee_id", header)
        self.assertIn("teacher_role", header)
        self.assertIn("employment_type", header)

    def test_write_csv_uses_shared_formatter_and_keeps_union_field_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "template_sync.csv"
            write_csv(
                path,
                [
                    {"id": "1", "enabled": True, "tags": ["A", "B"]},
                    {"id": "2", "extra": "later"},
                ],
            )
            self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))
            text = path.read_text(encoding="utf-8-sig")
            rows = read_csv_rows(path)

        self.assertEqual(text.splitlines()[0], "id,enabled,tags,extra")
        self.assertEqual(rows[0]["enabled"], "是")
        self.assertEqual(rows[0]["tags"], "A|B")
        self.assertEqual(rows[1]["extra"], "later")

    def test_formal_template_csv_text_uses_shared_csv_formatting(self) -> None:
        text = formal_template.csv_text(
            [{"id": "1", "enabled": True, "tags": ["A", "B"]}],
            ["id", "enabled", "tags"],
        )

        self.assertTrue(text.startswith("\ufeff"))
        self.assertIn("1,是,A|B", text)


if __name__ == "__main__":
    unittest.main()
