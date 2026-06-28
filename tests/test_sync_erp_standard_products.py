from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

from scripts.csv_utils import read_csv_rows
from scripts import sync_erp_standard_products as sync_products


class SyncErpStandardProductsTest(unittest.TestCase):
    def test_write_csv_uses_shared_helper_and_serializes_lists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "mappings.csv"
            sync_products.write_csv(
                path,
                [
                    {
                        "id": "P1",
                        "keywords": ["英语", "暑假", ""],
                        "name": " 产品一 ",
                        "ignored": "extra",
                    }
                ],
                ["id", "keywords", "name"],
            )

            self.assertFalse(path.read_bytes().startswith(b"\xef\xbb\xbf"))
            text = path.read_text(encoding="utf-8")
            rows = read_csv_rows(path)

        self.assertEqual(text.splitlines()[0], "id,keywords,name")
        self.assertEqual(rows, [{"id": "P1", "keywords": "英语|暑假", "name": "产品一"}])

    def test_text_normalizes_empty_and_nan_values_without_pandas(self) -> None:
        self.assertEqual(sync_products.text(None), "")
        self.assertEqual(sync_products.text(math.nan), "")
        self.assertEqual(sync_products.text(" 课程 "), "课程")


if __name__ == "__main__":
    unittest.main()
