from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

import data_admin_server
from scripts.csv_utils import read_csv_rows
from scripts import sync_erp_standard_products as sync_products


class SyncErpStandardProductsTest(unittest.TestCase):
    def test_fieldnames_reuse_admin_schema(self) -> None:
        self.assertIs(sync_products.BUSINESS_PRODUCT_MAPPING_FIELDNAMES, data_admin_server.BUSINESS_PRODUCT_MAPPING_FIELDNAMES)
        self.assertIs(sync_products.ERP_STANDARD_PRODUCT_FIELDNAMES, data_admin_server.ERP_STANDARD_PRODUCT_FIELDNAMES)

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

    def test_business_mapping_output_uses_current_local_product_field_only(self) -> None:
        product = {
            "id": "P_LOCAL",
            "name": "本地产品",
            "product_line": "无忧计划",
            "sub_product": "无忧暑",
            "course_nature": "正课",
            "subject": "英语",
        }
        row = sync_products.mapping_row(product, None, "")

        self.assertEqual(row["local_product_id"], "P_LOCAL")
        self.assertNotIn("canonical_product_id", row)
        self.assertNotIn("canonical_product_id", sync_products.BUSINESS_PRODUCT_MAPPING_FIELDNAMES)

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "business_product_mappings.csv"
            sync_products.write_csv(path, [row], sync_products.BUSINESS_PRODUCT_MAPPING_FIELDNAMES)
            header = path.read_text(encoding="utf-8").splitlines()[0].split(",")

        self.assertIn("local_product_id", header)
        self.assertNotIn("canonical_product_id", header)


if __name__ == "__main__":
    unittest.main()
