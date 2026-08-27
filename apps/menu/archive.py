from __future__ import annotations

import logging
import re
import shutil
from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.pdf.services import UNKNOWN_LOCATION_LABEL, _parse_date, build_download_filename

from .models import MenuArchiveEntry

logger = logging.getLogger(__name__)

ARCHIVE_SUBDIR = "menu_archive"
UNKNOWN_LOCATION_KEY = "unknown_location"
MENU_TYPE_LABELS = {
    MenuArchiveEntry.MenuType.BREAKFAST: "Завтрак",
    MenuArchiveEntry.MenuType.MAIN: "Основное",
    MenuArchiveEntry.MenuType.BANQUET: "Банкет",
}


def archive_root() -> Path:
    root = Path(settings.MEDIA_ROOT) / ARCHIVE_SUBDIR
    root.mkdir(parents=True, exist_ok=True)
    return root


def retention_days() -> int:
    return int(getattr(settings, "MENU_ARCHIVE_RETENTION_DAYS", 730))


def low_space_threshold_bytes() -> int:
    return int(getattr(settings, "MENU_ARCHIVE_LOW_SPACE_BYTES", 2 * 1024**3))


def detect_menu_type(ru_lines: list[str] | None) -> str:
    """Return breakfast|main|banquet from the first RU group line."""
    if not ru_lines:
        return MenuArchiveEntry.MenuType.MAIN
    first = (ru_lines[0] or "").strip().lower()
    if first == "завтрак:":
        return MenuArchiveEntry.MenuType.BREAKFAST
    if first == "банкет:":
        return MenuArchiveEntry.MenuType.BANQUET
    return MenuArchiveEntry.MenuType.MAIN


def archive_location_key(background_name: str = "", *, explicit_key: str | None = None) -> str:
    """Stable filesystem/DB key for archive uniqueness."""
    if explicit_key:
        safe = re.sub(r"[^a-z0-9._-]+", "_", explicit_key.strip().lower()).strip("._-")
        return safe or UNKNOWN_LOCATION_KEY
    name = Path(background_name or "").name.strip().lower()
    if not name:
        return UNKNOWN_LOCATION_KEY
    stem = Path(name).stem.strip()
    safe = re.sub(r"[^a-z0-9._-]+", "_", stem).strip("._-")
    return safe or UNKNOWN_LOCATION_KEY


def archive_relative_path(menu_date: date, menu_type: str, location_key: str) -> str:
    safe = re.sub(r"[^a-z0-9._-]+", "_", (location_key or "").strip().lower()).strip("._-")
    if not safe:
        safe = UNKNOWN_LOCATION_KEY
    return f"{ARCHIVE_SUBDIR}/{menu_date.isoformat()}_{menu_type}_{safe}.pdf"


def archive_absolute_path(menu_date: date, menu_type: str, location_key: str) -> Path:
    return Path(settings.MEDIA_ROOT) / archive_relative_path(menu_date, menu_type, location_key)


def archive_display_name(
    print_date: str,
    background_name: str = "",
    ru_lines: list[str] | None = None,
    *,
    location_label: str | None = None,
) -> str:
    filename = build_download_filename(
        print_date,
        background_name,
        ru_lines=ru_lines,
        location_label=location_label,
    )
    if filename.lower().endswith(".pdf"):
        return filename[:-4]
    return filename


def archive_row_title(types: dict, menu_date: date, *, location_key: str = "", location_label: str = "") -> str:
    for key in (
        MenuArchiveEntry.MenuType.MAIN,
        MenuArchiveEntry.MenuType.BREAKFAST,
        MenuArchiveEntry.MenuType.BANQUET,
    ):
        item = types.get(key) or {}
        name = (item.get("display_name") or "").strip()
        if name:
            return name.replace(" (завтрак)", "").replace(" (банкет)", "")
    label = (location_label or "").strip()
    if label and label != UNKNOWN_LOCATION_LABEL and location_key and location_key != UNKNOWN_LOCATION_KEY:
        return f"{menu_date.strftime('%d%m%Y')} - {label}"
    return menu_date.strftime("%d%m%Y")


def save_menu_pdf_to_archive(
    pdf_bytes: bytes,
    *,
    print_date: str,
    ru_lines: list[str] | None = None,
    menu_type: str | None = None,
    background_name: str = "",
    location_key: str | None = None,
    location_label: str | None = None,
    user=None,
) -> MenuArchiveEntry:
    menu_date = _parse_date(print_date)
    resolved_type = menu_type or detect_menu_type(ru_lines)
    if resolved_type not in MenuArchiveEntry.MenuType.values:
        resolved_type = MenuArchiveEntry.MenuType.MAIN
    resolved_key = archive_location_key(background_name, explicit_key=location_key)

    relative = archive_relative_path(menu_date, resolved_type, resolved_key)
    absolute = Path(settings.MEDIA_ROOT) / relative
    absolute.parent.mkdir(parents=True, exist_ok=True)
    absolute.write_bytes(pdf_bytes)
    title = archive_display_name(
        print_date,
        background_name,
        ru_lines=ru_lines,
        location_label=location_label,
    )

    actor = user if getattr(user, "is_authenticated", False) else None
    lookup = {
        "menu_date": menu_date,
        "menu_type": resolved_type,
        "location_key": resolved_key,
    }
    with transaction.atomic():
        existing = MenuArchiveEntry.objects.filter(**lookup).first()
        old_relative = (existing.relative_path or "").replace("\\", "/") if existing else ""
        entry, _created = MenuArchiveEntry.objects.update_or_create(
            **lookup,
            defaults={
                "display_name": title,
                "relative_path": relative.replace("\\", "/"),
                "file_size": len(pdf_bytes),
                "created_by": actor,
            },
        )
    if old_relative and old_relative != relative.replace("\\", "/"):
        delete_archive_file(old_relative)
    try:
        purge_old_archives()
    except Exception:
        logger.exception("Menu archive purge after save failed")
    return entry


def delete_archive_file(relative_path: str) -> None:
    if not relative_path:
        return
    path = Path(settings.MEDIA_ROOT) / relative_path
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.exception("Failed to delete archive file %s", path)


def purge_old_archives(days: int | None = None) -> int:
    cutoff = timezone.localdate() - timedelta(days=days if days is not None else retention_days())
    removed = 0
    for entry in MenuArchiveEntry.objects.filter(menu_date__lt=cutoff).iterator():
        delete_archive_file(entry.relative_path)
        entry.delete()
        removed += 1
    return removed


def list_archive_rows() -> list[dict]:
    """Group entries by date + location for the archive table."""
    by_row: dict[tuple[date, str], dict] = {}
    for entry in MenuArchiveEntry.objects.all().iterator():
        location_key = entry.location_key or UNKNOWN_LOCATION_KEY
        row_key = (entry.menu_date, location_key)
        row = by_row.setdefault(
            row_key,
            {
                "menu_date": entry.menu_date,
                "location_key": location_key,
                "types": {},
            },
        )
        row["types"][entry.menu_type] = {
            "id": entry.id,
            "menu_type": entry.menu_type,
            "label": MENU_TYPE_LABELS.get(entry.menu_type, entry.menu_type),
            "display_name": entry.display_name or "",
            "file_size": entry.file_size,
            "updated_at": entry.updated_at,
        }
    rows = []
    for (menu_date, location_key), raw in by_row.items():
        rows.append(
            {
                "menu_date": menu_date,
                "location_key": location_key,
                "display_name": archive_row_title(raw["types"], menu_date, location_key=location_key),
                "types": raw["types"],
            }
        )
    rows.sort(key=lambda item: (item["menu_date"], item["location_key"]), reverse=True)
    return rows


def archive_bytes_on_disk() -> int:
    root = archive_root()
    total = 0
    for path in root.rglob("*.pdf"):
        try:
            total += path.stat().st_size
        except OSError:
            continue
    return total


def disk_status() -> dict:
    root = Path(settings.MEDIA_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(root)
    archive_bytes = archive_bytes_on_disk()
    free = int(usage.free)
    return {
        "total_bytes": int(usage.total),
        "used_bytes": int(usage.used),
        "free_bytes": free,
        "archive_bytes": archive_bytes,
        "low_space": free < low_space_threshold_bytes(),
        "low_space_threshold_bytes": low_space_threshold_bytes(),
    }


def format_bytes(value: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(max(0, int(value)))
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{int(value)} B"


def get_entry_for_download(entry_id: int) -> tuple[MenuArchiveEntry, Path]:
    entry = MenuArchiveEntry.objects.filter(id=entry_id).first()
    if not entry:
        raise FileNotFoundError("archive entry not found")
    path = Path(settings.MEDIA_ROOT) / entry.relative_path
    if not path.is_file():
        raise FileNotFoundError("archive file missing on disk")
    return entry, path
