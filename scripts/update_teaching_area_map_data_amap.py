#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urlencode
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import data_admin_server as admin  # noqa: E402


GEOCODE_ENDPOINT = "https://restapi.amap.com/v3/geocode/geo"
DISTANCE_ENDPOINT = "https://restapi.amap.com/v3/distance"
GENERATED_NOTE = "高德驾车自动生成"


def request_json(endpoint: str, params: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    query = urlencode(params)
    payload: Dict[str, Any] = {}
    for attempt in range(5):
        with urlopen(f"{endpoint}?{query}", timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("status") != "0" or payload.get("infocode") != "10021":
            return payload
        time.sleep(1.5 * (attempt + 1))
    return payload


def city_for_area(area: Dict[str, Any]) -> str:
    text = " ".join(str(area.get(key) or "") for key in ("address", "name", "short_name", "campus"))
    if "芜湖" in text:
        return "芜湖"
    return "合肥"


def geocode_area(key: str, area: Dict[str, Any], timeout: int) -> Tuple[str, str]:
    payload = request_json(
        GEOCODE_ENDPOINT,
        {
            "key": key,
            "address": area.get("address", ""),
            "city": city_for_area(area),
            "output": "JSON",
        },
        timeout,
    )
    if payload.get("status") != "1":
        raise RuntimeError(f"{payload.get('info') or 'AMAP_ERROR'} ({payload.get('infocode') or 'unknown'})")
    geocodes = payload.get("geocodes") or []
    if not geocodes:
        raise RuntimeError("NO_GEOCODE_RESULT")
    location = geocodes[0].get("location") or ""
    if "," not in location:
        raise RuntimeError(f"INVALID_LOCATION: {location}")
    longitude, latitude = [part.strip() for part in location.split(",", 1)]
    return longitude, latitude


def driving_distance(
    key: str,
    origin: Dict[str, Any],
    destination: Dict[str, Any],
    timeout: int,
) -> Tuple[float, int]:
    payload = request_json(
        DISTANCE_ENDPOINT,
        {
            "key": key,
            "origins": f"{origin['longitude']},{origin['latitude']}",
            "destination": f"{destination['longitude']},{destination['latitude']}",
            "type": "1",
            "output": "JSON",
        },
        timeout,
    )
    if payload.get("status") != "1":
        raise RuntimeError(f"{payload.get('info') or 'AMAP_ERROR'} ({payload.get('infocode') or 'unknown'})")
    results = payload.get("results") or []
    if not results:
        raise RuntimeError("NO_DISTANCE_RESULT")
    result = results[0]
    meters = float(result.get("distance") or 0)
    seconds = float(result.get("duration") or 0)
    return round(meters / 1000, 1), max(1, round(seconds / 60))


def relation_type_for_minutes(minutes: int) -> str:
    if minutes <= 30:
        return "可联排"
    return "不建议跨区"


def load_areas() -> List[Dict[str, Any]]:
    doc = admin.read_json(admin.DATA_DIR / "teaching_areas.json", {"teaching_areas": []})
    return [admin.normalize_teaching_area(area) for area in doc.get("teaching_areas", [])]


def save_areas(areas: List[Dict[str, Any]]) -> None:
    admin.write_json(
        admin.DATA_DIR / "teaching_areas.json",
        {
            "updated_at": admin.today_text(),
            "source": "scripts/update_teaching_area_map_data_amap.py",
            "record_count": len(areas),
            "teaching_areas": areas,
        },
    )
    admin.write_csv(admin.DATA_DIR / "teaching_areas.csv", areas, admin.TEACHING_AREA_FIELDNAMES)


def load_existing_links() -> List[Dict[str, Any]]:
    doc = admin.read_json(admin.DATA_DIR / "teaching_area_links.json", {"teaching_area_links": []})
    return [admin.normalize_area_link(link) for link in doc.get("teaching_area_links", doc.get("links", []))]


def save_links(links: List[Dict[str, Any]]) -> None:
    admin.write_json(
        admin.DATA_DIR / "teaching_area_links.json",
        {
            "updated_at": admin.today_text(),
            "source": "scripts/update_teaching_area_map_data_amap.py",
            "record_count": len(links),
            "teaching_area_links": links,
        },
    )
    admin.write_csv(admin.DATA_DIR / "teaching_area_links.csv", links, admin.TEACHING_AREA_LINK_FIELDNAMES)


def write_report(lines: List[str]) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = admin.OUTPUT_DIR / f"teaching_area_map_data_report_{timestamp}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="调用高德 API 补齐教学区经纬度，并生成校区间驾车距离/时长关系。")
    parser.add_argument("--overwrite-coordinates", action="store_true", help="已有经纬度时也重新查询覆盖")
    parser.add_argument("--replace-links", action="store_true", help="用本次高德结果替换全部教学区关联")
    parser.add_argument("--timeout", type=int, default=10, help="单次 API 请求超时时间，单位秒")
    parser.add_argument("--sleep", type=float, default=0.15, help="两次 API 请求之间的间隔秒数")
    args = parser.parse_args()

    key = os.environ.get("AMAP_KEY") or os.environ.get("GAODE_KEY")
    if not key:
        print("缺少高德 API Key。请先设置环境变量 AMAP_KEY 或 GAODE_KEY。", file=sys.stderr)
        return 2

    areas = load_areas()
    report = ["# 教学区地图数据更新报告", "", f"- 更新时间：{admin.today_text()}"]
    geocode_ok = 0
    geocode_errors: List[str] = []

    for area in areas:
        if not area.get("address"):
            continue
        if area.get("longitude") and area.get("latitude") and not args.overwrite_coordinates:
            continue
        try:
            longitude, latitude = geocode_area(key, area, args.timeout)
            area["longitude"] = longitude
            area["latitude"] = latitude
            geocode_ok += 1
            print(f"坐标 OK {area['id']} {area.get('short_name')}: {longitude},{latitude}")
            time.sleep(args.sleep)
        except Exception as exc:  # noqa: BLE001 - collect row-level external API failures.
            geocode_errors.append(f"{area.get('id')} {area.get('short_name')}: {exc}")

    save_areas(areas)

    candidates = [
        area
        for area in areas
        if area.get("address") and area.get("longitude") and area.get("latitude")
    ]
    generated_links: List[Dict[str, Any]] = []
    distance_errors: List[str] = []
    for origin, destination in combinations(candidates, 2):
        try:
            distance_km, minutes = driving_distance(key, origin, destination, args.timeout)
            link = admin.normalize_area_link(
                {
                    "id": f"{origin['id']}__{destination['id']}",
                    "from_teaching_area_id": origin["id"],
                    "to_teaching_area_id": destination["id"],
                    "relation_type": relation_type_for_minutes(minutes),
                    "driving_distance_km": distance_km,
                    "travel_minutes": minutes,
                    "notes": f"{GENERATED_NOTE}：{origin.get('short_name')} -> {destination.get('short_name')}，{distance_km}km，约{minutes}分钟",
                }
            )
            generated_links.append(link)
            print(f"距离 OK {origin.get('short_name')} -> {destination.get('short_name')}: {distance_km}km / {minutes}分钟")
            time.sleep(args.sleep)
        except Exception as exc:  # noqa: BLE001
            distance_errors.append(f"{origin.get('id')} -> {destination.get('id')}: {exc}")

    if args.replace_links:
        links = generated_links
    else:
        generated_ids = {link["id"] for link in generated_links}
        existing_links = [
            link
            for link in load_existing_links()
            if link.get("id") not in generated_ids and GENERATED_NOTE not in admin.normalize_text(link.get("notes"))
        ]
        links = existing_links + generated_links
    links.sort(key=lambda link: (link["from_teaching_area_id"], link["to_teaching_area_id"]))
    save_links(links)

    report.extend(
        [
            f"- 有地址教学区：{sum(1 for area in areas if area.get('address'))}",
            f"- 有经纬度教学区：{len(candidates)}",
            f"- 本次补坐标：{geocode_ok}",
            f"- 生成/更新驾车关系：{len(generated_links)}",
            f"- 坐标错误：{len(geocode_errors)}",
            f"- 距离错误：{len(distance_errors)}",
            "",
            "## 驾车关系",
            "",
            "| 教学区A | 教学区B | 距离km | 时长分钟 | 关系 |",
            "|---|---:|---:|---:|---|",
        ]
    )
    area_name = {area["id"]: area.get("short_name") or area.get("name") or area["id"] for area in areas}
    for link in generated_links:
        report.append(
            f"| {area_name.get(link['from_teaching_area_id'], link['from_teaching_area_id'])} | "
            f"{area_name.get(link['to_teaching_area_id'], link['to_teaching_area_id'])} | "
            f"{link.get('driving_distance_km')} | {link.get('travel_minutes')} | {link.get('relation_type')} |"
        )
    if geocode_errors:
        report.extend(["", "## 坐标错误", ""] + [f"- {item}" for item in geocode_errors])
    if distance_errors:
        report.extend(["", "## 距离错误", ""] + [f"- {item}" for item in distance_errors])
    report_path = write_report(report)
    print(f"报告: {report_path}")

    return 1 if geocode_errors or distance_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
