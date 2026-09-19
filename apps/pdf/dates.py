from __future__ import annotations

from datetime import date, datetime


def format_print_date(value: str | None) -> str:
    parsed = parse_date(value)
    return parsed.strftime("%d.%m.%Y")


def format_print_stamp(value: str | None) -> str:
    parsed = parse_date(value)
    return parsed.strftime("%d%m%Y")


def parse_date(value: str | None) -> date:
    raw = (value or "").strip()
    if not raw:
        return datetime.now().date()

    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError("Некорректная дата печати.")


# Backward-compatible alias for older imports.
_parse_date = parse_date
