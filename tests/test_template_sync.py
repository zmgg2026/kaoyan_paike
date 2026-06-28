from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import formal_template
from scripts.csv_utils import read_csv_rows
from scripts.sync_template_workbook_to_admin_data import enrich_rows, write_csv


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
                    "selected_stages": ["基础"],
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
                    "window_name": "暑假",
                    "course_module": "词汇",
                    "teaching_area_ids": ["A1"],
                }
            ],
        )

        self.assertNotIn("actual_schedule_window_ids", classes[0])
        self.assertEqual(mappings[0]["local_product_id"], "P1")
        self.assertNotIn("canonical_product_id", mappings[0])
        self.assertNotIn("teaching_area_ids", product_courses[0])

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
