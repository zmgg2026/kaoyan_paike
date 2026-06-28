from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple


def clean_cell(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def read_csv_with_fieldnames(path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), [dict(row) for row in reader]


def read_csv_text_with_fieldnames(text: str) -> Tuple[List[str], List[Dict[str, str]]]:
    handle = io.StringIO(text.lstrip("\ufeff"), newline="")
    reader = csv.DictReader(handle)
    return list(reader.fieldnames or []), [dict(row) for row in reader]


def write_csv_rows(
    path: Path,
    fieldnames: Sequence[str],
    rows: Iterable[dict],
    *,
    encoding: str = "utf-8-sig",
    extrasaction: str = "ignore",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding=encoding) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction=extrasaction)
        writer.writeheader()
        for row in rows:
            if extrasaction == "raise":
                writer.writerow(row)
            else:
                writer.writerow({field: row.get(field, "") for field in fieldnames})
