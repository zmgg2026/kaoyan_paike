from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from scripts import audit_schedule_quality
from scripts import repair_schedule_quality_hotspots
from scripts.audit_schedule_coverage import is_public_auto_class, load_class_metadata


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
