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
MENU_FONT_SIZE = 20
MENU_LEADING = 24
GROUP_FONT_SIZE = 20
GROUP_LEADING = 24
FOOTER_FONT_SIZE = 11
FONT_CANDIDATES = [
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

FOOTER_NOTE = "Калории указаны за порцию / Calories indicated per serving"


@dataclass
class TextBlock:
    lines: list[str]
    font_name: str
    font_size: int
    leading: int
    space_before: int


def build_menu_pdf(
    *,
    preview: dict,
    print_date: str,
    show_kcal: bool,
    background_name: str = "",
    background_data: str = "",
) -> bytes:
    regular_font, bold_font = _ensure_fonts_registered()
    display_date = format_print_date(print_date)
    background = _decode_background(background_data)

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4, pageCompression=1)

    for index, page_name in enumerate(("ru", "en")):
        _draw_preview_page(
            pdf,
            items=preview.get(page_name) or [],
            display_date=display_date,
            show_kcal=show_kcal,
            regular_font=regular_font,
            bold_font=bold_font,
            background=background,
        )
        if index == 0:
            pdf.showPage()

    pdf.save()
    return buffer.getvalue()


def build_download_filename(print_date: str, background_name: str = "") -> str:
    return f"{format_print_stamp(print_date)} - {resolve_cover_location(background_name)}.pdf"


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
) -> None:
    width, height = A4
    left = 42
    right = width - 42
    footer_y = 28
    content_bottom = 78
    top = height - 48
    max_width = right - left

    if background is not None:
        _draw_background(pdf, background, width, height)

    blocks = _build_blocks(items, max_width=max_width, regular_font=regular_font, bold_font=bold_font)
    total_height = sum(block.space_before + len(block.lines) * block.leading for block in blocks)
    available_height = max(top - content_bottom, 0)
    y = min(top, content_bottom + available_height / 2 + total_height / 2)

    for block in blocks:
        y -= block.space_before
        pdf.setFont(block.font_name, block.font_size)
        for line in block.lines:
            if y < content_bottom:
                break
            pdf.drawCentredString(width / 2, y, line)
            y -= block.leading

    pdf.setFont(regular_font, FOOTER_FONT_SIZE)
    if show_kcal:
        pdf.drawString(left, footer_y, FOOTER_NOTE)
    pdf.drawRightString(right, footer_y, display_date)


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


def _build_blocks(items: list[dict], *, max_width: float, regular_font: str, bold_font: str) -> list[TextBlock]:
    blocks: list[TextBlock] = []
    for item in items:
        is_group = item.get("type") == "group"
        text = f"{item.get('text', '')}{item.get('suffix', '')}".strip()
        if is_group:
            lines = _wrap_text(text, max_width=max_width, font_name=bold_font, font_size=GROUP_FONT_SIZE)
            blocks.append(
                TextBlock(
                    lines=lines,
                    font_name=bold_font,
                    font_size=GROUP_FONT_SIZE,
                    leading=GROUP_LEADING,
                    space_before=16,
                )
            )
            continue

        lines = _wrap_dish_lines(
            item.get("text", ""),
            item.get("suffix", ""),
            max_width=max_width,
            font_name=regular_font,
            font_size=MENU_FONT_SIZE,
        )
        blocks.append(
            TextBlock(
                lines=lines,
                font_name=regular_font,
                font_size=MENU_FONT_SIZE,
                leading=MENU_LEADING,
                space_before=0,
            )
        )
    return blocks


def _wrap_dish_lines(text: str, suffix: str, *, max_width: float, font_name: str, font_size: int) -> list[str]:
    bullet = "• "
    raw = (text or "").strip()
    full = f"{bullet}{raw}{suffix}"
    if _text_width(full, font_name, font_size) <= max_width:
        return [full]

    prefix, last = _split_last_word(raw)
    tail = f"{last}{suffix}" if last else f"{raw}{suffix}"
    first_line = f"{bullet}{prefix}".rstrip()

    if prefix and _text_width(first_line, font_name, font_size) <= max_width and _text_width(tail, font_name, font_size) <= max_width:
        return [first_line, tail]

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
