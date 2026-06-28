from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from scripts.csv_utils import clean_cell, read_csv_rows, read_csv_with_fieldnames, write_csv_rows


class CsvUtilsTest(unittest.TestCase):
    def test_clean_cell_trims_and_normalizes_empty_values(self) -> None:
        self.assertEqual(clean_cell("  A  "), "A")
        self.assertEqual(clean_cell(None), "")

    def test_read_csv_rows_accepts_utf8_sig_and_returns_dicts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rows.csv"
            path.write_text("\ufeffid,name\n1,张三\n", encoding="utf-8")

            self.assertEqual(read_csv_rows(path), [{"id": "1", "name": "张三"}])
            self.assertEqual(read_csv_with_fieldnames(path), (["id", "name"], [{"id": "1", "name": "张三"}]))

    def test_write_csv_rows_filters_to_declared_fields_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rows.csv"
            write_csv_rows(path, ["id", "name"], [{"id": "1", "name": "张三", "extra": "ignored"}])

            with path.open(newline="", encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(rows, [{"id": "1", "name": "张三"}])

    def test_write_csv_rows_can_raise_for_extra_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rows.csv"
            with self.assertRaises(ValueError):
                write_csv_rows(path, ["id"], [{"id": "1", "extra": "boom"}], extrasaction="raise")


if __name__ == "__main__":
    unittest.main()
