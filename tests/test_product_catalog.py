from __future__ import annotations

import unittest

import data_admin_server
import scheduler
from scripts import field_utils
from scripts import product_catalog


class ProductCatalogTest(unittest.TestCase):
    def test_admin_exports_shared_product_catalog_helpers_for_compatibility(self) -> None:
        self.assertIs(data_admin_server.normalize_blank_marker, field_utils.normalize_blank_marker)
        self.assertIs(scheduler.blank_marker_to_empty, field_utils.normalize_blank_marker)
        self.assertIs(data_admin_server.normalize_int, field_utils.normalize_int)
        self.assertIs(data_admin_server.normalize_date_text, field_utils.normalize_date_text)
        self.assertIs(data_admin_server.normalize_time_text, field_utils.normalize_time_text)
        self.assertIs(scheduler.normalize_time_value, field_utils.normalize_time_text)
        self.assertIs(data_admin_server.product_catalog, product_catalog.product_catalog)
        self.assertIs(data_admin_server.sort_stage_values, product_catalog.sort_stage_values)
        self.assertIs(data_admin_server.product_stage_order, product_catalog.product_stage_order)
        self.assertIs(data_admin_server.DEFAULT_STAGE_ORDER, product_catalog.DEFAULT_STAGE_ORDER)
        self.assertIs(data_admin_server.PRODUCT_PROJECT_OPTIONS, product_catalog.PRODUCT_PROJECT_OPTIONS)
        self.assertIs(data_admin_server.PRODUCT_LINE_OPTIONS, product_catalog.PRODUCT_LINE_OPTIONS)

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
        self.assertEqual(
            product_catalog.infer_stage_order_from_context("无忧寒"),
            ["寒假", "春季", "暑假", "秋季"],
        )
        self.assertEqual(
            product_catalog.infer_stage_order_from_context("考研全年营"),
            ["一轮", "二轮", "三轮", "四轮"],
        )
        self.assertEqual(
            product_catalog.infer_stage_order_from_context("无忧秋"),
            ["基础", "强化", "冲刺"],
        )
        self.assertEqual(product_catalog.infer_stage_order_from_context("冲刺营"), ["冲刺"])
        self.assertEqual(
            product_catalog.stage_rank_map_from_context("寒暑营"),
            {"寒假": 0, "春季": 1, "暑假": 2, "秋季": 3, "基础": 0, "强化": 1, "冲刺": 2},
        )
        self.assertEqual(
            product_catalog.stage_rank_map_from_context("考研全年营"),
            {"导学1": 0, "导学2": 1, "一轮": 2, "二轮": 3, "三轮": 4, "四轮": 5},
        )

    def test_product_project_and_line_options_are_shared(self) -> None:
        self.assertEqual(product_catalog.PRODUCT_PROJECT_OPTIONS, ["考研", "专升本", "四六级"])
        self.assertEqual(
            product_catalog.PRODUCT_LINE_OPTIONS,
            ["考研复试", "考研集训营", "考研无忧", "考研个性化", "考研其他", "专升本", "四六级"],
        )


if __name__ == "__main__":
    unittest.main()
