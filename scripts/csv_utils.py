from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

DEFAULT_ENCODINGS: Sequence[str] = ("utf-8-sig", "utf-8", "gb18030")


def serialize_csv_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, list):
        return "|".join(str(item) for item in value)
    return str(value)


def clean_cell(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def clean_csv_rows(rows: Iterable[Dict[str, object]]) -> List[Dict[str, str]]:
    result: List[Dict[str, str]] = []
    for row in rows:
        cleaned = {
            str(key).strip(): clean_cell(value)
            for key, value in row.items()
            if key is not None and str(key).strip()
        }
        if any(value for value in cleaned.values()):
            result.append(cleaned)
    return result


def read_csv_text(path: Path, encodings: Sequence[str] = DEFAULT_ENCODINGS) -> str:
    last_error: Optional[UnicodeDecodeError] = None
    for encoding in encodings:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    return path.read_text(encoding="utf-8-sig")


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    return read_csv_with_fieldnames(path)[1]


def read_csv_with_fieldnames(path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    return read_csv_text_with_fieldnames(read_csv_text(path))


def read_csv_text_with_fieldnames(text: str) -> Tuple[List[str], List[Dict[str, str]]]:
    handle = io.StringIO(text.lstrip("\ufeff"), newline="")
    reader = csv.DictReader(handle)
    return list(reader.fieldnames or []), [dict(row) for row in reader]


def csv_rows_text(
    fieldnames: Sequence[str],
    rows: Iterable[dict],
    *,
    bom: bool = False,
    extrasaction: str = "ignore",
    value_formatter: Optional[Callable[[object], object]] = None,
) -> str:
    handle = io.StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction=extrasaction)
    writer.writeheader()
    for row in rows:
        writer.writerow(format_csv_row(row, fieldnames, extrasaction, value_formatter))
    text = handle.getvalue()
    return f"\ufeff{text}" if bom else text


def format_csv_row(
    row: dict,
    fieldnames: Sequence[str],
    extrasaction: str,
    value_formatter: Optional[Callable[[object], object]],
) -> dict:
    if extrasaction == "raise":
        return {
            key: value_formatter(value) if value_formatter else value
            for key, value in row.items()
        }
    return {
        field: value_formatter(row.get(field, "")) if value_formatter else row.get(field, "")
        for field in fieldnames
    }


def write_csv_rows(
    path: Path,
    fieldnames: Sequence[str],
    rows: Iterable[dict],
    *,
    encoding: str = "utf-8-sig",
    extrasaction: str = "ignore",
    value_formatter: Optional[Callable[[object], object]] = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding=encoding) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction=extrasaction)
        writer.writeheader()
        for row in rows:
            writer.writerow(format_csv_row(row, fieldnames, extrasaction, value_formatter))
