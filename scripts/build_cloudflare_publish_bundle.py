#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import shutil
import sys
from pathlib import Path
from typing import List


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DEFAULT_OUTPUT_DIR = ROOT / "outputs"
DEFAULT_BUNDLE_DIR = DEFAULT_OUTPUT_DIR / "cloudflare_schedule_publish"
WORKER_SOURCE = ROOT / "cloudflare_schedule_publish" / "_worker.js"


def copy_required(source: Path, target: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(f"缺少发布源文件: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def validate_no_public_coverage_gaps(output_dir: Path) -> None:
    summary_path = output_dir / "schedule_coverage_summary_latest_publish_check.csv"
    import scheduler
    from scripts import audit_schedule_coverage as coverage

    schedule_csv = output_dir / "batch_schedule_maintenance.csv"
    schedule_input = scheduler.load_input(ROOT / "data" / "scheduler_input_draft.json")
    metadata = coverage.load_class_metadata(ROOT / "data")
    expected_totals = coverage.class_totals(coverage.expected_hours(schedule_input, ignore_teacher=True))
    scheduled_totals = coverage.class_totals(coverage.scheduled_hours(schedule_csv, ignore_teacher=True))
    rows: List[dict] = []
    for class_id in sorted(expected_totals):
        meta = metadata.get(class_id)
        if not meta or meta.subject_category != "公共课":
            continue
        if meta.is_locked.strip().lower() in {"是", "1", "true", "yes", "y"}:
            continue
        expected = float(expected_totals[class_id])
        scheduled = float(scheduled_totals[class_id])
        gap = expected - scheduled
        if gap <= 0.01:
            continue
        rows.append(
            {
                "class_id": class_id,
                "class_name": meta.class_name,
                "sub_product": meta.sub_product,
                "subject": meta.subject,
                "suite_code": meta.suite_code,
                "expected_hours": expected,
                "scheduled_hours": scheduled,
                "gap_hours": gap,
            }
        )
    if not rows:
        return

    rows.sort(key=lambda row: (-float(row["gap_hours"]), str(row["sub_product"]), str(row["suite_code"]), str(row["class_id"])))
    with summary_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "class_id",
                "class_name",
                "sub_product",
                "subject",
                "suite_code",
                "expected_hours",
                "scheduled_hours",
                "gap_hours",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    total_gap = sum(float(row["gap_hours"]) for row in rows)
    first = rows[0]
    raise RuntimeError(
        "课表存在公共课班级总课时缺口，已停止生成发布包: "
        f"{len(rows)} 个班，合计 {total_gap:.1f}h；"
        f"首个缺口 {first['class_id']} 缺 {float(first['gap_hours']):.1f}h；"
        f"明细: {summary_path}"
    )


def build_bundle(output_dir: Path, bundle_dir: Path, skip_coverage_check: bool = False) -> Path:
    if not skip_coverage_check:
        validate_no_public_coverage_gaps(output_dir)
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    copy_required(output_dir / "batch_schedule_maintenance.html", bundle_dir / "schedule.html")
    # Cloudflare Pages redirects *.html asset subrequests to pretty URLs. The
    # Worker serves this internal copy as text/html to keep /schedule stable.
    copy_required(output_dir / "batch_schedule_maintenance.html", bundle_dir / "schedule_content.txt")
    copy_required(output_dir / "batch_schedule_maintenance.csv", bundle_dir / "schedule.csv")
    copy_required(output_dir / "batch_schedule_maintenance_report.md", bundle_dir / "report.md")
    copy_required(WORKER_SOURCE, bundle_dir / "_worker.js")
    (bundle_dir / "README.txt").write_text(
        "\n".join(
            [
                "27考研预排课表只读发布包",
                "",
                "入口: /schedule",
                "下载课表明细: /download/schedule.csv",
                "下载排课报告: /download/report.md",
                "健康检查: /healthz",
                "",
                "本目录由 scripts/build_cloudflare_publish_bundle.py 生成。",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return bundle_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 Cloudflare Pages 只读课表发布包")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--bundle-dir", type=Path, default=DEFAULT_BUNDLE_DIR)
    parser.add_argument("--skip-coverage-check", action="store_true", help="跳过课时覆盖门禁，仅用于人工排查")
    args = parser.parse_args()
    bundle_dir = build_bundle(args.output_dir.resolve(), args.bundle_dir.resolve(), args.skip_coverage_check)
    print(bundle_dir)


if __name__ == "__main__":
    main()
