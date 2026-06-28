#!/usr/bin/env python3
from __future__ import annotations

from datetime import date as Date
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import scheduler


SubjectWeekBounds = Dict[str, Tuple[Optional[int], Optional[int]]]
SUBJECT_ORDER = {"数学": 0, "英语": 1, "政治": 2, "语文": 3}


def slot_block_key(slot_block: Tuple[scheduler.TimeSlot, ...]) -> Tuple[str, int, int, str]:
    return scheduler.slot_sort_key(slot_block[0])


def week_key(slot_block: Tuple[scheduler.TimeSlot, ...]) -> Tuple[int, int]:
    year, week, _ = Date.fromisoformat(slot_block[0].date).isocalendar()
    return year, week


def balanced_week_quotas(
    slot_blocks: Sequence[Tuple[scheduler.TimeSlot, ...]],
    task_count: int,
) -> Dict[Tuple[int, int], int]:
    weeks: Dict[Tuple[int, int], int] = {}
    for slot_block in slot_blocks:
        key = week_key(slot_block)
        weeks[key] = weeks.get(key, 0) + 1
    if not weeks or task_count <= 0:
        return {}

    total_capacity = sum(weeks.values())
    capped_capacity = {
        key: max(1, capacity - 2) if capacity >= 6 else capacity
        for key, capacity in weeks.items()
    }
    raw = {
        key: task_count * capacity / total_capacity
        for key, capacity in capped_capacity.items()
    }
    quotas = {key: min(capped_capacity[key], int(raw[key])) for key in weeks}
    remaining = task_count - sum(quotas.values())

    order = sorted(
        weeks,
        key=lambda key: (raw[key] - int(raw[key]), capped_capacity[key] - quotas[key], key),
        reverse=True,
    )
    while remaining > 0 and order:
        progressed = False
        for key in order:
            if remaining <= 0:
                break
            if quotas[key] >= capped_capacity[key]:
                continue
            quotas[key] += 1
            remaining -= 1
            progressed = True
        if not progressed:
            break

    if remaining > 0:
        overflow_order = sorted(weeks, key=lambda key: (weeks[key] - quotas[key], key), reverse=True)
        while remaining > 0:
            for key in overflow_order:
                if remaining <= 0:
                    break
                if quotas[key] >= weeks[key]:
                    continue
                quotas[key] += 1
                remaining -= 1

    return quotas


def front_loaded_week_quotas(
    slot_blocks: Sequence[Tuple[scheduler.TimeSlot, ...]],
    task_count: int,
) -> Dict[Tuple[int, int], int]:
    weeks: Dict[Tuple[int, int], int] = {}
    for slot_block in slot_blocks:
        key = week_key(slot_block)
        weeks[key] = weeks.get(key, 0) + 1
    if not weeks or task_count <= 0:
        return {}

    ordered_weeks = sorted(weeks)
    capped_capacity = {
        key: max(1, capacity - 2) if capacity >= 6 else capacity
        for key, capacity in weeks.items()
    }
    quotas = {key: 0 for key in ordered_weeks}

    def fill_layer(capacities: Dict[Tuple[int, int], int], remaining: int) -> int:
        while remaining > 0:
            available = [key for key in ordered_weeks if quotas[key] < capacities[key]]
            if not available:
                break
            min_quota = min(quotas[key] for key in available)
            progressed = False
            for key in ordered_weeks:
                if remaining <= 0:
                    break
                if quotas[key] >= capacities[key] or quotas[key] != min_quota:
                    continue
                quotas[key] += 1
                remaining -= 1
                progressed = True
            if not progressed:
                break
        return remaining

    remaining = fill_layer(capped_capacity, task_count)
    if remaining > 0:
        fill_layer(weeks, remaining)
    return quotas


def evenly_spaced_week_subset(
    weeks: Sequence[Tuple[int, int]],
    count: int,
) -> List[Tuple[int, int]]:
    if count <= 0:
        return []
    if count >= len(weeks):
        return list(weeks)
    if count == 1:
        return [weeks[len(weeks) // 2]]
    indexes = {
        round(index * (len(weeks) - 1) / (count - 1))
        for index in range(count)
    }
    result = [weeks[index] for index in sorted(indexes)]
    cursor = 0
    while len(result) < count and cursor < len(weeks):
        candidate = weeks[cursor]
        if candidate not in result:
            result.append(candidate)
        cursor += 1
    return sorted(result)


def balanced_capped_week_quotas(
    slot_blocks: Sequence[Tuple[scheduler.TimeSlot, ...]],
    task_count: int,
    weekly_limit: Optional[int],
    weekly_min: Optional[int] = None,
) -> Dict[Tuple[int, int], int]:
    capacities: Dict[Tuple[int, int], int] = {}
    for slot_block in slot_blocks:
        key = week_key(slot_block)
        capacities[key] = capacities.get(key, 0) + 1
    if not capacities or task_count <= 0:
        return {}

    if weekly_limit:
        capacities = {key: min(capacity, weekly_limit) for key, capacity in capacities.items()}
    if sum(capacities.values()) < task_count:
        raise ValueError(f"周半天容量不足，需要 {task_count} 个半天，仅有 {sum(capacities.values())} 个")
    if weekly_min:
        if weekly_limit and weekly_min > weekly_limit:
            raise ValueError(f"周半天下限 {weekly_min} 不能大于周上限 {weekly_limit}")
        eligible_weeks = [key for key in sorted(capacities) if capacities[key] >= weekly_min]
        active_weeks: List[Tuple[int, int]] = []
        for active_count in range(min(len(eligible_weeks), task_count // weekly_min), 0, -1):
            candidate_weeks = (
                eligible_weeks
                if active_count == len(eligible_weeks)
                else evenly_spaced_week_subset(eligible_weeks, active_count)
            )
            if sum(capacities[key] for key in candidate_weeks) >= task_count:
                active_weeks = candidate_weeks
                break
        if not active_weeks:
            raise ValueError(f"周半天下限不足，需要每周至少 {weekly_min} 个半天，共 {task_count} 个半天")

        quotas = {key: 0 for key in sorted(capacities)}
        for key in active_weeks:
            quotas[key] = weekly_min
        remaining = task_count - weekly_min * len(active_weeks)
        while remaining > 0:
            available = [key for key in active_weeks if quotas[key] < capacities[key]]
            if not available:
                break
            min_quota = min(quotas[key] for key in available)
            progressed = False
            for key in available:
                if remaining <= 0:
                    break
                if quotas[key] != min_quota:
                    continue
                quotas[key] += 1
                remaining -= 1
                progressed = True
            if not progressed:
                break
        if remaining > 0:
            raise ValueError(f"周半天容量不足，需要 {task_count} 个半天，仅有 {task_count - remaining} 个")
        return quotas

    quotas = {key: 0 for key in sorted(capacities)}
    remaining = task_count
    while remaining > 0:
        available = [key for key in sorted(capacities) if quotas[key] < capacities[key]]
        if not available:
            break
        min_quota = min(quotas[key] for key in available)
        progressed = False
        for key in available:
            if remaining <= 0:
                break
            if quotas[key] != min_quota:
                continue
            quotas[key] += 1
            remaining -= 1
            progressed = True
        if not progressed:
            break
    return quotas


def bounded_week_quotas(
    slot_blocks: Sequence[Tuple[scheduler.TimeSlot, ...]],
    task_count: int,
    weekly_min: Optional[int],
    weekly_max: Optional[int],
) -> Dict[Tuple[int, int], int]:
    capacities: Dict[Tuple[int, int], int] = {}
    for slot_block in slot_blocks:
        key = week_key(slot_block)
        capacities[key] = capacities.get(key, 0) + 1
    if not capacities or task_count <= 0:
        return {}

    capped_capacities = {
        key: min(capacity, weekly_max) if weekly_max else capacity
        for key, capacity in capacities.items()
    }
    if sum(capped_capacities.values()) < task_count:
        raise ValueError(f"周半天上限容量不足，需要 {task_count} 个半天，仅有 {sum(capped_capacities.values())} 个")

    ordered_weeks = sorted(capped_capacities)
    if not weekly_min:
        quotas = {key: 0 for key in ordered_weeks}
        remaining = task_count
        while remaining > 0:
            available = [key for key in ordered_weeks if quotas[key] < capped_capacities[key]]
            if not available:
                break
            min_quota = min(quotas[key] for key in available)
            progressed = False
            for key in available:
                if remaining <= 0:
                    break
                if quotas[key] != min_quota:
                    continue
                quotas[key] += 1
                remaining -= 1
                progressed = True
            if not progressed:
                break
        if remaining > 0:
            raise ValueError(f"周半天容量不足，需要 {task_count} 个半天，仅有 {task_count - remaining} 个")
        return quotas

    if weekly_max and weekly_min > weekly_max:
        raise ValueError(f"周半天下限 {weekly_min} 不能大于周上限 {weekly_max}")

    eligible_weeks = [key for key in ordered_weeks if capped_capacities[key] >= weekly_min]
    active_weeks: List[Tuple[int, int]] = []
    for active_count in range(min(len(eligible_weeks), task_count // weekly_min), 0, -1):
        candidate_weeks = (
            eligible_weeks
            if active_count == len(eligible_weeks)
            else evenly_spaced_week_subset(eligible_weeks, active_count)
        )
        if sum(capped_capacities[key] for key in candidate_weeks) >= task_count:
            active_weeks = candidate_weeks
            break
    if not active_weeks:
        if task_count <= max(capped_capacities.values()):
            active_weeks = [next(key for key in ordered_weeks if capped_capacities[key] >= task_count)]
        else:
            raise ValueError(f"周半天下限不足，需要每周至少 {weekly_min} 个半天，共 {task_count} 个半天")

    quotas = {key: 0 for key in ordered_weeks}
    if task_count < weekly_min:
        quotas[active_weeks[0]] = task_count
        return quotas

    for key in active_weeks:
        quotas[key] = weekly_min
    remaining = task_count - weekly_min * len(active_weeks)
    while remaining > 0:
        available = [key for key in active_weeks if quotas[key] < capped_capacities[key]]
        if not available:
            break
        min_quota = min(quotas[key] for key in available)
        progressed = False
        for key in available:
            if remaining <= 0:
                break
            if quotas[key] != min_quota:
                continue
            quotas[key] += 1
            remaining -= 1
            progressed = True
        if not progressed:
            break
    if remaining > 0:
        raise ValueError(f"周半天容量不足，需要 {task_count} 个半天，仅有 {task_count - remaining} 个")
    return quotas


def summer_camp_subject_week_bounds(subjects: Set[str]) -> SubjectWeekBounds:
    if "数学" in subjects:
        return {
            "数学": (4, 5),
            "政治": (3, 4),
            "英语": (3, 4),
        }
    return {
        "政治": (5, 6),
        "英语": (4, 6),
    }


def long_camp_subject_week_bounds(subjects: Set[str]) -> SubjectWeekBounds:
    configured: SubjectWeekBounds = {
        # 全年营/半年营按剩余未排课量在可排周内平均铺开；
        # 只要课量足够，每个公共课科目每个可排周至少保留 1 个半天。
        "数学": (1, 4),
        "政治": (1, 3),
        "英语": (1, 4),
    }
    return {
        subject: configured[subject]
        for subject in subjects
        if subject in configured
    }


def effective_week_count_for_slot_blocks(
    slot_blocks: Sequence[Tuple[scheduler.TimeSlot, ...]],
) -> int:
    if not slot_blocks:
        return 0
    weeks = sorted({week_key(slot_block) for slot_block in slot_blocks})
    dates = [Date.fromisoformat(slot_block[0].date) for slot_block in slot_blocks]
    span_days = (max(dates) - min(dates)).days + 1
    rounded_weeks = max(1, round(span_days / 7))
    return max(1, min(len(weeks), rounded_weeks))


def average_subject_week_bounds_from_counts(
    subject_slot_blocks: Dict[str, List[Tuple[scheduler.TimeSlot, ...]]],
    subject_counts: Dict[str, int],
    hard_weekly_max: Optional[Dict[str, int]] = None,
) -> SubjectWeekBounds:
    bounds: SubjectWeekBounds = {}
    for subject, count in subject_counts.items():
        if count <= 0:
            continue
        effective_weeks = effective_week_count_for_slot_blocks(subject_slot_blocks.get(subject, []))
        if effective_weeks <= 0:
            continue
        weekly_min = count // effective_weeks if count >= effective_weeks else None
        weekly_max = (count + effective_weeks - 1) // effective_weeks
        if hard_weekly_max and hard_weekly_max.get(subject):
            weekly_max = min(weekly_max, hard_weekly_max[subject])
            if weekly_min is not None:
                weekly_min = min(weekly_min, weekly_max)
        bounds[subject] = (
            weekly_min if weekly_min and weekly_min > 0 else None,
            max(1, weekly_max),
        )
    return bounds


def long_camp_subject_week_hard_max(subjects: Set[str]) -> Dict[str, int]:
    configured = {
        "数学": 4,
        "政治": 3,
        "英语": 4,
    }
    return {
        subject: configured[subject]
        for subject in subjects
        if subject in configured
    }


def sum_subject_week_quotas(
    subject_week_quotas: Dict[str, Dict[Tuple[int, int], int]],
    fallback_weeks: Iterable[Tuple[int, int]],
) -> Dict[Tuple[int, int], int]:
    weeks = set(fallback_weeks)
    for quotas in subject_week_quotas.values():
        weeks.update(quotas)
    return {
        key: sum(quotas.get(key, 0) for quotas in subject_week_quotas.values())
        for key in sorted(weeks)
    }


def max_only_subject_week_limits(
    subject_slot_blocks: Dict[str, List[Tuple[scheduler.TimeSlot, ...]]],
    subject_week_bounds: Optional[SubjectWeekBounds],
) -> Dict[str, Dict[Tuple[int, int], int]]:
    if not subject_week_bounds:
        return {}
    limits: Dict[str, Dict[Tuple[int, int], int]] = {}
    for subject, (_weekly_min, weekly_max) in subject_week_bounds.items():
        if not weekly_max:
            continue
        capacities: Dict[Tuple[int, int], int] = {}
        for slot_block in subject_slot_blocks.get(subject, []):
            key = week_key(slot_block)
            capacities[key] = capacities.get(key, 0) + 1
        limits[subject] = {
            key: min(capacity, weekly_max)
            for key, capacity in capacities.items()
        }
    return limits


def bounded_subject_week_quotas(
    slot_blocks: Sequence[Tuple[scheduler.TimeSlot, ...]],
    subject_slot_blocks: Dict[str, List[Tuple[scheduler.TimeSlot, ...]]],
    subject_counts: Dict[str, int],
    subject_week_bounds: SubjectWeekBounds,
    preferred_weekly_total_max: Optional[int] = None,
    require_all_weeks: bool = False,
) -> Dict[str, Dict[Tuple[int, int], int]]:
    total_capacities: Dict[Tuple[int, int], int] = {}
    for slot_block in slot_blocks:
        key = week_key(slot_block)
        total_capacities[key] = total_capacities.get(key, 0) + 1
    if preferred_weekly_total_max:
        preferred_total_capacities = {
            key: min(capacity, preferred_weekly_total_max)
            for key, capacity in total_capacities.items()
        }
        if sum(preferred_total_capacities.values()) >= sum(subject_counts.values()):
            total_capacities = preferred_total_capacities

    required_min_weeks: Set[Tuple[int, int]] = set()
    if require_all_weeks:
        weekly_min_total = sum(
            weekly_min
            for subject, (weekly_min, _weekly_max) in subject_week_bounds.items()
            if subject in subject_counts and weekly_min
        )
        if weekly_min_total:
            required_min_weeks = {
                key
                for key, capacity in total_capacities.items()
                if capacity >= weekly_min_total
            }

    if (
        preferred_weekly_total_max
        and not require_all_weeks
        and set(subject_counts) == {"英语", "政治"}
        and {"英语", "政治"}.issubset(subject_week_bounds)
    ):
        special_quotas: Dict[str, Dict[Tuple[int, int], int]] = {}
        weeks = sorted(total_capacities)
        can_use_special = True
        for subject in ("英语", "政治"):
            weekly_min, weekly_max = subject_week_bounds[subject]
            if weekly_min is None or weekly_max is None:
                can_use_special = False
                break
            capacities: Dict[Tuple[int, int], int] = {}
            for slot_block in subject_slot_blocks.get(subject, []):
                key = week_key(slot_block)
                capacities[key] = capacities.get(key, 0) + 1
            capacities = {key: min(capacities.get(key, 0), weekly_max) for key in weeks}
            if subject_counts[subject] < weekly_min * len(weeks):
                can_use_special = False
                break
            if sum(capacities.values()) < subject_counts[subject]:
                can_use_special = False
                break
            special_quotas[subject] = {key: weekly_min for key in weeks}

        if can_use_special:
            remaining_by_subject = {
                subject: subject_counts[subject] - sum(special_quotas[subject].values())
                for subject in special_quotas
            }
            subject_week_order = {
                "英语": weeks,
                "政治": list(reversed(weeks)),
            }
            for subject in ("英语", "政治"):
                weekly_max = subject_week_bounds[subject][1] or 999
                while remaining_by_subject[subject] > 0:
                    progressed = False
                    for key in subject_week_order[subject]:
                        if remaining_by_subject[subject] <= 0:
                            break
                        if special_quotas[subject].get(key, 0) >= weekly_max:
                            continue
                        if sum(quotas.get(key, 0) for quotas in special_quotas.values()) >= total_capacities.get(key, 0):
                            continue
                        special_quotas[subject][key] = special_quotas[subject].get(key, 0) + 1
                        remaining_by_subject[subject] -= 1
                        progressed = True
                    if not progressed:
                        can_use_special = False
                        break
                if not can_use_special:
                    break
            if can_use_special:
                return special_quotas

    quotas: Dict[str, Dict[Tuple[int, int], int]] = {
        subject: {key: 0 for key in sorted(total_capacities)}
        for subject in subject_counts
    }
    subject_capacities: Dict[str, Dict[Tuple[int, int], int]] = {}
    active_weeks_by_subject: Dict[str, List[Tuple[int, int]]] = {}
    remaining_by_subject: Dict[str, int] = {}

    for subject, count in subject_counts.items():
        if subject not in subject_week_bounds:
            quotas[subject] = balanced_week_quotas(subject_slot_blocks.get(subject, []), count)
            continue
        weekly_min, weekly_max = subject_week_bounds[subject]
        capacities: Dict[Tuple[int, int], int] = {}
        for slot_block in subject_slot_blocks.get(subject, []):
            key = week_key(slot_block)
            capacities[key] = capacities.get(key, 0) + 1
        if weekly_max:
            capacities = {key: min(capacity, weekly_max) for key, capacity in capacities.items()}
        if sum(capacities.values()) < count:
            raise ValueError(f"{subject} 周半天上限容量不足，需要 {count} 个半天，仅有 {sum(capacities.values())} 个")
        subject_capacities[subject] = capacities
        if not weekly_min:
            active_weeks = [key for key in sorted(capacities) if capacities[key] > 0]
            active_weeks_by_subject[subject] = active_weeks
            remaining_by_subject[subject] = count
            continue

        eligible_weeks = [key for key in sorted(capacities) if capacities[key] >= weekly_min]
        if require_all_weeks and required_min_weeks:
            required_weeks = [
                key
                for key in sorted(required_min_weeks)
                if capacities.get(key, 0) >= weekly_min
            ]
            if count >= weekly_min * len(required_weeks) and sum(capacities[key] for key in eligible_weeks) >= count:
                active_weeks = eligible_weeks
                min_weeks = required_weeks
            else:
                active_weeks = []
                for active_count in range(min(len(eligible_weeks), count // weekly_min), 0, -1):
                    candidate_weeks = evenly_spaced_week_subset(eligible_weeks, active_count)
                    if sum(capacities[key] for key in candidate_weeks) >= count:
                        active_weeks = candidate_weeks
                        break
                min_weeks = active_weeks
        else:
            active_weeks = []
            for active_count in range(min(len(eligible_weeks), count // weekly_min), 0, -1):
                candidate_weeks = evenly_spaced_week_subset(eligible_weeks, active_count)
                if sum(capacities[key] for key in candidate_weeks) >= count:
                    active_weeks = candidate_weeks
                    break
            min_weeks = active_weeks
        if not active_weeks:
            raise ValueError(f"{subject} 周半天下限不足，需要每周至少 {weekly_min} 个半天，共 {count} 个半天")
        for key in min_weeks:
            quotas[subject][key] = weekly_min
        active_weeks_by_subject[subject] = active_weeks
        remaining_by_subject[subject] = count - weekly_min * len(min_weeks)

    def total_quota_for_week(key: Tuple[int, int]) -> int:
        return sum(subject_quotas.get(key, 0) for subject_quotas in quotas.values())

    for key in sorted(total_capacities):
        while total_quota_for_week(key) > total_capacities[key]:
            reducible_subjects = [
                subject
                for subject in quotas
                if quotas[subject].get(key, 0) > 0
            ]
            if not reducible_subjects:
                raise ValueError(f"周半天总容量不足，{key} 需要 {total_quota_for_week(key)} 个半天，仅有 {total_capacities[key]} 个")
            subject = max(
                reducible_subjects,
                key=lambda item: (
                    quotas[item].get(key, 0),
                    SUBJECT_ORDER.get(item, 99),
                    item,
                ),
            )
            quotas[subject][key] = quotas[subject].get(key, 0) - 1
            remaining_by_subject[subject] = remaining_by_subject.get(subject, 0) + 1

    while any(remaining > 0 for remaining in remaining_by_subject.values()):
        progressed = False
        for subject in sorted(remaining_by_subject, key=lambda item: (-remaining_by_subject[item], SUBJECT_ORDER.get(item, 99), item)):
            if remaining_by_subject[subject] <= 0:
                continue
            capacities = subject_capacities.get(subject, {})
            candidate_weeks = [
                key
                for key in active_weeks_by_subject.get(subject, [])
                if quotas[subject].get(key, 0) < capacities.get(key, 0)
                and total_quota_for_week(key) < total_capacities.get(key, 0)
            ]
            if not candidate_weeks:
                continue
            candidate_weeks.sort(
                key=lambda key: (
                    total_quota_for_week(key),
                    quotas[subject].get(key, 0),
                    key,
                )
            )
            key = candidate_weeks[0]
            quotas[subject][key] = quotas[subject].get(key, 0) + 1
            remaining_by_subject[subject] -= 1
            progressed = True
        if not progressed:
            remaining = sum(remaining_by_subject.values())
            raise ValueError(f"周半天容量不足，仍有 {remaining} 个半天无法分配")
    return quotas


def shift_tail_week_quota_to_early(
    quotas: Dict[Tuple[int, int], int],
    slot_blocks: Sequence[Tuple[scheduler.TimeSlot, ...]],
    tail_week: Tuple[int, int],
    amount: int,
) -> None:
    capacities: Dict[Tuple[int, int], int] = {}
    for slot_block in slot_blocks:
        key = week_key(slot_block)
        capacities[key] = capacities.get(key, 0) + 1
    capped_capacity = {
        key: max(1, capacity - 2) if capacity >= 6 else capacity
        for key, capacity in capacities.items()
    }

    for _ in range(amount):
        candidate_weeks = [
            key
            for key in sorted(capacities)
            if key != tail_week and quotas.get(key, 0) < capped_capacity[key]
        ]
        if not candidate_weeks:
            candidate_weeks = [
                key
                for key in sorted(capacities)
                if key != tail_week and quotas.get(key, 0) < capacities[key]
            ]
        if not candidate_weeks:
            quotas[tail_week] = quotas.get(tail_week, 0) + 1
            continue

        min_quota = min(quotas.get(key, 0) for key in candidate_weeks)
        for key in candidate_weeks:
            if quotas.get(key, 0) == min_quota:
                quotas[key] = quotas.get(key, 0) + 1
                break


def subject_target_indices(
    slot_blocks: Sequence[Tuple[scheduler.TimeSlot, ...]],
    block_index: Dict[Tuple[str, ...], int],
    quotas: Dict[Tuple[int, int], int],
    count: int,
) -> List[float]:
    targets: List[float] = []
    by_week: Dict[Tuple[int, int], List[Tuple[scheduler.TimeSlot, ...]]] = {}
    for slot_block in slot_blocks:
        by_week.setdefault(week_key(slot_block), []).append(slot_block)

    for key in sorted(quotas):
        week_blocks = by_week.get(key, [])
        if not week_blocks:
            continue
        quota = min(quotas[key], len(week_blocks))
        for index in range(quota):
            position = round((index + 1) * (len(week_blocks) + 1) / (quota + 1)) - 1
            position = max(0, min(len(week_blocks) - 1, position))
            slot_ids = tuple(slot.id for slot in week_blocks[position])
            targets.append(float(block_index.get(slot_ids, len(block_index))))

    if len(targets) < count:
        span = max(len(slot_blocks) - 1, 1)
        missing = count - len(targets)
        for index in range(missing):
            targets.append((index + 1) * span / (missing + 1))
    return targets[:count]
