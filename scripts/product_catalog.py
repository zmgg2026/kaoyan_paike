from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, Optional

from scripts.field_utils import normalize_int, normalize_text, split_pipe_values


DEFAULT_STAGE_ORDER = ["导学", "基础", "强化", "冲刺", "一轮", "二轮", "三轮", "四轮"]
DEFAULT_STAGE_ORDER_INDEX = {stage: index for index, stage in enumerate(DEFAULT_STAGE_ORDER)}


def unique_list(values: Iterable[Any]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        text = normalize_text(value)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def label_text(*values: Any) -> str:
    return " ".join(normalize_text(value) for value in values if normalize_text(value))


def infer_project(product_name: str) -> str:
    if "考研" in product_name:
        return "考研"
    if "专升本" in product_name:
        return "专升本"
    return "四六级"


def infer_product_line(product_name: str, class_name: str = "", project: str = "") -> str:
    text = label_text(class_name, product_name)
    project_name = project or infer_project(product_name or class_name)
    if project_name != "考研":
        return project_name
    if "复试" in text:
        return "考研复试"
    if "无忧" in text:
        return "考研无忧"
    if "个性化" in text:
        return "考研个性化"
    if "营" in text or "集训" in text:
        return "考研集训营"
    return "考研其他"


def infer_sub_product(product_line: str, product_name: str, class_name: str = "") -> str:
    text = label_text(class_name, product_name)
    class_text = normalize_text(class_name)
    if product_line == "考研复试":
        return "考研复试小班" if "直通车" in class_text else "考研复试大班"
    if product_line == "考研无忧":
        for keyword, value in (
            ("无忧秋", "无忧秋"),
            ("无忧寒", "无忧寒"),
            ("无忧春", "无忧春"),
            ("无忧暑", "无忧暑"),
            ("秋", "无忧秋"),
            ("寒", "无忧寒"),
            ("春", "无忧春"),
            ("暑", "无忧暑"),
        ):
            if keyword in text:
                return value
        return "无忧"
    if product_line == "考研集训营":
        for keyword, value in (
            ("全年", "全年营"),
            ("半年", "半年营"),
            ("寒暑", "寒暑营"),
            ("暑假", "暑假营"),
            ("暑期", "暑假营"),
            ("冲刺", "冲刺营"),
        ):
            if keyword in text:
                return value
        return "集训营"
    if product_line == "考研个性化":
        return "考研个性化"
    if product_line == "考研其他":
        for keyword, value in (
            ("在职", "考研在职班"),
            ("呆滞", "考研呆滞班"),
            ("企业", "考研企培班"),
            ("合作", "考研企培班"),
            ("体验", "考研活动"),
            ("大咖", "考研大咖班"),
            ("专项", "考研专项班"),
        ):
            if keyword in text:
                return value
    return product_line or ""


def infer_capacity_type(standard_capacity: int) -> str:
    if standard_capacity <= 0:
        return ""
    return "VIP" if standard_capacity <= 2 else "班课"


def first_non_empty(values: Iterable[Any]) -> str:
    for value in values:
        text = normalize_text(value)
        if text:
            return text
    return ""


def unique_non_empty(values: Iterable[Any]) -> List[str]:
    return sorted({normalize_text(value) for value in values if normalize_text(value)})


def infer_unique_value(values: Iterable[Any]) -> str:
    unique_values = unique_non_empty(values)
    return unique_values[0] if len(unique_values) == 1 else ""


def stage_sort_key(value: Any) -> tuple[int, int, str]:
    text = normalize_text(value)
    match = re.match(r"^(导学)(\d+)$", text)
    base = match.group(1) if match else text
    rank = DEFAULT_STAGE_ORDER_INDEX.get(base, len(DEFAULT_STAGE_ORDER) + 1)
    sub_rank = int(match.group(2)) if match else 0
    return rank, sub_rank, text


def sort_stage_values(values: Iterable[Any]) -> List[str]:
    return sorted(unique_list(normalize_text(value) for value in values), key=stage_sort_key)


def stage_order_for_context(*values: Any) -> List[str]:
    stages = [
        normalize_text(value)
        for value in values
        if DEFAULT_STAGE_ORDER_INDEX.get(re.sub(r"\d+$", "", normalize_text(value)), None) is not None
    ]
    stages = sort_stage_values(stages)
    return stages if stages else list(DEFAULT_STAGE_ORDER)


def product_stage_order(product: Mapping[str, Any], cls: Optional[Mapping[str, Any]] = None) -> List[str]:
    cls = cls or {}
    stages = (
        split_pipe_values(cls.get("selected_stages"))
        or split_pipe_values(cls.get("stages"))
        or split_pipe_values(product.get("applicable_stages"))
    )
    return sort_stage_values(stages) if stages else list(DEFAULT_STAGE_ORDER)


def product_catalog(
    products: Iterable[Mapping[str, Any]],
    product_courses: Iterable[Mapping[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    catalog: Dict[str, Dict[str, Any]] = {}
    for product in products:
        product_id = normalize_text(product.get("id") or product.get("product_id"))
        if product_id:
            catalog[product_id] = dict(product)
    for course in product_courses:
        product_id = normalize_text(course.get("product_id"))
        if not product_id or product_id in catalog:
            continue
        product_name = normalize_text(course.get("product_name")) or product_id
        project = normalize_text(course.get("project")) or infer_project(product_name)
        product_line = infer_product_line(product_name, project=project)
        catalog[product_id] = {
            "id": product_id,
            "name": product_name,
            "project": project,
            "product_line": product_line,
            "sub_product": infer_sub_product(product_line, product_name),
            "product_system": "",
            "standard_capacity": 0,
            "capacity_type": "",
            "subject": "",
            "subject_category": "",
            "course_nature": "",
            "notes": "",
        }
    return catalog
