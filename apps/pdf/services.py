from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


logger = logging.getLogger(__name__)

FONT_REGULAR = "MenuAutoPrintRegular"
FONT_BOLD = "MenuAutoPrintBold"
FOOTER_FONT_SIZE = 11
FONT_CANDIDATES = [
    (
        Path("/app/fonts/times.ttf"),
        Path("/app/fonts/timesbd.ttf"),
    ),
    (
        Path("/app/fonts/Times New Roman.ttf"),
        Path("/app/fonts/Times New Roman Bold.ttf"),
    ),
    (
        Path("/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman.ttf"),
        Path("/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman_Bold.ttf"),
    ),
    (
        Path("/usr/share/fonts/truetype/msttcorefonts/times.ttf"),
        Path("/usr/share/fonts/truetype/msttcorefonts/timesbd.ttf"),
    ),
    (
        Path("/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf"),
    ),
    (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"),
    ),
    (
        Path("C:/Windows/Fonts/times.ttf"),
        Path("C:/Windows/Fonts/timesbd.ttf"),
    ),
]

COVER_LOCATIONS = {
    "3k.jpg": "3й корпус",
    "airlines.jpg": "Самолёт",
    "banket.jpg": "Банкет",
    "board.jpg": "Лодка",
    "dd.jpg": "ДД",
    "dubai.jpg": "Дубай",
    "kd.jpg": "КД",
    "kd-ng.jpg": "КД НГ",
    "spa.jpg": "СПА",
    "tash.jpg": "Ташкент",
    "train.jpg": "Поезд",
    "vil126.jpg": "Вилла-126",
}

FOOTER_NOTE_RU = "Калорийность и вес указаны на порцию"
FOOTER_NOTE_EN = "Calories indicated per serving"
FOOTER_NOTE = FOOTER_NOTE_RU

BASE_MENU_FONT_SIZE = 20
BASE_MENU_LEADING = 28
BASE_GROUP_FONT_SIZE = 20
BASE_GROUP_LEADING = 28
BASE_CONTINUATION_LEADING = 18
BASE_GROUP_SPACE_BEFORE = 20
BASE_AFTER_GROUP_SPACE_BEFORE = 6
BASE_DISH_SPACE_BEFORE = 2
MIN_MENU_FONT_SIZE = 12

PAGE_MARGIN_LEFT = 42
PAGE_MARGIN_RIGHT = 42
PAGE_CONTENT_TOP_OFFSET = 48
PAGE_CONTENT_BOTTOM = 78
PAGE_FOOTER_Y = 28


@dataclass
class PageLayout:
    menu_font_size: int
    menu_leading: int
    group_font_size: int
    group_leading: int
    continuation_leading: int
    group_space_before: int
    after_group_space_before: int
    dish_space_before: int

    @classmethod
    def from_menu_font_size(cls, menu_font_size: int) -> PageLayout:
        scale = menu_font_size / BASE_MENU_FONT_SIZE
        return cls(
            menu_font_size=menu_font_size,
            menu_leading=max(1, round(BASE_MENU_LEADING * scale)),
            group_font_size=menu_font_size,
            group_leading=max(1, round(BASE_GROUP_LEADING * scale)),
            continuation_leading=max(1, round(BASE_CONTINUATION_LEADING * scale)),
            group_space_before=max(1, round(BASE_GROUP_SPACE_BEFORE * scale)),
            after_group_space_before=max(1, round(BASE_AFTER_GROUP_SPACE_BEFORE * scale)),
            dish_space_before=max(1, round(BASE_DISH_SPACE_BEFORE * scale)),
        )

    def to_dict(self) -> dict:
        return {
            "menu_font_size": self.menu_font_size,
            "menu_leading": self.menu_leading,
            "group_font_size": self.group_font_size,
            "group_leading": self.group_leading,
            "continuation_leading": self.continuation_leading,
            "group_space_before": self.group_space_before,
            "after_group_space_before": self.after_group_space_before,
            "dish_space_before": self.dish_space_before,
        }


@dataclass
class TextBlock:
    lines: list[str]
    font_name: str
    font_size: int
    leading: int
    continuation_leading: int
    space_before: int
    is_dish: bool = False


def build_menu_pdf(
    *,
    preview: dict,
    print_date: str,
    show_kcal: bool,
    background_name: str = "",
    background_data: str = "",
    document_title: str = "menu.pdf",
    auto_format: bool = True,
) -> bytes:
    regular_font, bold_font = _ensure_fonts_registered()
    display_date = format_print_date(print_date)
    background = _decode_background(background_data)
    layout_by_page = preview.get("layout") or {}

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4, pageCompression=1)
    pdf.setTitle(document_title)
    pdf.setAuthor("Menu AutoPrint")
    pdf.setCreator("Menu AutoPrint")
    pdf.setSubject("Generated menu")

    for index, page_name in enumerate(("ru", "en")):
        items = preview.get(page_name) or []
        layout_data = layout_by_page.get(page_name)
        if layout_data:
            layout = PageLayout(**layout_data)
        else:
            layout = compute_page_layout(
                items,
                auto_format=auto_format,
                regular_font=regular_font,
                bold_font=bold_font,
            )
        footer_note = FOOTER_NOTE_RU if page_name == "ru" else FOOTER_NOTE_EN
        _draw_preview_page(
            pdf,
            items=items,
            display_date=display_date,
            show_kcal=show_kcal,
            regular_font=regular_font,
            bold_font=bold_font,
            background=background,
            layout=layout,
            footer_note=footer_note,
        )
        if index == 0:
            pdf.showPage()

    pdf.save()
    return buffer.getvalue()


def build_download_filename(print_date: str, background_name: str = "", ru_lines: list[str] | None = None) -> str:
    breakfast_suffix = " (завтрак)" if _has_breakfast_first_group(ru_lines) else ""
    return f"{format_print_stamp(print_date)} - {resolve_cover_location(background_name)}{breakfast_suffix}.pdf"


def resolve_cover_location(background_name: str | None) -> str:
    normalized = Path(background_name or "").name.strip().lower()
    if not normalized:
        return "unknown_location"
    return COVER_LOCATIONS.get(normalized, "unknown_location")


def format_print_date(value: str | None) -> str:
    parsed = _parse_date(value)
    return parsed.strftime("%d.%m.%Y")


def format_print_stamp(value: str | None) -> str:
    parsed = _parse_date(value)
    return parsed.strftime("%d%m%Y")


def _has_breakfast_first_group(lines: list[str] | None) -> bool:
    if not lines:
        return False
    first = (lines[0] or "").strip().lower()
    return first == "завтрак:"


def _parse_date(value: str | None) -> date:
    raw = (value or "").strip()
    if not raw:
        return datetime.now().date()

    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return datetime.now().date()


def get_menu_fonts() -> tuple[str, str]:
    return _ensure_fonts_registered()


def _ensure_fonts_registered() -> tuple[str, str]:
    try:
        pdfmetrics.getFont(FONT_REGULAR)
        pdfmetrics.getFont(FONT_BOLD)
        return FONT_REGULAR, FONT_BOLD
    except KeyError:
        pass

    for regular_path, bold_path in FONT_CANDIDATES:
        if regular_path.exists() and bold_path.exists():
            pdfmetrics.registerFont(TTFont(FONT_REGULAR, str(regular_path)))
            pdfmetrics.registerFont(TTFont(FONT_BOLD, str(bold_path)))
            return FONT_REGULAR, FONT_BOLD

    logger.warning("No Cyrillic-capable serif font found, falling back to Helvetica")
    return "Helvetica", "Helvetica-Bold"


def _decode_background(background_data: str | None):
    raw = (background_data or "").strip()
    if not raw:
        return None

    try:
        payload = raw.split(",", 1)[1] if raw.startswith("data:") and "," in raw else raw
        image_bytes = base64.b64decode(payload)
        return ImageReader(BytesIO(image_bytes))
    except Exception as exc:
        logger.warning("Background decode failed: %s", exc)
        return None


def _draw_preview_page(
    pdf: canvas.Canvas,
    *,
    items: list[dict],
    display_date: str,
    show_kcal: bool,
    regular_font: str,
    bold_font: str,
    background,
    layout: PageLayout,
    footer_note: str,
) -> None:
    width, height = A4
    left = PAGE_MARGIN_LEFT
    right = width - PAGE_MARGIN_RIGHT
    footer_y = PAGE_FOOTER_Y
    content_bottom = PAGE_CONTENT_BOTTOM
    top = _page_content_top()
    max_width = _page_max_width()

    if background is not None:
        _draw_background(pdf, background, width, height)

    blocks = _build_blocks(
        items,
        max_width=max_width,
        regular_font=regular_font,
        bold_font=bold_font,
        layout=layout,
    )
    total_height = _total_blocks_height(blocks)
    available_height = max(top - content_bottom, 0)
    y = min(top, content_bottom + available_height / 2 + total_height / 2)

    for block in blocks:
        y -= block.space_before
        pdf.setFont(block.font_name, block.font_size)
        for line_index, line in enumerate(block.lines):
            if y < content_bottom:
                break
            pdf.drawCentredString(width / 2, y, line)
            if line_index < len(block.lines) - 1:
                if block.is_dish and line_index == 0:
                    y -= block.continuation_leading
                else:
                    y -= block.leading
            else:
                y -= block.leading

    pdf.setFont(regular_font, FOOTER_FONT_SIZE)
    if show_kcal:
        pdf.drawString(left, footer_y, footer_note)
    pdf.drawRightString(right, footer_y, display_date)


def _page_content_top() -> float:
    return A4[1] - PAGE_CONTENT_TOP_OFFSET


def _page_max_width() -> float:
    return A4[0] - PAGE_MARGIN_LEFT - PAGE_MARGIN_RIGHT


def _block_height(block: TextBlock) -> float:
    height = block.space_before
    if not block.lines:
        return height
    for line_index in range(1, len(block.lines)):
        if block.is_dish and line_index == 1:
            height += block.continuation_leading
        else:
            height += block.leading
    height += block.leading
    return height


def _total_blocks_height(blocks: list[TextBlock]) -> float:
    return sum(_block_height(block) for block in blocks)


def compute_page_layout(
    items: list[dict],
    *,
    auto_format: bool,
    regular_font: str,
    bold_font: str,
) -> PageLayout:
    if not auto_format:
        return PageLayout.from_menu_font_size(BASE_MENU_FONT_SIZE)

    available_height = _page_content_top() - PAGE_CONTENT_BOTTOM
    for font_size in range(BASE_MENU_FONT_SIZE, MIN_MENU_FONT_SIZE - 1, -1):
        layout = PageLayout.from_menu_font_size(font_size)
        blocks = _build_blocks(
            items,
            max_width=_page_max_width(),
            regular_font=regular_font,
            bold_font=bold_font,
            layout=layout,
        )
        if _total_blocks_height(blocks) <= available_height:
            return layout
    return PageLayout.from_menu_font_size(MIN_MENU_FONT_SIZE)


def enrich_page_items(
    items: list[dict],
    *,
    layout: PageLayout,
    regular_font: str,
    bold_font: str,
) -> list[dict]:
    max_width = _page_max_width()
    enriched: list[dict] = []
    for item in items:
        copy = dict(item)
        if item.get("type") == "group":
            text = f"{item.get('text', '')}{item.get('suffix', '')}".strip()
            copy["lines"] = _wrap_text(
                text,
                max_width=max_width,
                font_name=bold_font,
                font_size=layout.group_font_size,
            )
        else:
            copy["lines"] = _wrap_dish_lines(
                item.get("text", ""),
                item.get("suffix", ""),
                max_width=max_width,
                font_name=regular_font,
                font_size=layout.menu_font_size,
            )
        enriched.append(copy)
    return enriched


def _draw_background(pdf: canvas.Canvas, background, page_width: float, page_height: float) -> None:
    try:
        image_width, image_height = background.getSize()
        scale = max(page_width / image_width, page_height / image_height)
        draw_width = image_width * scale
        draw_height = image_height * scale
        x = (page_width - draw_width) / 2
        y = (page_height - draw_height) / 2
        pdf.drawImage(background, x, y, width=draw_width, height=draw_height, mask="auto")

        pdf.saveState()
        if hasattr(pdf, "setFillAlpha"):
            pdf.setFillAlpha(0.72)
        pdf.setFillColorRGB(1, 1, 1)
        pdf.rect(0, 0, page_width, page_height, fill=1, stroke=0)
        pdf.restoreState()
    except Exception as exc:
        logger.warning("Background draw failed: %s", exc)


def _build_blocks(
    items: list[dict],
    *,
    max_width: float,
    regular_font: str,
    bold_font: str,
    layout: PageLayout,
) -> list[TextBlock]:
    blocks: list[TextBlock] = []
    previous_type = None
    for index, item in enumerate(items):
        is_group = item.get("type") == "group"
        if index == 0:
            space_before = 0
        elif is_group:
            space_before = layout.group_space_before
        elif previous_type == "group":
            space_before = layout.after_group_space_before
        else:
            space_before = layout.dish_space_before

        if is_group:
            text = f"{item.get('text', '')}{item.get('suffix', '')}".strip()
            block_lines = _wrap_text(
                text,
                max_width=max_width,
                font_name=bold_font,
                font_size=layout.group_font_size,
            )
            blocks.append(
                TextBlock(
                    lines=block_lines,
                    font_name=bold_font,
                    font_size=layout.group_font_size,
                    leading=layout.group_leading,
                    continuation_leading=layout.group_leading,
                    space_before=space_before,
                    is_dish=False,
                )
            )
            previous_type = "group"
            continue

        block_lines = _wrap_dish_lines(
            item.get("text", ""),
            item.get("suffix", ""),
            max_width=max_width,
            font_name=regular_font,
            font_size=layout.menu_font_size,
        )
        blocks.append(
            TextBlock(
                lines=block_lines,
                font_name=regular_font,
                font_size=layout.menu_font_size,
                leading=layout.menu_leading,
                continuation_leading=layout.continuation_leading,
                space_before=space_before,
                is_dish=True,
            )
        )
        previous_type = "dish"
    return blocks


def _wrap_dish_lines(text: str, suffix: str, *, max_width: float, font_name: str, font_size: int) -> list[str]:
    bullet = "• "
    raw = (text or "").strip()
    full = f"{bullet}{raw}{suffix}"
    if _text_width(full, font_name, font_size) <= max_width:
        return [full]

    if not suffix:
        return _wrap_text(full, max_width=max_width, font_name=font_name, font_size=font_size)

    words = raw.split()
    for split_index in range(len(words) - 1, 0, -1):
        head = " ".join(words[:split_index]).strip()
        tail = " ".join(words[split_index:]).strip()
        first_line = f"{bullet}{head}".rstrip()
        second_line = f"{tail}{suffix}".strip()
        if (
            head
            and tail
            and _text_width(first_line, font_name, font_size) <= max_width
            and _text_width(second_line, font_name, font_size) <= max_width
        ):
            return [first_line, second_line]

    return _wrap_head_and_tail(raw, suffix, max_width=max_width, font_name=font_name, font_size=font_size)


def _wrap_head_and_tail(text: str, suffix: str, *, max_width: float, font_name: str, font_size: int) -> list[str]:
    bullet = "• "
    words = (text or "").split()
    if not words:
        return [f"{bullet}{suffix}".strip()]
    if len(words) == 1:
        return _wrap_text(f"{bullet}{words[0]}{suffix}", max_width=max_width, font_name=font_name, font_size=font_size)

    head_words = words[:-1]
    tail = f"{words[-1]}{suffix}"
    lines: list[str] = []
    current = bullet.rstrip()

    for word in head_words:
        candidate = f"{current} {word}".strip()
        if current and _text_width(candidate, font_name, font_size) > max_width and current != bullet.rstrip():
            lines.append(current)
            current = word
        else:
            current = candidate

    if current:
        lines.append(current)
    lines.append(tail)
    return lines


def _wrap_text(text: str, *, max_width: float, font_name: str, font_size: int) -> list[str]:
    words = (text or "").split()
    if not words:
        return [""]

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}".strip()
        if _text_width(candidate, font_name, font_size) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _split_last_word(text: str) -> tuple[str, str]:
    raw = (text or "").strip()
    parts = raw.rsplit(" ", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return "", raw


def _text_width(text: str, font_name: str, font_size: int) -> float:
    return pdfmetrics.stringWidth(text, font_name, font_size)
