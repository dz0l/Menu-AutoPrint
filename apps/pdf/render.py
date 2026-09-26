from __future__ import annotations

import base64
import logging
from io import BytesIO
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from apps.pdf.dates import format_print_date
from apps.pdf.layout import (
    PAGE_CONTENT_BOTTOM,
    FOOTER_FONT_SIZE,
    PAGE_FOOTER_Y,
    PAGE_MARGIN_LEFT,
    PAGE_MARGIN_RIGHT,
    PageLayout,
    _build_blocks,
    _page_content_top,
    _page_max_width,
    _total_blocks_height,
    compute_page_layout,
)
from apps.pdf.names import FOOTER_NOTE_EN, FOOTER_NOTE_RU


logger = logging.getLogger(__name__)

FONT_REGULAR = "MenuAutoPrintRegular"
FONT_BOLD = "MenuAutoPrintBold"
# Helvetica AFM ascent / 1000. Used only when no TTF is registered.
HELVETICA_BASELINE_RATIO = 0.718
# Chromium, line-height 1, bundled Times: baseline is 0.825 of the font size
# below the line-box top. hhea ascent/em (0.891) paints the line too high.
TIMES_CSS_BASELINE_RATIO = 0.825
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


def build_menu_pdf(
    *,
    preview: dict,
    print_date: str,
    show_kcal: bool,
    background_name: str = "",
    background_data: str = "",
    background_bytes: bytes | None = None,
    document_title: str = "menu.pdf",
    auto_format: bool = False,
) -> bytes:
    regular_font, bold_font = _ensure_fonts_registered()
    display_date = format_print_date(print_date)
    background = _load_background(background_data=background_data, background_bytes=background_bytes)
    layout_by_page = preview.get("layout") or {}

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4, pageCompression=1)
    pdf.setTitle(document_title)
    pdf.setAuthor("Menu AutoPrint")
    pdf.setCreator("Menu AutoPrint")
    pdf.setSubject("Generated menu")

    segments = preview.get("segments")
    if not segments:
        segments = [
            {
                "ru": preview.get("ru") or [],
                "en": preview.get("en") or [],
                "layout": layout_by_page,
            }
        ]

    page_drawn = False
    for segment in segments:
        seg_layout = segment.get("layout") or {}
        for page_name in ("ru", "en"):
            if page_drawn:
                pdf.showPage()
            items = segment.get(page_name) or []
            layout_data = seg_layout.get(page_name)
            if layout_data and all(
                key in layout_data
                for key in (
                    "menu_font_size",
                    "menu_leading",
                    "group_font_size",
                    "group_leading",
                    "continuation_leading",
                    "group_space_before",
                    "after_group_space_before",
                    "dish_space_before",
                )
            ):
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
            page_drawn = True

    pdf.save()
    return buffer.getvalue()


def get_menu_fonts() -> tuple[str, str]:
    return _ensure_fonts_registered()


def resolve_menu_font_files() -> tuple[Path, Path] | None:
    """TTF pair shared by PDF and HTML. Bundled Times is preferred over system fonts."""
    root = Path(__file__).resolve().parents[2]
    candidates = [
        (
            root / "fonts" / "Times New Roman.ttf",
            root / "fonts" / "Times New Roman Bold.ttf",
        ),
        *FONT_CANDIDATES,
    ]
    seen: set[tuple[Path, Path]] = set()
    for regular_path, bold_path in candidates:
        key = (regular_path, bold_path)
        if key in seen:
            continue
        seen.add(key)
        if regular_path.is_file() and bold_path.is_file():
            return regular_path, bold_path
    return None


def font_baseline_ratio(path: Path | None = None) -> float:
    """CSS shift that puts the browser baseline on the PDF layout-box top."""
    if path is None:
        files = resolve_menu_font_files()
        path = files[0] if files else None
    if path is None:
        return HELVETICA_BASELINE_RATIO
    hhea = _ttf_baseline_ratio(path)
    if abs(hhea - (1825 / 2048)) < 0.002:
        return TIMES_CSS_BASELINE_RATIO
    return hhea


def _ttf_baseline_ratio(path: Path) -> float:
    import struct

    data = path.read_bytes()
    table_count = struct.unpack(">H", data[4:6])[0]
    offset = 12
    tables: dict[bytes, int] = {}
    for _ in range(table_count):
        tag, _checksum, table_offset, _length = struct.unpack(">4sIII", data[offset : offset + 16])
        tables[tag] = table_offset
        offset += 16
    head = tables[b"head"]
    units = struct.unpack(">H", data[head + 18 : head + 20])[0]
    hhea = tables[b"hhea"]
    ascent = struct.unpack(">h", data[hhea + 4 : hhea + 6])[0]
    if units <= 0:
        return HELVETICA_BASELINE_RATIO
    return ascent / units


def _ensure_fonts_registered() -> tuple[str, str]:
    try:
        pdfmetrics.getFont(FONT_REGULAR)
        pdfmetrics.getFont(FONT_BOLD)
        return FONT_REGULAR, FONT_BOLD
    except KeyError:
        pass

    files = resolve_menu_font_files()
    if files is not None:
        regular_path, bold_path = files
        pdfmetrics.registerFont(TTFont(FONT_REGULAR, str(regular_path)))
        pdfmetrics.registerFont(TTFont(FONT_BOLD, str(bold_path)))
        return FONT_REGULAR, FONT_BOLD

    logger.warning("No Cyrillic-capable serif font found, falling back to Helvetica")
    return "Helvetica", "Helvetica-Bold"


def _load_background(*, background_data: str | None = None, background_bytes: bytes | None = None):
    if background_bytes:
        try:
            return ImageReader(BytesIO(background_bytes))
        except Exception as exc:
            logger.warning("Background bytes load failed: %s", exc)
            return None
    return _decode_background(background_data)


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
                raise ValueError(
                    "Меню не помещается на лист. Добавьте разделитель --- или сократите список."
                )
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
