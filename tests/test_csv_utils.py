from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from scripts.csv_utils import (
    clean_csv_rows,
    csv_rows_text,
    clean_cell,
    read_csv_text,
    read_csv_rows,
    read_csv_text_with_fieldnames,
    read_csv_with_fieldnames,
    serialize_csv_value,
    write_csv_rows,
)


class CsvUtilsTest(unittest.TestCase):
    def test_clean_cell_trims_and_normalizes_empty_values(self) -> None:
        self.assertEqual(clean_cell("  A  "), "A")
        self.assertEqual(clean_cell(None), "")
        self.assertEqual(clean_cell(0), "0")
        self.assertEqual(clean_cell(False), "False")

    def test_read_csv_rows_accepts_utf8_sig_and_returns_dicts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rows.csv"
            path.write_text("\ufeffid,name\n1,张三\n", encoding="utf-8")

            self.assertEqual(read_csv_rows(path), [{"id": "1", "name": "张三"}])
            self.assertEqual(read_csv_with_fieldnames(path), (["id", "name"], [{"id": "1", "name": "张三"}]))
            self.assertEqual(
                read_csv_text_with_fieldnames("\ufeffid,name\n2,李四\n"),
                (["id", "name"], [{"id": "2", "name": "李四"}]),
            )

    def test_read_csv_with_fieldnames_accepts_gb18030_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rows.csv"
            path.write_bytes("id,name\n1,张三\n".encode("gb18030"))

            self.assertIn("张三", read_csv_text(path))
            self.assertEqual(read_csv_with_fieldnames(path), (["id", "name"], [{"id": "1", "name": "张三"}]))

    def test_clean_csv_rows_strips_headers_values_and_drops_empty_rows(self) -> None:
        rows = clean_csv_rows(
            [
                {" id ": " 1 ", "name": " 张三 ", None: "ignored"},
                {" id ": " ", "name": None},
            ]
        )

        self.assertEqual(rows, [{"id": "1", "name": "张三"}])

    def test_write_csv_rows_filters_to_declared_fields_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rows.csv"
            write_csv_rows(path, ["id", "name"], [{"id": "1", "name": "张三", "extra": "ignored"}])

            with path.open(newline="", encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(rows, [{"id": "1", "name": "张三"}])

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rows.csv"
            write_csv_rows(path, ["id"], [{"id": "1"}], encoding="utf-8")

            self.assertFalse(path.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_csv_rows_text_can_format_values_and_include_bom(self) -> None:
        def formatter(value: object) -> str:
            if isinstance(value, bool):
                return "是" if value else "否"
            if isinstance(value, list):
                return "|".join(str(item) for item in value)
            return str(value or "")

        text = csv_rows_text(
            ["id", "active", "tags"],
            [{"id": "1", "active": True, "tags": ["A", "B"]}],
            bom=True,
            value_formatter=formatter,
        )

        self.assertTrue(text.startswith("\ufeff"))
        self.assertIn("1,是,A|B", text)

    def test_serialize_csv_value_matches_template_and_admin_format(self) -> None:
        self.assertEqual(serialize_csv_value(None), "")
        self.assertEqual(serialize_csv_value(True), "是")
        self.assertEqual(serialize_csv_value(False), "否")
        self.assertEqual(serialize_csv_value(["A", "B"]), "A|B")
        self.assertEqual(serialize_csv_value(0), "0")

    def test_write_csv_rows_can_raise_for_extra_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rows.csv"
            with self.assertRaises(ValueError):
                write_csv_rows(path, ["id"], [{"id": "1", "extra": "boom"}], extrasaction="raise")


if __name__ == "__main__":
    unittest.main()
