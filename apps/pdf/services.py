from io import BytesIO
from pathlib import Path
import logging

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


logger = logging.getLogger(__name__)

FONT_NAME = "MenuAutoPrintDejaVu"
FONT_CANDIDATES = [
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("C:/Windows/Fonts/times.ttf"),
    Path("C:/Windows/Fonts/arial.ttf"),
]


def build_menu_pdf(*, html: str, base_url: str, preview: dict, print_date: str) -> bytes:
    try:
        from weasyprint import HTML

        return HTML(string=html, base_url=base_url).write_pdf()
    except Exception as exc:
        logger.exception("WeasyPrint PDF generation failed: %s", exc)

    return build_reportlab_pdf(preview=preview, print_date=print_date)


def _ensure_font_registered() -> str:
    try:
        pdfmetrics.getFont(FONT_NAME)
        return FONT_NAME
    except KeyError:
        pass

    for candidate in FONT_CANDIDATES:
        if candidate.exists():
            pdfmetrics.registerFont(TTFont(FONT_NAME, str(candidate)))
            return FONT_NAME

    logger.warning("DejaVu font not found, falling back to Helvetica")
    return "Helvetica"


def build_reportlab_pdf(*, preview: dict, print_date: str) -> bytes:
    font_name = _ensure_font_registered()
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)

    page_names = ("ru", "en")
    for index, page_name in enumerate(page_names):
        _draw_preview_page(pdf, preview.get(page_name) or [], print_date, font_name)
        if index < len(page_names) - 1:
            pdf.showPage()

    pdf.save()
    return buffer.getvalue()


def _draw_preview_page(pdf: canvas.Canvas, items: list[dict], print_date: str, font_name: str) -> None:
    width, height = A4
    left = 42
    right = width - 42
    bottom = 52
    top = height - 58
    max_width = right - left

    blocks = []
    total_height = 0
    for item in items:
        is_group = item.get("type") == "group"
        text = f"{item.get('text', '')}{item.get('suffix', '')}"
        if not is_group:
            text = f"\u2022 {text}"

        font_size = 18 if is_group else 15
        leading = 24 if is_group else 19
        space_before = 14 if is_group else 0
        wrapped = simpleSplit(text, font_name, font_size, max_width) or [text]
        block_height = space_before + len(wrapped) * leading
        blocks.append(
            {
                "font_size": font_size,
                "leading": leading,
                "space_before": space_before,
                "lines": wrapped,
            }
        )
        total_height += block_height

    available_height = max(top - bottom - 28, 0)
    start_y = min(top, bottom + available_height / 2 + total_height / 2)
    y = start_y

    for block in blocks:
        y -= block["space_before"]
        pdf.setFont(font_name, block["font_size"])
        for line in block["lines"]:
            if y < bottom + 20:
                break
            pdf.drawCentredString(width / 2, y, line)
            y -= block["leading"]

    if print_date:
        pdf.setFont(font_name, 10)
        pdf.drawRightString(right, 24, print_date)
