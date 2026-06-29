#!/usr/bin/env python3
from __future__ import annotations

import html
import re
from pathlib import Path

try:
    from PIL import Image as PILImage
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase.pdfmetrics import registerFont
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        Image,
        ListFlowable,
        ListItem,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )
except ImportError as exc:
    raise SystemExit(
        "生成 PDF 需要安装文档依赖: python3 -m pip install reportlab pillow"
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "docs" / "ai-assisted-scheduling-system-user-guide.md"
OUT_DIR = ROOT / "docs" / "generated"
PDF_PATH = OUT_DIR / "AI辅助排课系统使用攻略.pdf"

FONT_NAME = "GuideChinese"
FONT_PATHS = [
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    Path("/System/Library/Fonts/STHeiti Medium.ttc"),
    Path("/System/Library/Fonts/PingFang.ttc"),
]
PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 18 * mm
CONTENT_WIDTH = PAGE_WIDTH - MARGIN * 2


def register_fonts() -> None:
    for font_path in FONT_PATHS:
        if font_path.exists():
            registerFont(TTFont(FONT_NAME, str(font_path)))
            return
    raise FileNotFoundError("未找到可嵌入 PDF 的中文字体")


def make_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "GuideTitle",
            parent=base["Title"],
            fontName=FONT_NAME,
            fontSize=22,
            leading=30,
            textColor=colors.HexColor("#1F3A5F"),
            alignment=TA_CENTER,
            spaceAfter=14,
        ),
        "h1": ParagraphStyle(
            "GuideHeading1",
            parent=base["Heading1"],
            fontName=FONT_NAME,
            fontSize=15,
            leading=21,
            textColor=colors.HexColor("#2E5E8C"),
            spaceBefore=14,
            spaceAfter=8,
            keepWithNext=True,
        ),
        "h2": ParagraphStyle(
            "GuideHeading2",
            parent=base["Heading2"],
            fontName=FONT_NAME,
            fontSize=12.5,
            leading=18,
            textColor=colors.HexColor("#244B68"),
            spaceBefore=10,
            spaceAfter=5,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "GuideBody",
            parent=base["BodyText"],
            fontName=FONT_NAME,
            fontSize=9.7,
            leading=15,
            textColor=colors.HexColor("#263238"),
            alignment=TA_LEFT,
            wordWrap="CJK",
            spaceAfter=5,
        ),
        "small": ParagraphStyle(
            "GuideSmall",
            parent=base["BodyText"],
            fontName=FONT_NAME,
            fontSize=8.2,
            leading=12,
            textColor=colors.HexColor("#263238"),
            wordWrap="CJK",
        ),
        "code": ParagraphStyle(
            "GuideCode",
            parent=base["BodyText"],
            fontName=FONT_NAME,
            fontSize=8.2,
            leading=12,
            textColor=colors.HexColor("#263238"),
            backColor=colors.HexColor("#F5F7FA"),
            borderColor=colors.HexColor("#D9E2EA"),
            borderWidth=0.4,
            borderPadding=5,
            wordWrap="CJK",
            spaceBefore=3,
            spaceAfter=7,
        ),
        "caption": ParagraphStyle(
            "GuideCaption",
            parent=base["BodyText"],
            fontName=FONT_NAME,
            fontSize=8.2,
            leading=12,
            textColor=colors.HexColor("#60717D"),
            alignment=TA_CENTER,
            spaceAfter=8,
        ),
    }


def paragraph_text(markdown_text: str) -> str:
    escaped = html.escape(markdown_text)
    escaped = re.sub(
        r"`([^`]+)`",
        r'<font color="#1F4D78">\1</font>',
        escaped,
    )
    return escaped


def parse_table_row(line: str) -> list[str]:
    text = line.strip().strip("|")
    return [cell.strip() for cell in text.split("|")]


def is_table_separator(line: str) -> bool:
    cells = parse_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def column_widths(rows: list[list[str]]) -> list[float]:
    columns = max(len(row) for row in rows)
    weights = []
    for col in range(columns):
        max_len = max((len(row[col]) if col < len(row) else 0) for row in rows)
        weights.append(min(max(max_len, 8), 34))
    total = sum(weights) or columns
    widths = [CONTENT_WIDTH * weight / total for weight in weights]
    min_width = 28 * mm
    shortfall = sum(max(0, min_width - width) for width in widths)
    if shortfall:
        wide_indexes = [idx for idx, width in enumerate(widths) if width > min_width]
        for idx in wide_indexes:
            widths[idx] -= shortfall / len(wide_indexes)
        widths = [max(min_width, width) for width in widths]
    return widths


def table_flowable(rows: list[list[str]], styles: dict[str, ParagraphStyle]) -> Table:
    max_columns = max(len(row) for row in rows)
    normalized = [row + [""] * (max_columns - len(row)) for row in rows]
    data = [
        [Paragraph(paragraph_text(cell), styles["small"]) for cell in row]
        for row in normalized
    ]
    table = Table(data, colWidths=column_widths(normalized), repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF5")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1F4D78")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D2DCE6")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFBFC")]),
            ]
        )
    )
    return table


def image_flowables(line: str, styles: dict[str, ParagraphStyle]) -> list[object]:
    match = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", line.strip())
    if not match:
        return []
    caption, relative = match.groups()
    image_path = (SOURCE_PATH.parent / relative).resolve()
    if not image_path.exists():
        return []
    with PILImage.open(image_path) as image:
        width, height = image.size
    max_width = CONTENT_WIDTH
    max_height = 130 * mm
    scale = min(max_width / width, max_height / height, 1)
    flowables: list[object] = [
        Image(str(image_path), width=width * scale, height=height * scale),
    ]
    if caption:
        flowables.append(Paragraph(paragraph_text(caption), styles["caption"]))
    return flowables


def list_flowable(items: list[str], ordered: bool, styles: dict[str, ParagraphStyle]) -> ListFlowable:
    flowables = [
        ListItem(Paragraph(paragraph_text(item), styles["body"]), leftIndent=9)
        for item in items
    ]
    return ListFlowable(
        flowables,
        bulletType="1" if ordered else "bullet",
        start="1",
        leftIndent=14,
        bulletFontName=FONT_NAME,
        bulletFontSize=8.5,
    )


def flush_paragraph(buffer: list[str], story: list[object], styles: dict[str, ParagraphStyle]) -> None:
    if not buffer:
        return
    text = " ".join(part.strip() for part in buffer if part.strip())
    if text:
        story.append(Paragraph(paragraph_text(text), styles["body"]))
    buffer.clear()


def flush_list(
    items: list[str],
    ordered: bool,
    story: list[object],
    styles: dict[str, ParagraphStyle],
) -> None:
    if not items:
        return
    story.append(list_flowable(items, ordered, styles))
    story.append(Spacer(1, 3))
    items.clear()


def build_story(markdown_text: str, styles: dict[str, ParagraphStyle]) -> list[object]:
    lines = markdown_text.splitlines()
    story: list[object] = []
    paragraph_buffer: list[str] = []
    list_items: list[str] = []
    list_ordered = False
    index = 0

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_paragraph(paragraph_buffer, story, styles)
            flush_list(list_items, list_ordered, story, styles)
            fence = stripped[3:].strip()
            code_lines = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            if fence != "mermaid":
                code_text = "<br/>".join(html.escape(item) or "&nbsp;" for item in code_lines)
                story.append(Paragraph(code_text, styles["code"]))
            index += 1
            continue

        if stripped.startswith("|") and "|" in stripped[1:]:
            flush_paragraph(paragraph_buffer, story, styles)
            flush_list(list_items, list_ordered, story, styles)
            table_lines = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index])
                index += 1
            rows = [parse_table_row(item) for item in table_lines if not is_table_separator(item)]
            if rows:
                story.append(table_flowable(rows, styles))
                story.append(Spacer(1, 8))
            continue

        if not stripped:
            flush_paragraph(paragraph_buffer, story, styles)
            flush_list(list_items, list_ordered, story, styles)
            story.append(Spacer(1, 2))
            index += 1
            continue

        image_items = image_flowables(stripped, styles)
        if image_items:
            flush_paragraph(paragraph_buffer, story, styles)
            flush_list(list_items, list_ordered, story, styles)
            story.extend(image_items)
            index += 1
            continue

        heading_match = re.match(r"^(#{1,3})\s+(.+)$", stripped)
        if heading_match:
            flush_paragraph(paragraph_buffer, story, styles)
            flush_list(list_items, list_ordered, story, styles)
            level = len(heading_match.group(1))
            text = heading_match.group(2).strip()
            if level == 1:
                story.append(Paragraph(paragraph_text(text), styles["title"]))
            elif level == 2:
                story.append(Paragraph(paragraph_text(text), styles["h1"]))
            else:
                story.append(Paragraph(paragraph_text(text), styles["h2"]))
            index += 1
            continue

        ordered_match = re.match(r"^\d+\.\s+(.+)$", stripped)
        bullet_match = re.match(r"^[-*]\s+(.+)$", stripped)
        if ordered_match or bullet_match:
            is_ordered = bool(ordered_match)
            item_text = ordered_match.group(1) if ordered_match else bullet_match.group(1)
            flush_paragraph(paragraph_buffer, story, styles)
            if list_items and list_ordered != is_ordered:
                flush_list(list_items, list_ordered, story, styles)
            list_ordered = is_ordered
            list_items.append(item_text)
            index += 1
            continue

        flush_list(list_items, list_ordered, story, styles)
        paragraph_buffer.append(stripped)
        index += 1

    flush_paragraph(paragraph_buffer, story, styles)
    flush_list(list_items, list_ordered, story, styles)
    return story


def add_page_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont(FONT_NAME, 8)
    canvas.setFillColor(colors.HexColor("#6B7C86"))
    canvas.drawString(MARGIN, 10 * mm, "AI辅助排课系统使用攻略")
    canvas.drawRightString(PAGE_WIDTH - MARGIN, 10 * mm, f"{doc.page}")
    canvas.restoreState()


def build_pdf() -> Path:
    register_fonts()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    styles = make_styles()
    markdown_text = SOURCE_PATH.read_text(encoding="utf-8")
    story = build_story(markdown_text, styles)
    doc = SimpleDocTemplate(
        str(PDF_PATH),
        pagesize=A4,
        rightMargin=MARGIN,
        leftMargin=MARGIN,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title="AI辅助排课系统使用攻略",
        author="AI辅助排课系统",
    )
    doc.build(story, onFirstPage=add_page_footer, onLaterPages=add_page_footer)
    return PDF_PATH


if __name__ == "__main__":
    print(build_pdf())
