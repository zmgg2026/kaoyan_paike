#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urlencode
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import data_admin_server as admin  # noqa: E402


AMAP_ENDPOINT = "https://restapi.amap.com/v3/geocode/geo"


def city_for_area(area: Dict[str, Any]) -> str:
    text = " ".join(
        str(area.get(key) or "")
        for key in ("address", "name", "short_name", "campus")
    )
    if "芜湖" in text:
        return "芜湖"
    if "合肥" in text or "安徽" in text:
        return "合肥"
    return "合肥"


def geocode_address(key: str, address: str, city: str, timeout: int) -> Tuple[str, str, Dict[str, Any]]:
    params = urlencode({"key": key, "address": address, "city": city, "output": "JSON"})
    with urlopen(f"{AMAP_ENDPOINT}?{params}", timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("status") != "1":
        raise RuntimeError(f"{payload.get('info') or 'AMAP_ERROR'} ({payload.get('infocode') or 'unknown'})")
    geocodes = payload.get("geocodes") or []
    if not geocodes:
        raise RuntimeError("NO_GEOCODE_RESULT")
    location = geocodes[0].get("location") or ""
    if "," not in location:
        raise RuntimeError(f"INVALID_LOCATION: {location}")
    longitude, latitude = [part.strip() for part in location.split(",", 1)]
    return longitude, latitude, geocodes[0]


def load_areas() -> List[Dict[str, Any]]:
    doc = admin.read_json(admin.DATA_DIR / "teaching_areas.json", {"teaching_areas": []})
    return [admin.normalize_teaching_area(area) for area in doc.get("teaching_areas", [])]


def save_areas(areas: List[Dict[str, Any]]) -> None:
    admin.write_json(
        admin.DATA_DIR / "teaching_areas.json",
        {
            "updated_at": admin.today_text(),
            "source": "scripts/geocode_teaching_areas_amap.py",
            "record_count": len(areas),
            "teaching_areas": areas,
        },
    )
    admin.write_csv(admin.DATA_DIR / "teaching_areas.csv", areas, admin.TEACHING_AREA_FIELDNAMES)


def main() -> int:
    parser = argparse.ArgumentParser(description="用高德地理编码补齐教学区经纬度。")
    parser.add_argument("--overwrite", action="store_true", help="已存在经纬度时也重新查询并覆盖")
    parser.add_argument("--limit", type=int, default=0, help="最多查询多少条，默认不限制")
    parser.add_argument("--timeout", type=int, default=10, help="单次 API 请求超时时间，单位秒")
    parser.add_argument("--sleep", type=float, default=0.2, help="两次请求之间的间隔秒数")
    args = parser.parse_args()

    key = os.environ.get("AMAP_KEY") or os.environ.get("GAODE_KEY")
    if not key:
        print("缺少高德 API Key。请先设置环境变量 AMAP_KEY 或 GAODE_KEY。", file=sys.stderr)
        return 2

    areas = load_areas()
    updated = 0
    skipped = 0
    errors: List[str] = []

    for area in areas:
        address = admin.normalize_text(area.get("address"))
        if not address:
            skipped += 1
            continue
        if not args.overwrite and area.get("longitude") and area.get("latitude"):
            skipped += 1
            continue
        if args.limit and updated >= args.limit:
            skipped += 1
            continue
        try:
            city = city_for_area(area)
            longitude, latitude, result = geocode_address(key, address, city, args.timeout)
            area["longitude"] = longitude
            area["latitude"] = latitude
            formatted_address = admin.normalize_text(result.get("formatted_address"))
            if formatted_address and formatted_address != address:
                note = f"高德匹配地址：{formatted_address}"
                area["notes"] = "；".join([text for text in (admin.normalize_text(area.get("notes")), note) if text])
            updated += 1
            print(f"OK {area.get('id')} {area.get('short_name')}: {longitude},{latitude}")
            time.sleep(args.sleep)
        except Exception as exc:  # noqa: BLE001 - report row-level API/data issues and keep going.
            errors.append(f"{area.get('id')} {area.get('short_name')}: {exc}")

    if updated:
        save_areas(areas)

    print(f"完成：更新 {updated} 条，跳过 {skipped} 条，错误 {len(errors)} 条。")
    for error in errors:
        print(f"ERROR {error}", file=sys.stderr)
    return 1 if errors and not updated else 0


if __name__ == "__main__":
    raise SystemExit(main())
