from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import audit_schedule_quality
from scripts import repair_schedule_quality_hotspots
from scripts.audit_schedule_coverage import is_public_auto_class, load_class_metadata, main as coverage_main, scheduled_hours
from scripts.repair_public_coverage_gaps import gap_key, halfday_rows


class ScheduleAuditTest(unittest.TestCase):
    def test_coverage_audit_infers_public_class_metadata_from_compact_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            with (data_dir / "classes.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["id", "name", "product_id", "suite_code", "is_schedule_locked"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "id": "KYYY2750",
                        "name": "考研英语寒暑集训营",
                        "product_id": "KYHSY_ZK_YY",
                        "suite_code": "2750",
                        "is_schedule_locked": "否",
                    }
                )

            metadata = load_class_metadata(data_dir)

        info = metadata["KYYY2750"]
        self.assertEqual(info.subject, "英语")
        self.assertEqual(info.subject_category, "公共课")
        self.assertTrue(is_public_auto_class(info))

        info.is_locked = "锁定"
        self.assertFalse(is_public_auto_class(info))

    def test_coverage_audit_prefers_current_manual_lock_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            with (data_dir / "classes.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["id", "name", "product_id", "is_manual_schedule_locked", "is_schedule_locked"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "id": "KYYY2750",
                        "name": "考研英语寒暑集训营",
                        "product_id": "KYHSY_ZK_YY",
                        "is_manual_schedule_locked": "否",
                        "is_schedule_locked": "是",
                    }
                )
                writer.writerow(
                    {
                        "id": "KYZZ2750",
                        "name": "考研政治寒暑集训营",
                        "product_id": "KYHSY_ZK_ZZ",
                        "is_manual_schedule_locked": "是",
                        "is_schedule_locked": "否",
                    }
                )

            metadata = load_class_metadata(data_dir)

        self.assertEqual(metadata["KYYY2750"].is_locked, "否")
        self.assertTrue(is_public_auto_class(metadata["KYYY2750"]))
        self.assertEqual(metadata["KYZZ2750"].is_locked, "是")
        self.assertFalse(is_public_auto_class(metadata["KYZZ2750"]))

    def test_coverage_audit_accepts_current_window_name_schedule_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            schedule_csv = Path(tmp) / "schedule.csv"
            with schedule_csv.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "class_id",
                        "subject",
                        "window_name",
                        "quarter",
                        "stage",
                        "course_module",
                        "course_group",
                        "teacher_id",
                        "duration_hours",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "class_id": "C1",
                        "subject": "英语",
                        "window_name": "暑假",
                        "quarter": "旧窗口",
                        "stage": "基础",
                        "course_module": "词汇",
                        "course_group": "阅读类",
                        "teacher_id": "T1",
                        "duration_hours": "2",
                    }
                )

            hours = scheduled_hours(schedule_csv)

        self.assertEqual(hours[("C1", "英语", "暑假", "基础", "词汇", "阅读类", "T1")], 2)

    def test_coverage_audit_detail_outputs_current_window_name_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            data_dir = base / "data"
            out_dir = base / "outputs"
            data_dir.mkdir()
            out_dir.mkdir()
            (data_dir / "scheduler_input_draft.json").write_text(
                json.dumps(
                    {
                        "time_slots": [],
                        "rooms": [{"id": "R1", "capacity": 40}],
                        "products": [
                            {
                                "id": "P1",
                                "name": "产品1",
                                "requirements": [
                                    {
                                        "subject_category": "公共课",
                                        "subject": "英语",
                                        "window_name": "暑假",
                                        "stage": "基础",
                                        "course_module": "词汇",
                                        "course_group": "阅读类",
                                        "total_hours": 4,
                                        "block_hours": 2,
                                    }
                                ],
                            }
                        ],
                        "classes": [
                            {
                                "id": "C1",
                                "name": "测试班",
                                "product_id": "P1",
                                "preferred_room_ids": ["R1"],
                                "teacher_assignments": [
                                    {
                                        "subject": "英语",
                                        "stage": "基础",
                                        "course_module": "词汇",
                                        "course_group": "阅读类",
                                        "teacher_id": "T1",
                                        "teacher_name": "张老师",
                                    }
                                ],
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            schedule_csv = base / "schedule.csv"
            with schedule_csv.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "class_id",
                        "subject",
                        "window_name",
                        "stage",
                        "course_module",
                        "course_group",
                        "teacher_id",
                        "duration_hours",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "class_id": "C1",
                        "subject": "英语",
                        "window_name": "暑假",
                        "stage": "基础",
                        "course_module": "词汇",
                        "course_group": "阅读类",
                        "teacher_id": "T1",
                        "duration_hours": "2",
                    }
                )
            argv = [
                "audit_schedule_coverage.py",
                "--data-dir",
                str(data_dir),
                "--schedule-csv",
                str(schedule_csv),
                "--out-dir",
                str(out_dir),
                "--timestamp",
                "unit",
            ]

            with patch.object(sys, "argv", argv):
                coverage_main()

            gap_csv = out_dir / "schedule_coverage_detail_gaps_unit.csv"
            with gap_csv.open(newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)
                fieldnames = reader.fieldnames or []

        self.assertIn("window_name", fieldnames)
        self.assertNotIn("quarter", fieldnames)
        self.assertEqual(rows[0]["window_name"], "暑假")

    def test_public_gap_repair_reads_and_writes_current_window_name_field(self) -> None:
        current_gap_row = {
            "class_id": "C1",
            "subject": "英语",
            "window_name": "暑假",
            "quarter": "旧窗口",
            "stage": "基础",
            "course_module": "词汇",
            "course_group": "阅读类",
            "teacher_id": "T1",
        }
        task = {
            "class_id": "C1",
            "class_name": "测试班",
            "subject": "英语",
            "window_name": "暑假",
            "quarter": "旧窗口",
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

        self.assertEqual(gap_key(current_gap_row)[2], "暑假")
        current_rows = halfday_rows(
            task,
            "2026-07-01",
            "AM",
            ["date", "lesson_slot", "window_name", "stage", "course_module"],
        )
        legacy_rows = halfday_rows(
            task,
            "2026-07-01",
            "AM",
            ["date", "lesson_slot", "quarter", "stage", "course_module"],
        )

        self.assertEqual(current_rows[0]["window_name"], "暑假")
        self.assertNotIn("quarter", current_rows[0])
        self.assertEqual(legacy_rows[0]["quarter"], "暑假")

    def test_quality_audit_uses_shared_compact_class_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            with (data_dir / "classes.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["id", "name", "product_id", "suite_code"])
                writer.writeheader()
                writer.writerow(
                    {
                        "id": "KYZZ2750",
                        "name": "考研政治寒暑集训营",
                        "product_id": "KYHSY_ZK_ZZ",
                        "suite_code": "2750",
                    }
                )

            metadata = audit_schedule_quality.load_class_metadata(data_dir)

        self.assertEqual(metadata["KYZZ2750"]["subject"], "政治")
        self.assertEqual(metadata["KYZZ2750"]["subject_category"], "公共课")

    def test_quality_audit_and_repair_hotspots_share_room_metadata_reader(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "rooms.json").write_text(
                (
                    '{"rooms":[{"id":"R201","name":"环球209",'
                    '"teaching_area_id":"ARHFWY03","teaching_area_name":"环球"}]}'
                ),
                encoding="utf-8",
            )

            audit_rooms = audit_schedule_quality.load_room_metadata(data_dir)
            repair_rooms = repair_schedule_quality_hotspots.load_room_meta(data_dir)

        self.assertEqual(audit_rooms["R201"]["teaching_area_id"], "ARHFWY03")
        self.assertEqual(repair_rooms, audit_rooms)


if __name__ == "__main__":
    unittest.main()
