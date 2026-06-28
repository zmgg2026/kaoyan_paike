from __future__ import annotations

import re
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
        self.assertIn("scripts/audit_release_package.py", script)
        self.assertIn("schedule_coverage_audit_verify_run.md", script)
        self.assertIn("schedule_quality_report_verify_run.md", script)

    def test_release_verification_compiles_all_python_scripts(self) -> None:
        script = (ROOT / "scripts" / "verify_release.sh").read_text(encoding="utf-8")

        self.assertIn('find scripts -name "*.py"', script)
        self.assertIn("-m py_compile \"$script_path\"", script)

    def test_ci_runs_release_verification(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

        self.assertIn("actions/setup-python", workflow)
        self.assertIn("python3 -m pip install -r requirements.txt", workflow)
        self.assertIn("bash scripts/verify_release.sh", workflow)

    def test_release_path_modules_use_csv_utils_for_csv_io(self) -> None:
        modules = [
            ROOT / "business_class_import.py",
            ROOT / "formal_template.py",
            ROOT / "scheduler.py",
            ROOT / "run_scheduling_pipeline.py",
            ROOT / "scripts" / "build_camp_maintenance_schedule.py",
            ROOT / "scripts" / "build_cloudflare_publish_bundle.py",
            ROOT / "scripts" / "schedule_batch.py",
            ROOT / "scripts" / "schedule_data.py",
            ROOT / "scripts" / "schedule_class_windows.py",
            ROOT / "scripts" / "schedule_conflicts.py",
            ROOT / "scripts" / "schedule_outputs.py",
            ROOT / "scripts" / "schedule_scope.py",
            ROOT / "scripts" / "sync_erp_standard_products.py",
            ROOT / "scripts" / "sync_template_workbook_to_admin_data.py",
        ]
        offenders = []
        for path in modules:
            source = path.read_text(encoding="utf-8")
            imports_stdlib_csv = bool(re.search(r"(?m)^\s*(import\s+csv\b|from\s+csv\s+import\b)", source))
            if imports_stdlib_csv or "csv." in source or "scripts.csv_utils" not in source:
                offenders.append(str(path.relative_to(ROOT)))

        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
