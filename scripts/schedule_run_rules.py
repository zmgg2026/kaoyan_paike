from __future__ import annotations

from datetime import date as Date, timedelta
from typing import Iterable, List, Set, Tuple


def parsed_dates(values: Iterable[str]) -> Set[Date]:
    return {Date.fromisoformat(date_text) for date_text in values}


def creates_teacher_run_over_limit(
    existing_dates: Set[str],
    new_date: str,
    max_consecutive_days: int,
) -> bool:
    dates = parsed_dates(existing_dates)
    current = Date.fromisoformat(new_date)
    dates.add(current)
    run_length = max_consecutive_days + 1
    for delta in range(-max_consecutive_days, 1):
        start = current + timedelta(days=delta)
        if all(start + timedelta(days=offset) in dates for offset in range(run_length)):
            return True
    return False


def creates_three_day_teacher_run(
    existing_dates: Set[str],
    new_date: str,
) -> bool:
    return creates_teacher_run_over_limit(existing_dates, new_date, 2)


def creates_adjacent_subject_day(existing_dates: Set[str], new_date: str) -> bool:
    if not existing_dates:
        return False
    current = Date.fromisoformat(new_date)
    dates = parsed_dates(existing_dates)
    return current - timedelta(days=1) in dates or current + timedelta(days=1) in dates


def run_dates(dates: Iterable[str]) -> List[Tuple[str, str, str]]:
    return [
        (run[0], run[1], run[2])
        for run in run_dates_over_limit(dates, 2)
    ]


def run_dates_over_limit(dates: Iterable[str], max_consecutive_days: int) -> List[Tuple[str, ...]]:
    parsed = sorted(parsed_dates(dates))
    parsed_set = set(parsed)
    run_length = max_consecutive_days + 1
    runs: List[Tuple[str, ...]] = []
    for start in parsed:
        run = tuple((start + timedelta(days=offset)).isoformat() for offset in range(run_length))
        if all(Date.fromisoformat(date_text) in parsed_set for date_text in run):
            runs.append(run)
    return runs
