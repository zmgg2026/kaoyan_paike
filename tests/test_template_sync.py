from __future__ import annotations

import unittest

from scripts.sync_template_workbook_to_admin_data import enrich_rows


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


if __name__ == "__main__":
    unittest.main()
