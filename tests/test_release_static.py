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

    def test_release_docs_do_not_ship_personal_paths(self) -> None:
        offenders = []
        paths = [ROOT / "README.md", ROOT / "PUBLIC_SCHEDULE_DEPLOY.md", ROOT / "LAUNCH_CHECKLIST.md"]
        paths.extend(sorted((ROOT / "docs").rglob("*.md")))
        paths.extend(sorted((ROOT / "share").rglob("*.html")))
        for path in paths:
            source = path.read_text(encoding="utf-8")
            if any(marker in source for marker in PERSONAL_PATH_MARKERS):
                offenders.append(str(path.relative_to(ROOT)))

        self.assertEqual([], offenders)

    def test_release_verification_runs_audits(self) -> None:
        script = (ROOT / "scripts" / "verify_release.sh").read_text(encoding="utf-8")

        self.assertIn("scripts/audit_schedule_coverage.py", script)
        self.assertIn("scripts/audit_schedule_quality.py", script)
        self.assertIn("schedule_coverage_audit_verify_run.md", script)
        self.assertIn("schedule_quality_report_verify_run.md", script)


if __name__ == "__main__":
    unittest.main()
