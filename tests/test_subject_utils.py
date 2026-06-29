from __future__ import annotations

import unittest

from scripts.subject_utils import (
    CORE_PUBLIC_SUBJECT_PREFERRED_PERIODS,
    CORE_PUBLIC_SUBJECTS,
    PUBLIC_SUBJECT_PLACEMENT_ORDER,
    PUBLIC_SUBJECT_SORT_ORDER,
    PUBLIC_SUBJECTS_WITH_CHINESE,
    subject_placement_value,
    subject_sort_value,
)


class SubjectUtilsTest(unittest.TestCase):
    def test_core_public_subjects_are_shared(self) -> None:
        self.assertEqual(CORE_PUBLIC_SUBJECTS, frozenset({"英语", "政治", "数学"}))

    def test_public_subjects_with_chinese_are_shared(self) -> None:
        self.assertEqual(PUBLIC_SUBJECTS_WITH_CHINESE, frozenset({"英语", "政治", "数学", "语文"}))

    def test_public_subject_sort_order_is_shared(self) -> None:
        self.assertEqual(PUBLIC_SUBJECT_SORT_ORDER, {"数学": 0, "英语": 1, "政治": 2, "语文": 3})
        self.assertEqual(subject_sort_value(" 数学 "), 0)
        self.assertEqual(subject_sort_value("未知"), 99)

    def test_core_public_subject_preferred_periods_are_shared(self) -> None:
        self.assertEqual(CORE_PUBLIC_SUBJECT_PREFERRED_PERIODS, {"数学": "AM", "英语": "PM", "政治": "PM"})

    def test_public_subject_placement_order_is_shared(self) -> None:
        self.assertEqual(PUBLIC_SUBJECT_PLACEMENT_ORDER, {"数学": 0, "政治": 1, "英语": 2, "语文": 3})
        self.assertEqual(subject_placement_value(" 政治 "), 1)
        self.assertEqual(subject_placement_value("专业课"), 99)


if __name__ == "__main__":
    unittest.main()
