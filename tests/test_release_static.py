from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PERSONAL_PATH_MARKERS = ("/Users/" + "plzhz", "Down" + "loads" + "/")


class ReleaseStaticTest(unittest.TestCase):
    def test_scripts_do_not_ship_personal_default_paths(self) -> None:
        offenders = []
        for path in sorted((ROOT / "scripts").glob("*.py")):
            source = path.read_text(encoding="utf-8")
            if any(marker in source for marker in PERSONAL_PATH_MARKERS):
                offenders.append(str(path.relative_to(ROOT)))

        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
