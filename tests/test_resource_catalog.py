from __future__ import annotations

import unittest

import data_admin_server
from scripts import resource_catalog


class ResourceCatalogTest(unittest.TestCase):
    def test_admin_exports_shared_teacher_resource_options(self) -> None:
        self.assertIs(data_admin_server.TEACHER_GENDER_OPTIONS, resource_catalog.TEACHER_GENDER_OPTIONS)
        self.assertIs(data_admin_server.TEACHER_ROLE_OPTIONS, resource_catalog.TEACHER_ROLE_OPTIONS)
        self.assertIs(data_admin_server.TEACHER_EMPLOYMENT_TYPE_OPTIONS, resource_catalog.TEACHER_EMPLOYMENT_TYPE_OPTIONS)
        self.assertIs(data_admin_server.TEACHER_SUBJECT_TYPE_OPTIONS, resource_catalog.TEACHER_SUBJECT_TYPE_OPTIONS)
        self.assertIs(data_admin_server.TEACHER_CONTRACT_STATUS_OPTIONS, resource_catalog.TEACHER_CONTRACT_STATUS_OPTIONS)
        self.assertIs(data_admin_server.TEACHER_EMPLOYMENT_STATUS_OPTIONS, resource_catalog.TEACHER_EMPLOYMENT_STATUS_OPTIONS)

    def test_teacher_resource_options_match_template_values(self) -> None:
        self.assertEqual(resource_catalog.TEACHER_GENDER_OPTIONS, ["男", "女", "其他"])
        self.assertEqual(resource_catalog.TEACHER_ROLE_OPTIONS, ["管理者", "教师"])
        self.assertEqual(resource_catalog.TEACHER_EMPLOYMENT_TYPE_OPTIONS, ["全职", "兼职", "外聘", "内部"])
        self.assertEqual(resource_catalog.TEACHER_SUBJECT_TYPE_OPTIONS, ["公共课", "专业课"])
        self.assertEqual(resource_catalog.TEACHER_CONTRACT_STATUS_OPTIONS, ["已签约", "未签约", "待续签", "已终止"])
        self.assertEqual(resource_catalog.TEACHER_EMPLOYMENT_STATUS_OPTIONS, ["在职", "离职", "停用", "待入职"])


if __name__ == "__main__":
    unittest.main()
