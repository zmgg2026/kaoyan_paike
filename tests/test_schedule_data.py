from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.schedule_data import (
    load_active_blackout_dates,
    load_area_links,
    load_area_metadata,
    load_class_metadata,
    load_room_maps,
    load_room_metadata,
    load_room_name_to_id,
    load_room_names,
    load_teacher_maps,
    load_teacher_name_to_id,
)


class ScheduleDataTest(unittest.TestCase):
    def test_load_class_metadata_accepts_directory_or_csv_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            classes_path = data_dir / "classes.csv"
            with classes_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["id", "name", "product_id", "suite_code", "product_line", "subject"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "id": "CLASS_A",
                        "name": "测试班",
                        "product_id": "P1",
                        "suite_code": "2726",
                        "product_line": "考研无忧",
                        "subject": "数学",
                    }
                )

            from_directory = load_class_metadata(data_dir)
            from_csv = load_class_metadata(classes_path)

        self.assertEqual(from_csv, from_directory)
        self.assertEqual(from_csv["CLASS_A"]["suite_code"], "2726")
        self.assertEqual(from_csv["CLASS_A"]["product_line"], "考研无忧")

    def test_load_class_metadata_prefers_current_manual_lock_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            classes_path = data_dir / "classes.csv"
            with classes_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["id", "is_manual_schedule_locked", "is_schedule_locked"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "id": "CLASS_UNLOCKED_CURRENT",
                        "is_manual_schedule_locked": "否",
                        "is_schedule_locked": "是",
                    }
                )
                writer.writerow(
                    {
                        "id": "CLASS_LOCKED_LEGACY",
                        "is_manual_schedule_locked": "",
                        "is_schedule_locked": "是",
                    }
                )

            metadata = load_class_metadata(data_dir)

        self.assertEqual(metadata["CLASS_UNLOCKED_CURRENT"]["is_manual_schedule_locked"], "否")
        self.assertNotIn("is_schedule_locked", metadata["CLASS_UNLOCKED_CURRENT"])
        self.assertEqual(metadata["CLASS_LOCKED_LEGACY"]["is_manual_schedule_locked"], "是")
        self.assertNotIn("is_schedule_locked", metadata["CLASS_LOCKED_LEGACY"])

    def test_load_class_metadata_prefers_current_selected_stages_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            classes_path = data_dir / "classes.csv"
            with classes_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["id", "selected_stages", "stages", "stage"])
                writer.writeheader()
                writer.writerow(
                    {
                        "id": "CLASS_CURRENT",
                        "selected_stages": "基础|强化",
                        "stages": "旧阶段",
                        "stage": "更旧阶段",
                    }
                )
                writer.writerow(
                    {
                        "id": "CLASS_LEGACY",
                        "selected_stages": "",
                        "stages": "冲刺",
                        "stage": "更旧阶段",
                    }
                )

            metadata = load_class_metadata(data_dir)

        self.assertEqual(metadata["CLASS_CURRENT"]["selected_stages"], "基础|强化")
        self.assertNotIn("stages", metadata["CLASS_CURRENT"])
        self.assertEqual(metadata["CLASS_LEGACY"]["selected_stages"], "冲刺")
        self.assertNotIn("stages", metadata["CLASS_LEGACY"])

    def test_load_class_metadata_infers_subject_for_compact_class_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            classes_path = data_dir / "classes.csv"
            with classes_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["id", "name", "product_id"])
                writer.writeheader()
                writer.writerow(
                    {
                        "id": "KYHSY2750",
                        "name": "考研英语寒暑集训营",
                        "product_id": "KYHSY_ZK_YY",
                    }
                )

            metadata = load_class_metadata(data_dir)

        self.assertEqual(metadata["KYHSY2750"]["subject"], "英语")
        self.assertEqual(metadata["KYHSY2750"]["subject_category"], "公共课")

    def test_load_room_name_to_id_accepts_directory_or_csv_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            rooms_path = data_dir / "rooms.csv"
            with rooms_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["id", "name"])
                writer.writeheader()
                writer.writerow({"id": "R101", "name": "汇金403"})
                writer.writerow({"id": "R102", "name": "汇金403"})
                writer.writerow({"id": "R103", "name": "环球209"})

            from_directory = load_room_name_to_id(data_dir)
            from_csv = load_room_name_to_id(rooms_path)

        self.assertEqual(from_csv, from_directory)
        self.assertEqual(from_csv["汇金403"], "R101")
        self.assertEqual(from_csv["环球209"], "R103")

    def test_load_room_maps_only_reverse_maps_unique_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            rooms_path = data_dir / "rooms.csv"
            with rooms_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["id", "name"])
                writer.writeheader()
                writer.writerow({"id": "R101", "name": "汇金403"})
                writer.writerow({"id": "R102", "name": "汇金403"})
                writer.writerow({"id": "R103", "name": "环球209"})

            by_id, by_name = load_room_maps(data_dir)

        self.assertEqual(by_id, {"R101": "汇金403", "R102": "汇金403", "R103": "环球209"})
        self.assertNotIn("汇金403", by_name)
        self.assertEqual(by_name["环球209"], "R103")

    def test_load_room_names_accepts_directory_json_or_csv_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            rooms_csv = data_dir / "rooms.csv"
            with rooms_csv.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["id", "name"])
                writer.writeheader()
                writer.writerow({"id": "R101", "name": "汇金403"})
                writer.writerow({"id": "R102", "name": ""})

            from_directory_csv = load_room_names(data_dir)
            from_csv = load_room_names(rooms_csv)

            rooms_json = data_dir / "rooms.json"
            rooms_json.write_text(
                json.dumps({"rooms": [{"id": "R201", "name": "环球209"}]}, ensure_ascii=False),
                encoding="utf-8",
            )
            from_directory_json = load_room_names(data_dir)
            from_json = load_room_names(rooms_json)

        self.assertEqual(from_directory_csv, {"R101": "汇金403", "R102": "R102"})
        self.assertEqual(from_csv, from_directory_csv)
        self.assertEqual(from_directory_json, {"R201": "环球209"})
        self.assertEqual(from_json, from_directory_json)

    def test_load_room_metadata_accepts_directory_json_or_csv_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            rooms_csv = data_dir / "rooms.csv"
            with rooms_csv.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["id", "name", "teaching_area_id"])
                writer.writeheader()
                writer.writerow({"id": "R101", "name": "汇金403", "teaching_area_id": "A1"})

            from_directory_csv = load_room_metadata(data_dir)
            from_csv = load_room_metadata(rooms_csv)

            rooms_json = data_dir / "rooms.json"
            rooms_json.write_text(
                json.dumps(
                    {
                        "rooms": [
                            {
                                "id": "R201",
                                "name": "环球209",
                                "teaching_area_id": "A2",
                                "is_active": False,
                                "capacity": 0,
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            from_directory_json = load_room_metadata(data_dir)
            from_json = load_room_metadata(rooms_json)

        self.assertEqual(from_directory_csv["R101"]["teaching_area_id"], "A1")
        self.assertEqual(from_csv, from_directory_csv)
        self.assertEqual(from_directory_json["R201"]["teaching_area_id"], "A2")
        self.assertEqual(from_directory_json["R201"]["is_active"], "False")
        self.assertEqual(from_directory_json["R201"]["capacity"], "0")
        self.assertEqual(from_json, from_directory_json)

    def test_load_area_metadata_and_links_use_current_resource_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            with (data_dir / "teaching_areas.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["id", "name", "region"])
                writer.writeheader()
                writer.writerow({"id": "A_NS", "name": "新站校区", "region": "新站"})
                writer.writerow({"id": "", "name": "空行", "region": ""})
            with (data_dir / "teaching_area_links.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["from_teaching_area_id", "to_teaching_area_id", "travel_minutes", "relation_type"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "from_teaching_area_id": "A_NS",
                        "to_teaching_area_id": "A_BH",
                        "travel_minutes": " 40 ",
                        "relation_type": "跨区",
                    }
                )
                writer.writerow(
                    {
                        "from_teaching_area_id": "",
                        "to_teaching_area_id": "A_IGNORED",
                        "travel_minutes": "99",
                        "relation_type": "无效",
                    }
                )

            areas = load_area_metadata(data_dir)
            links = load_area_links(data_dir)

        self.assertEqual(areas, {"A_NS": {"id": "A_NS", "name": "新站校区", "region": "新站"}})
        self.assertEqual(links[("A_NS", "A_BH")]["travel_minutes"], "40")
        self.assertIs(links[("A_NS", "A_BH")], links[("A_BH", "A_NS")])
        self.assertNotIn(("", "A_IGNORED"), links)

    def test_load_teacher_name_to_id_defaults_to_six_digit_employee_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            teachers_path = data_dir / "teachers.csv"
            with teachers_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["employee_id", "name"])
                writer.writeheader()
                writer.writerow({"employee_id": "000123", "name": "张老师"})
                writer.writerow({"employee_id": "T2", "name": "李老师"})

            strict = load_teacher_name_to_id(data_dir)
            loose = load_teacher_name_to_id(teachers_path, require_six_digit=False)

        self.assertEqual(strict, {"张老师": "000123"})
        self.assertEqual(loose["张老师"], "000123")
        self.assertEqual(loose["李老师"], "T2")

    def test_load_teacher_maps_combines_teacher_base_and_assignments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            with (data_dir / "teachers.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["employee_id", "name"])
                writer.writeheader()
                writer.writerow({"employee_id": "100001", "name": "张老师"})
            with (data_dir / "class_teacher_assignments.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["teacher_id", "teacher_name"])
                writer.writeheader()
                writer.writerow({"teacher_id": "T_EXT", "teacher_name": "外聘老师"})

            by_id, by_name = load_teacher_maps(data_dir)

        self.assertEqual(by_id["100001"], "张老师")
        self.assertEqual(by_name["张老师"], "100001")
        self.assertEqual(by_id["T_EXT"], "外聘老师")
        self.assertEqual(by_name["外聘老师"], "T_EXT")

    def test_load_active_blackout_dates_expands_enabled_ranges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            with (data_dir / "global_blackout_dates.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["start_date", "end_date", "is_active"])
                writer.writeheader()
                writer.writerow({"start_date": "2026-10-01", "end_date": "2026-10-03", "is_active": "是"})
                writer.writerow({"start_date": "2026-10-04", "end_date": "", "is_active": ""})
                writer.writerow({"start_date": "2026-10-05", "end_date": "", "is_active": "否"})

            dates = load_active_blackout_dates(data_dir)

        self.assertEqual(dates, {"2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"})


if __name__ == "__main__":
    unittest.main()
