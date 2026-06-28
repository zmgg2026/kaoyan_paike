from __future__ import annotations

import unittest

import data_admin_server
from scripts import field_utils
from scripts import product_catalog


class ProductCatalogTest(unittest.TestCase):
    def test_admin_exports_shared_product_catalog_helpers_for_compatibility(self) -> None:
        self.assertIs(data_admin_server.normalize_int, field_utils.normalize_int)
        self.assertIs(data_admin_server.normalize_date_text, field_utils.normalize_date_text)
        self.assertIs(data_admin_server.product_catalog, product_catalog.product_catalog)
        self.assertIs(data_admin_server.sort_stage_values, product_catalog.sort_stage_values)
        self.assertIs(data_admin_server.product_stage_order, product_catalog.product_stage_order)
        self.assertIs(data_admin_server.DEFAULT_STAGE_ORDER, product_catalog.DEFAULT_STAGE_ORDER)

    def test_product_catalog_adds_course_only_products_with_current_labels(self) -> None:
        catalog = product_catalog.product_catalog(
            [],
            [{"product_id": "P_WY", "product_name": "考研无忧暑英语班"}],
        )

        self.assertEqual(catalog["P_WY"]["name"], "考研无忧暑英语班")
        self.assertEqual(catalog["P_WY"]["project"], "考研")
        self.assertEqual(catalog["P_WY"]["product_line"], "考研无忧")
        self.assertEqual(catalog["P_WY"]["sub_product"], "无忧暑")

    def test_existing_product_rows_win_over_course_fallback(self) -> None:
        catalog = product_catalog.product_catalog(
            [{"id": "P1", "name": "手工产品", "product_system": "常规体系"}],
            [{"product_id": "P1", "product_name": "课程侧产品名"}],
        )

        self.assertEqual(catalog["P1"]["name"], "手工产品")
        self.assertEqual(catalog["P1"]["product_system"], "常规体系")

    def test_stage_order_matches_business_sequence(self) -> None:
        self.assertEqual(
            ["导学1", "导学2", "基础", "强化", "冲刺", "四轮"],
            product_catalog.sort_stage_values(["强化", "四轮", "导学2", "冲刺", "基础", "导学1"]),
        )
        self.assertEqual(product_catalog.DEFAULT_STAGE_ORDER, product_catalog.product_stage_order({}))


if __name__ == "__main__":
    unittest.main()
