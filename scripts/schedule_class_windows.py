from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Set

import scheduler
from scripts.csv_utils import read_csv_rows
from scripts.field_utils import parse_enabled, split_pipe_values
from scripts.period_utils import normalize_period as normalize_schedule_period
from scripts.schedule_data import load_room_metadata
from scripts.schedule_scope import normalize_date


@dataclass(frozen=True)
class ClassWindowConstraint:
    class_window_id: str
    class_id: str
    class_name: str
    product_id: str
    schedule_window_id: str
    season_window_id: str
    season_name: str
    schedule_window_name: str
    earliest_date: str
    earliest_period: str
    latest_date: str
    latest_period: str
    teaching_area_ids: frozenset[str]
    room_ids: frozenset[str]
    preferred_room_is_required: bool
    notes: str = ""

    @property
    def room_id(self) -> str:
        if len(self.room_ids) == 1:
            return next(iter(self.room_ids))
        return ""


def is_enabled(value: str) -> bool:
    return parse_enabled(value, default=True)


def class_window_matches(
    row: Dict[str, str],
    schedule_window_ids: Optional[Set[str]],
    season_window_ids: Optional[Set[str]],
) -> bool:
    if schedule_window_ids and (row.get("schedule_window_id") or "").strip() not in schedule_window_ids:
        return False
    if season_window_ids:
        season_tokens = {
            (row.get("season_window_id") or "").strip(),
            (row.get("season_name") or "").strip(),
            (row.get("schedule_window_name") or "").strip(),
        }
        if not (season_tokens & season_window_ids):
            return False
    return True


def room_ids_by_area_for_path(path: Path) -> Dict[str, frozenset[str]]:
    rooms = load_room_metadata(path.parent)
    result: Dict[str, Set[str]] = {}
    for room_id, room in rooms.items():
        if not is_enabled(room.get("is_active", "")):
            continue
        area_id = (room.get("teaching_area_id") or "").strip()
        if area_id:
            result.setdefault(area_id, set()).add(room_id)
    return {area_id: frozenset(room_ids) for area_id, room_ids in result.items()}


def expand_area_room_ids(
    teaching_area_ids: frozenset[str],
    room_ids_by_area: Mapping[str, frozenset[str]],
) -> frozenset[str]:
    room_ids: Set[str] = set()
    for area_id in teaching_area_ids:
        room_ids.update(room_ids_by_area.get(area_id, frozenset()))
    return frozenset(room_ids)


def row_to_constraint(
    row: Dict[str, str],
    room_ids_by_area: Optional[Mapping[str, frozenset[str]]] = None,
) -> ClassWindowConstraint:
    teaching_area_ids = frozenset(split_pipe_values(row.get("preferred_teaching_area_ids") or ""))
    room_ids = frozenset(split_pipe_values(row.get("preferred_room_ids") or ""))
    if not room_ids and teaching_area_ids and room_ids_by_area:
        room_ids = expand_area_room_ids(teaching_area_ids, room_ids_by_area)
    return ClassWindowConstraint(
        class_window_id=(row.get("class_window_id") or "").strip(),
        class_id=(row.get("class_id") or "").strip(),
        class_name=(row.get("class_name") or "").strip(),
        product_id=(row.get("product_id") or "").strip(),
        schedule_window_id=(row.get("schedule_window_id") or "").strip(),
        season_window_id=(row.get("season_window_id") or "").strip(),
        season_name=(row.get("season_name") or "").strip(),
        schedule_window_name=(row.get("schedule_window_name") or "").strip(),
        earliest_date=normalize_date(row.get("earliest_date") or ""),
        earliest_period=normalize_schedule_period(row.get("earliest_period") or "", "AM") or "",
        latest_date=normalize_date(row.get("latest_date") or ""),
        latest_period=normalize_schedule_period(row.get("latest_period") or "", "EVENING") or "",
        teaching_area_ids=teaching_area_ids,
        room_ids=room_ids,
        preferred_room_is_required=is_enabled(row.get("preferred_room_is_required") or ""),
        notes=(row.get("notes") or "").strip(),
    )


def merge_constraints(constraints: Iterable[ClassWindowConstraint]) -> ClassWindowConstraint:
    items = list(constraints)
    if not items:
        raise ValueError("merge_constraints 需要至少一条班级窗口记录")
    first = items[0]
    start = min(
        items,
        key=lambda constraint: (
            constraint.earliest_date or "9999-12-31",
            scheduler.period_sort_value(constraint.earliest_period or "AM"),
        ),
    )
    end = max(
        items,
        key=lambda constraint: (
            constraint.latest_date or "0001-01-01",
            scheduler.period_sort_value(constraint.latest_period or "EVENING"),
        ),
    )
    room_sets = {constraint.room_ids for constraint in items}
    room_ids = next(iter(room_sets)) if len(room_sets) == 1 else frozenset()
    area_sets = {constraint.teaching_area_ids for constraint in items}
    teaching_area_ids = next(iter(area_sets)) if len(area_sets) == 1 else frozenset()
    return ClassWindowConstraint(
        class_window_id="|".join(constraint.class_window_id for constraint in items if constraint.class_window_id),
        class_id=first.class_id,
        class_name=first.class_name,
        product_id=first.product_id,
        schedule_window_id="|".join(dict.fromkeys(constraint.schedule_window_id for constraint in items if constraint.schedule_window_id)),
        season_window_id="|".join(dict.fromkeys(constraint.season_window_id for constraint in items if constraint.season_window_id)),
        season_name="|".join(dict.fromkeys(constraint.season_name for constraint in items if constraint.season_name)),
        schedule_window_name="|".join(dict.fromkeys(constraint.schedule_window_name for constraint in items if constraint.schedule_window_name)),
        earliest_date=start.earliest_date,
        earliest_period=start.earliest_period,
        latest_date=end.latest_date,
        latest_period=end.latest_period,
        teaching_area_ids=teaching_area_ids,
        room_ids=room_ids,
        preferred_room_is_required=all(constraint.preferred_room_is_required for constraint in items),
        notes="；".join(constraint.notes for constraint in items if constraint.notes),
    )


def load_class_window_constraints(
    path: Path,
    class_ids: Optional[Set[str]] = None,
    schedule_window_ids: Optional[Set[str]] = None,
    season_window_ids: Optional[Set[str]] = None,
    included_only: bool = True,
    room_ids_by_area: Optional[Mapping[str, frozenset[str]]] = None,
) -> Dict[str, ClassWindowConstraint]:
    if not path.exists():
        return {}
    room_ids_by_area = room_ids_by_area if room_ids_by_area is not None else room_ids_by_area_for_path(path)
    by_class: Dict[str, List[ClassWindowConstraint]] = {}
    for row in read_csv_rows(path):
        class_id = (row.get("class_id") or "").strip()
        if not class_id or (class_ids and class_id not in class_ids):
            continue
        if included_only and not is_enabled(row.get("is_class_window_included") or ""):
            continue
        if not class_window_matches(row, schedule_window_ids, season_window_ids):
            continue
        by_class.setdefault(class_id, []).append(row_to_constraint(row, room_ids_by_area))
    return {
        class_id: merge_constraints(constraints)
        for class_id, constraints in by_class.items()
    }


def load_class_window_constraint_items(
    path: Path,
    class_ids: Optional[Set[str]] = None,
    schedule_window_ids: Optional[Set[str]] = None,
    season_window_ids: Optional[Set[str]] = None,
    included_only: bool = True,
    room_ids_by_area: Optional[Mapping[str, frozenset[str]]] = None,
) -> Dict[str, List[ClassWindowConstraint]]:
    if not path.exists():
        return {}
    room_ids_by_area = room_ids_by_area if room_ids_by_area is not None else room_ids_by_area_for_path(path)
    by_class: Dict[str, List[ClassWindowConstraint]] = {}
    for row in read_csv_rows(path):
        class_id = (row.get("class_id") or "").strip()
        if not class_id or (class_ids and class_id not in class_ids):
            continue
        if included_only and not is_enabled(row.get("is_class_window_included") or ""):
            continue
        if not class_window_matches(row, schedule_window_ids, season_window_ids):
            continue
        by_class.setdefault(class_id, []).append(row_to_constraint(row, room_ids_by_area))
    for constraints in by_class.values():
        constraints.sort(
            key=lambda constraint: (
                constraint.earliest_date or "9999-12-31",
                scheduler.period_sort_value(constraint.earliest_period or "AM"),
                constraint.latest_date or "9999-12-31",
            )
        )
    return by_class


def class_window_constraints_by_suite_code(
    class_constraints: Dict[str, ClassWindowConstraint],
    class_metadata: Dict[str, Dict[str, str]],
    suite_codes: Optional[Set[str]] = None,
) -> Dict[str, Dict[str, ClassWindowConstraint]]:
    by_suite: Dict[str, Dict[str, ClassWindowConstraint]] = {}
    for class_id, constraint in class_constraints.items():
        suite_code = (class_metadata.get(class_id, {}).get("suite_code") or "").strip()
        if not suite_code or (suite_codes and suite_code not in suite_codes):
            continue
        by_suite.setdefault(suite_code, {})[class_id] = constraint
    return by_suite


def suite_window_constraints_from_class_windows(
    class_constraints: Dict[str, ClassWindowConstraint],
    class_metadata: Dict[str, Dict[str, str]],
    suite_codes: Optional[Set[str]] = None,
) -> Dict[str, ClassWindowConstraint]:
    return {
        suite_code: merge_constraints(constraints.values())
        for suite_code, constraints in class_window_constraints_by_suite_code(
            class_constraints,
            class_metadata,
            suite_codes,
        ).items()
        if constraints
    }


def bounds_for_constraints(
    constraints: Iterable[ClassWindowConstraint],
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    items = list(constraints)
    if not items:
        return None, None, None, None
    start = min(
        items,
        key=lambda constraint: (
            constraint.earliest_date or "9999-12-31",
            scheduler.period_sort_value(constraint.earliest_period or "AM"),
        ),
    )
    end = max(
        items,
        key=lambda constraint: (
            constraint.latest_date or "0001-01-01",
            scheduler.period_sort_value(constraint.latest_period or "EVENING"),
        ),
    )
    return start.earliest_date, start.earliest_period, end.latest_date, end.latest_period


def season_names_for_constraints(constraints: Iterable[ClassWindowConstraint]) -> Set[str]:
    return {constraint.season_name for constraint in constraints if constraint.season_name}
