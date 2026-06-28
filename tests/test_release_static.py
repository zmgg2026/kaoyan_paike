from __future__ import annotations

import re
import unittest
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
PERSONAL_PATH_MARKERS = ("/Users/" + "plzhz", "Down" + "loads" + "/")
TEXT_RELEASE_SUFFIXES = {".csv", ".html", ".js", ".json", ".md", ".py", ".sh", ".txt", ".yml"}


def release_text_files() -> Iterable[Path]:
    top_level_files = [
        ROOT / ".env.example",
        ROOT / ".gitignore",
        ROOT / "LAUNCH_CHECKLIST.md",
        ROOT / "PUBLIC_SCHEDULE_DEPLOY.md",
        ROOT / "README.md",
        ROOT / "SCHEDULING_RULES_REVIEW_20260524.md",
    ]
    for path in top_level_files:
        yield path
    for directory in (".github", "cloudflare_schedule_publish", "docs", "examples", "scripts", "share", "tests", "web_admin"):
        for path in sorted((ROOT / directory).rglob("*")):
            if path.is_file() and path.suffix in TEXT_RELEASE_SUFFIXES:
                yield path
    for path in sorted(ROOT.glob("*.py")):
        yield path


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
        self.assertIn("scripts/build_release_archive.py", script)
        self.assertIn("git archive --format=zip", script)
        self.assertIn("git diff --quiet && git diff --cached --quiet", script)
        self.assertIn("Tracked working tree has uncommitted changes", script)
        self.assertIn('--zip "$WORK_DIR/release_package_audit.zip"', script)
        self.assertIn("schedule_coverage_audit_verify_run.md", script)
        self.assertIn("schedule_quality_report_verify_run.md", script)

    def test_release_verification_compiles_all_python_scripts(self) -> None:
        script = (ROOT / "scripts" / "verify_release.sh").read_text(encoding="utf-8")

        self.assertIn('export PYTHONPYCACHEPREFIX="$WORK_DIR/pycache"', script)
        self.assertIn('find scripts -name "*.py"', script)
        self.assertIn("-m py_compile \"$script_path\"", script)

    def test_release_surface_does_not_reintroduce_summer_lodging_constraints(self) -> None:
        forbidden_terms = [
            "camp_" + "lodging_" + "constraints",
            "schedule_" + "lodging",
            "summer_" + "room_" + "constraint",
            "暑假" + "住宿" + "上课" + "约束",
            "住宿" + "上课" + "约束",
        ]
        offenders = []
        for path in release_text_files():
            source = path.read_text(encoding="utf-8")
            matches = [term for term in forbidden_terms if term in source]
            if matches:
                offenders.append(f"{path.relative_to(ROOT)}: {', '.join(matches)}")

        self.assertEqual([], offenders)

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
            ROOT / "scripts" / "analyze_erp_import_failures.py",
            ROOT / "scripts" / "build_erp_retry_import.py",
            ROOT / "scripts" / "build_erp_lesson_id_map.py",
            ROOT / "scripts" / "build_erp_reverse_import_from_result.py",
            ROOT / "scripts" / "build_failed_erp_class_schedule_review.py",
            ROOT / "scripts" / "build_camp_maintenance_schedule.py",
            ROOT / "scripts" / "build_cloudflare_publish_bundle.py",
            ROOT / "scripts" / "compare_history_remaining_changes.py",
            ROOT / "scripts" / "export_erp_adjusted_lesson_import.py",
            ROOT / "scripts" / "export_erp_lesson_import.py",
            ROOT / "scripts" / "fix_teacher_employee_ids.py",
            ROOT / "scripts" / "repair_2726_summer_week_balance.py",
            ROOT / "scripts" / "repair_2757_halfday_blocks.py",
            ROOT / "scripts" / "repair_2792_extreme_weeks.py",
            ROOT / "scripts" / "repair_class_conflicts_and_ep_same_day.py",
            ROOT / "scripts" / "repair_public_coverage_gaps.py",
            ROOT / "scripts" / "repair_teacher_travel_swaps.py",
            ROOT / "scripts" / "repair_wyqc_foundation_deadlines.py",
            ROOT / "scripts" / "repair_wyqc_foundation_gaps.py",
            ROOT / "scripts" / "repair_wyqc_summer_week_balance.py",
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
            calls_stdlib_csv = bool(re.search(r"(?<![A-Za-z0-9_])csv\.", source))
            if imports_stdlib_csv or calls_stdlib_csv or "scripts.csv_utils" not in source:
                offenders.append(str(path.relative_to(ROOT)))

        self.assertEqual([], offenders)

    def test_erp_excel_modules_use_shared_excel_text_normalization(self) -> None:
        modules = [
            ROOT / "scripts" / "analyze_erp_import_failures.py",
            ROOT / "scripts" / "build_erp_lesson_id_map.py",
            ROOT / "scripts" / "build_erp_reverse_import_from_result.py",
            ROOT / "scripts" / "build_erp_retry_import.py",
            ROOT / "scripts" / "build_failed_erp_class_schedule_review.py",
            ROOT / "scripts" / "export_erp_lesson_import.py",
        ]
        offenders = []
        for path in modules:
            source = path.read_text(encoding="utf-8")
            if "normalize_excel_text as clean" not in source:
                offenders.append(f"{path.relative_to(ROOT)} does not import normalize_excel_text as clean")
            if re.search(r"(?m)^def clean\(", source):
                offenders.append(f"{path.relative_to(ROOT)} defines local clean")
            if "ROOT = Path(__file__).resolve().parents[1]" not in source or "sys.path.insert(0, str(ROOT))" not in source:
                offenders.append(f"{path.relative_to(ROOT)} is missing direct-script import bootstrap")

        self.assertEqual([], offenders)

    def test_schedule_display_owns_shared_calendar_helpers_for_repair_outputs(self) -> None:
        modules = [
            ROOT / "scripts" / "build_failed_erp_class_schedule_review.py",
            ROOT / "scripts" / "repair_2726_summer_week_balance.py",
            ROOT / "scripts" / "repair_public_coverage_gaps.py",
            ROOT / "scripts" / "repair_wyqc_foundation_deadlines.py",
            ROOT / "scripts" / "repair_wyqc_foundation_gaps.py",
            ROOT / "scripts" / "repair_wyqc_summer_week_balance.py",
            ROOT / "scripts" / "sync_erp_adjusted_schedule.py",
        ]
        offenders = []
        for path in modules:
            source = path.read_text(encoding="utf-8")
            if "from scripts.schedule_display import" not in source:
                offenders.append(f"{path.relative_to(ROOT)} does not import schedule_display")
            if re.search(r"(?m)^def (weekday_label|week_start)\(", source):
                offenders.append(f"{path.relative_to(ROOT)} defines local calendar helper")
            if re.search(r"(?m)^WEEKDAYS?(?:_LABELS)?\\s*=", source):
                offenders.append(f"{path.relative_to(ROOT)} defines local weekday labels")

        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
