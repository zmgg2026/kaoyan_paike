#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
TMP_ROOT="${TMPDIR:-/tmp}"
WORK_DIR="$(mktemp -d "$TMP_ROOT/ai-schedule-verify.XXXXXX")"

cleanup() {
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

run() {
  echo
  echo "==> $*"
  "$@"
}

cd "$ROOT_DIR"

echo "Release verification workspace: $WORK_DIR"

while IFS= read -r script_path; do
  run bash -n "$script_path"
done < <(find scripts -name "*.sh" -print | sort)

run "$PYTHON_BIN" -m py_compile \
  scheduler.py \
  run_scheduling_pipeline.py \
  data_admin_server.py \
  business_class_import.py \
  generate_time_slots.py \
  schedule_publish_server.py

while IFS= read -r script_path; do
  run "$PYTHON_BIN" -m py_compile "$script_path"
done < <(find scripts -name "*.py" -print | sort)

run "$PYTHON_BIN" scripts/audit_release_package.py --root "$ROOT_DIR"

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if git diff --quiet && git diff --cached --quiet; then
    run git archive --format=zip -o "$WORK_DIR/release_package_audit.zip" HEAD
  else
    echo "Tracked working tree has uncommitted changes; auditing a current tracked-file archive instead of HEAD."
    run "$PYTHON_BIN" scripts/build_release_archive.py --output "$WORK_DIR/release_package_audit.zip"
  fi
  run "$PYTHON_BIN" scripts/audit_release_package.py --zip "$WORK_DIR/release_package_audit.zip"
fi

run "$PYTHON_BIN" -m unittest discover -v

run "$PYTHON_BIN" scheduler.py \
  --input examples/input_example.json \
  --output "$WORK_DIR/input_example_schedule.csv" \
  --html-output "$WORK_DIR/input_example_schedule.html"

run "$PYTHON_BIN" run_scheduling_pipeline.py \
  --source examples/csv_minimal \
  --data-dir "$WORK_DIR/csv_minimal_data" \
  --output-dir "$WORK_DIR/csv_minimal_outputs" \
  --timestamp verify_preflight \
  --preflight

run "$PYTHON_BIN" run_scheduling_pipeline.py \
  --source examples/csv_minimal \
  --data-dir "$WORK_DIR/csv_minimal_data" \
  --output-dir "$WORK_DIR/csv_minimal_outputs" \
  --timestamp verify_run

run "$PYTHON_BIN" scripts/audit_schedule_coverage.py \
  --data-dir "$WORK_DIR/csv_minimal_data" \
  --schedule-csv "$WORK_DIR/csv_minimal_outputs/schedule_verify_run.csv" \
  --out-dir "$WORK_DIR/csv_minimal_outputs" \
  --timestamp verify_run

run "$PYTHON_BIN" scripts/audit_schedule_quality.py \
  --data-dir "$WORK_DIR/csv_minimal_data" \
  --schedule-csv "$WORK_DIR/csv_minimal_outputs/schedule_verify_run.csv" \
  --out-dir "$WORK_DIR/csv_minimal_outputs" \
  --timestamp verify_run

test -s "$WORK_DIR/input_example_schedule.csv"
test -s "$WORK_DIR/input_example_schedule.html"
test -s "$WORK_DIR/csv_minimal_outputs/schedule_verify_run.csv"
test -s "$WORK_DIR/csv_minimal_outputs/schedule_verify_run.html"
test -s "$WORK_DIR/csv_minimal_outputs/import_report_verify_run.md"
test -s "$WORK_DIR/csv_minimal_outputs/schedule_coverage_audit_verify_run.md"
test -s "$WORK_DIR/csv_minimal_outputs/schedule_quality_report_verify_run.md"

if [[ "${RUN_REAL_DATA_PREFLIGHT:-0}" == "1" && -d data ]]; then
  run "$PYTHON_BIN" run_scheduling_pipeline.py \
    --source data \
    --output-dir "$WORK_DIR/real_data_preflight" \
    --timestamp verify_real_data \
    --preflight
fi

echo
echo "Release verification passed."
