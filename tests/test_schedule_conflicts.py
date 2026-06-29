from __future__ import annotations

import unittest

from scripts.schedule_conflicts import minutes


class ScheduleConflictsTest(unittest.TestCase):
    def test_minutes_reuses_shared_time_parsing(self) -> None:
        self.assertEqual(minutes("08:30:00"), 510)
        self.assertIsNone(minutes("25:00"))


if __name__ == "__main__":
    unittest.main()
