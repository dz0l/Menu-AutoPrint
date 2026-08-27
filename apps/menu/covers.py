from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction

from .models import MenuCover

logger = logging.getLogger(__name__)

COVERS_SUBDIR = "menu_covers"
MAX_COVER_BYTES = 3 * 1024 * 1024
ALLOWED_COVER_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/pjpeg",
    "image/png",
}
ALLOWED_COVER_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def covers_root() -> Path:
    root = Path(settings.MEDIA_ROOT) / COVERS_SUBDIR
    root.mkdir(parents=True, exist_ok=True)
    return root


def cover_absolute_path(relative_path: str) -> Path:
    return Path(settings.MEDIA_ROOT) / relative_path


def serialize_cover(cover: MenuCover) -> dict:
    return {
        "id": cover.id,
        "location_name": cover.location_name,
        "original_filename": cover.original_filename,
        "file_size": cover.file_size,
        "location_key": cover.location_key,
        "updated_at": cover.updated_at.isoformat() if cover.updated_at else "",
    }


def list_covers() -> list[MenuCover]:
    return list(MenuCover.objects.all().order_by("location_name", "id"))


def get_cover(cover_id: int) -> MenuCover:
    return MenuCover.objects.get(id=cover_id)


def _sanitize_extension(filename: str) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix == ".jpeg":
        return ".jpg"
    if suffix in ALLOWED_COVER_EXTENSIONS:
        return suffix
    return ""


def _validate_upload(uploaded: UploadedFile) -> str:
    if not uploaded:
        raise ValueError("Выберите файл подложки.")
    if uploaded.size and uploaded.size > MAX_COVER_BYTES:
        raise ValueError("Подложка слишком большая. Выберите изображение меньше 3 МБ.")
    content_type = (uploaded.content_type or "").lower()
    extension = _sanitize_extension(uploaded.name or "")
    if content_type and content_type not in ALLOWED_COVER_CONTENT_TYPES and not extension:
        raise ValueError("Поддерживаются только JPG и PNG.")
    if not extension:
        if content_type in {"image/png"}:
            extension = ".png"
        elif content_type in ALLOWED_COVER_CONTENT_TYPES:
            extension = ".jpg"
        else:
            raise ValueError("Поддерживаются только JPG и PNG.")
    return extension


def create_cover(*, location_name: str, uploaded: UploadedFile, user=None) -> MenuCover:
    name = (location_name or "").strip()
    if not name:
        raise ValueError("Укажите название локации.")
    if len(name) > 128:
        raise ValueError("Название слишком длинное.")
    extension = _validate_upload(uploaded)

    stored_name = f"{uuid.uuid4().hex}{extension}"
    relative = f"{COVERS_SUBDIR}/{stored_name}".replace("\\", "/")
    absolute = cover_absolute_path(relative)
    absolute.parent.mkdir(parents=True, exist_ok=True)

    with absolute.open("wb") as handle:
        for chunk in uploaded.chunks():
            handle.write(chunk)

    actor = user if getattr(user, "is_authenticated", False) else None
    try:
        cover = MenuCover.objects.create(
            location_name=name,
            original_filename=Path(uploaded.name or stored_name).name[:255],
            relative_path=relative,
            file_size=absolute.stat().st_size,
            created_by=actor,
        )
    except Exception:
        absolute.unlink(missing_ok=True)
        raise
    return cover


def update_cover_name(cover: MenuCover, location_name: str) -> MenuCover:
    name = (location_name or "").strip()
    if not name:
        raise ValueError("Укажите название локации.")
    if len(name) > 128:
        raise ValueError("Название слишком длинное.")
    cover.location_name = name
    cover.save(update_fields=["location_name", "updated_at"])
    return cover


def delete_cover(cover: MenuCover) -> None:
    relative = cover.relative_path
    with transaction.atomic():
        cover.delete()
    if relative:
        path = cover_absolute_path(relative)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.exception("Failed to delete cover file %s", path)


def read_cover_bytes(cover: MenuCover) -> bytes:
    path = cover_absolute_path(cover.relative_path)
    if not path.is_file():
        raise FileNotFoundError("cover file missing")
    return path.read_bytes()


def cover_content_type(cover: MenuCover) -> str:
    suffix = Path(cover.relative_path or cover.original_filename).suffix.lower()
    if suffix == ".png":
        return "image/png"
    return "image/jpeg"


def safe_location_key_from_name(value: str = "") -> str:
    safe = re.sub(r"[^a-z0-9._-]+", "_", (value or "").strip().lower()).strip("._-")
    return safe or "unknown_location"
