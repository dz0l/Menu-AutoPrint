"""Shared menu document build / PDF / archive used by web and integration API."""

from __future__ import annotations

import base64
import logging

from apps.pdf.services import (
    UNKNOWN_LOCATION_LABEL,
    build_download_filename,
    build_menu_pdf,
    format_print_date,
)

from .archive import find_archive_entry, save_menu_pdf_to_archive
from .covers import cover_content_type, get_cover, read_cover_bytes
from .models import MenuCover
from .services import build_preview, normalize_lines, translate_lines

logger = logging.getLogger(__name__)


def parse_cover_id(value) -> int | None:
    if value in (None, "", "null", "undefined"):
        return None
    try:
        cover_id = int(value)
    except (TypeError, ValueError):
        return None
    return cover_id if cover_id > 0 else None


def bytes_to_data_url(data: bytes, content_type: str) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


def validate_editor_menu_input(data: dict) -> None:
    """Reject editor document types before preview, session storage, or archive.

    Web keeps its ``{"error": string}`` responses. Booleans stay loose: an empty
    or null ``show_kcal`` still means off. Integration validates on its own path.
    """
    if not isinstance(data, dict):
        raise ValueError("invalid payload")
    if "ru" in data:
        ru = data.get("ru")
    elif "ru_lines" in data:
        ru = data.get("ru_lines")
    else:
        ru = ""
    if ru is None:
        ru = ""
    ru_ok = isinstance(ru, str) or (
        isinstance(ru, list) and all(item is None or isinstance(item, str) for item in ru)
    )
    if not ru_ok:
        raise ValueError("ru must be a string")
    if "print_date" in data and data["print_date"] not in (None, "") and not isinstance(data["print_date"], str):
        raise ValueError("print_date must be a string")
    for key in ("background_name", "background_data"):
        if key in data and data[key] not in (None, "") and not isinstance(data[key], str):
            raise ValueError(f"{key} must be a string")
    if "cover_id" in data and data["cover_id"] not in (None, "", "null", "undefined"):
        cover_id = data["cover_id"]
        if isinstance(cover_id, bool) or isinstance(cover_id, float) or not isinstance(cover_id, (int, str)):
            raise ValueError("cover_id must be a positive integer")


def build_document_payload(
    data: dict,
    *,
    require_cover: bool = False,
    require_print_date: bool = False,
    dishes=None,
) -> dict:
    ru_lines = normalize_lines(data.get("ru") or data.get("ru_lines"))
    en_lines = translate_lines(ru_lines, dishes=dishes)
    show_kcal = _as_bool(data.get("show_kcal", True), default=True, strict=False)
    auto_format = _as_bool(data.get("auto_format", False), default=False, strict=False)
    print_date = data.get("print_date") or ""
    if isinstance(print_date, str):
        print_date = print_date.strip()
    else:
        print_date = str(print_date or "").strip()
    if require_print_date and not print_date:
        raise ValueError("print_date required")

    background_name = data.get("background_name") or ""
    background_data = data.get("background_data") or ""
    background_bytes = None
    location_label = UNKNOWN_LOCATION_LABEL
    location_key = None
    cover_id = parse_cover_id(data.get("cover_id"))

    if require_cover and cover_id is None:
        raise ValueError("cover_id required")

    if cover_id is not None:
        try:
            cover = get_cover(cover_id)
        except MenuCover.DoesNotExist as exc:
            raise ValueError("Подложка не найдена.") from exc
        try:
            background_bytes = read_cover_bytes(cover)
        except FileNotFoundError as exc:
            raise ValueError("Файл подложки отсутствует на сервере.") from exc
        background_data = bytes_to_data_url(background_bytes, cover_content_type(cover))
        background_name = cover.original_filename
        location_label = cover.location_name
        location_key = cover.location_key
    else:
        location_label = UNKNOWN_LOCATION_LABEL
        location_key = "unknown_location"

    preview = build_preview(ru_lines, en_lines, show_kcal=show_kcal, auto_format=auto_format, dishes=dishes)
    filename = build_download_filename(
        print_date,
        background_name,
        ru_lines=ru_lines,
        location_label=location_label,
    )
    return {
        "preview": preview,
        "show_kcal": show_kcal,
        "auto_format": auto_format,
        "print_date": print_date,
        "display_date": format_print_date(print_date),
        "background_name": background_name,
        "background_data": background_data,
        "background_bytes": background_bytes,
        "location_label": location_label,
        "location_key": location_key,
        "cover_id": cover_id,
        "filename": filename,
        "ru_lines": ru_lines,
    }


def build_pdf_from_payload(payload: dict) -> bytes:
    return build_menu_pdf(
        preview=payload["preview"],
        print_date=payload.get("print_date") or "",
        show_kcal=bool(payload.get("show_kcal")),
        background_name=payload.get("background_name") or "",
        background_data=payload.get("background_data") or "",
        background_bytes=payload.get("background_bytes"),
        document_title=payload.get("filename") or "menu.pdf",
        auto_format=bool(payload.get("auto_format", False)),
    )


def archive_conflict_status(data: dict) -> dict:
    """Whether this document would replace an existing archive file. Read-only."""
    ru_lines = normalize_lines(data.get("ru") or data.get("ru_lines"))
    print_date = data.get("print_date") or ""
    if isinstance(print_date, str):
        print_date = print_date.strip()
    else:
        print_date = str(print_date or "").strip()
    background_name = data.get("background_name") or ""
    if not isinstance(background_name, str):
        background_name = ""
    location_key = None
    cover_id = parse_cover_id(data.get("cover_id"))
    if cover_id is not None:
        try:
            cover = get_cover(cover_id)
        except MenuCover.DoesNotExist as exc:
            raise ValueError("Подложка не найдена.") from exc
        background_name = cover.original_filename
        location_key = cover.location_key
    entry = find_archive_entry(
        print_date=print_date,
        ru_lines=ru_lines,
        background_name=background_name,
        location_key=location_key,
    )
    return {
        "exists": entry is not None,
        "display_name": (entry.display_name or "").strip() if entry else "",
    }


def archive_pdf_for_user(user, pdf: bytes, payload: dict) -> None:
    """Persist PDF for archive when actor is application admin."""
    if not getattr(user, "is_admin", False):
        return
    try:
        save_menu_pdf_to_archive(
            pdf,
            print_date=payload.get("print_date") or "",
            ru_lines=payload.get("ru_lines"),
            background_name=payload.get("background_name") or "",
            location_key=payload.get("location_key"),
            location_label=payload.get("location_label"),
            user=user,
        )
    except Exception as exc:
        logger.exception("Failed to save menu PDF to archive")
        raise ValueError("Не удалось сохранить PDF в архив. Проверьте диск и повторите.") from exc


def _as_bool(value, *, default: bool, strict: bool) -> bool:
    if isinstance(value, bool):
        return value
    if strict:
        raise ValueError("boolean required")
    # Legacy API: null / empty string means "off", not the declared default.
    if value in (None, ""):
        return False
    return str(value).strip().lower() not in {"", "0", "false", "no", "off", "none"}
