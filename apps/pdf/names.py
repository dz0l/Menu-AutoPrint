from __future__ import annotations

from pathlib import Path

from apps.pdf.dates import format_print_stamp

UNKNOWN_LOCATION_LABEL = "unknown_location"

FOOTER_NOTE_RU = "Калорийность и вес указаны на порцию"
FOOTER_NOTE_EN = "Calories indicated per serving"


def build_download_filename(
    print_date: str,
    background_name: str = "",
    ru_lines: list[str] | None = None,
    *,
    location_label: str | None = None,
) -> str:
    breakfast_suffix = " (завтрак)" if _has_breakfast_first_group(ru_lines) else ""
    label = (location_label or "").strip() or resolve_cover_location(background_name)
    return f"{format_print_stamp(print_date)} - {label}{breakfast_suffix}.pdf"


def resolve_cover_location(background_name: str | None) -> str:
    """Custom uploaded backgrounds are treated as an unknown location."""
    _ = Path(background_name or "").name.strip().lower()
    return UNKNOWN_LOCATION_LABEL


def _has_breakfast_first_group(lines: list[str] | None) -> bool:
    if not lines:
        return False
    first = (lines[0] or "").strip().lower()
    return first == "завтрак:"
