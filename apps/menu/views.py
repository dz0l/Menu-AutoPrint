import logging
import re
import unicodedata
from collections import OrderedDict
from uuid import uuid4
from urllib.parse import quote

from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from apps.core.http_utils import admin_required as _admin_required
from apps.core.http_utils import editor_required as _editor_required
from apps.core.http_utils import json_body as _json_body
from apps.core.http_utils import request_payload as _request_payload
from apps.dishes.services import analyze_pasted
from apps.dishes.translation import is_translation_configured
from .archive import (
    MENU_TYPE_LABELS,
    disk_status,
    format_bytes,
    get_entry_for_download,
    list_archive_rows,
    purge_old_archives,
)
from .covers import (
    cover_absolute_path,
    cover_content_type,
    create_cover,
    delete_cover,
    get_cover,
    list_covers,
    read_cover_bytes,
    serialize_cover,
    update_cover_name,
)
from .document import (
    archive_pdf_for_user,
    build_document_payload,
    build_pdf_from_payload,
    bytes_to_data_url,
    validate_editor_menu_input,
)
from .models import MenuArchiveEntry, MenuCover
from apps.pdf.layout import page_frame
from apps.pdf.render import font_baseline_ratio, resolve_menu_font_files
from apps.pdf.services import (
    FOOTER_NOTE_EN,
    FOOTER_NOTE_RU,
)

logger = logging.getLogger(__name__)
SESSION_DOCUMENTS_KEY = "menu_rendered_documents"
SESSION_DOCUMENTS_LIMIT = 8
# Cap custom background data URLs stored in session (~1 MiB raw ≈ 1.4M base64 chars).
SESSION_BACKGROUND_MAX_CHARS = 1_500_000


def _ascii_filename(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    sanitized = re.sub(r'[^A-Za-z0-9._ -]+', "", normalized).strip()
    return sanitized or "menu.pdf"


def _bytes_to_data_url(data: bytes, content_type: str) -> str:
    return bytes_to_data_url(data, content_type)


def _store_document(request, payload: dict) -> str:
    token = uuid4().hex
    docs = OrderedDict(request.session.get(SESSION_DOCUMENTS_KEY, {}))
    docs[token] = payload
    while len(docs) > SESSION_DOCUMENTS_LIMIT:
        docs.popitem(last=False)
    request.session[SESSION_DOCUMENTS_KEY] = dict(docs)
    request.session.modified = True
    return token


def _session_safe_payload(payload: dict) -> dict:
    """Drop non-JSON bytes and avoid storing huge backgrounds in session."""
    stored = {key: value for key, value in payload.items() if key != "background_bytes"}
    if stored.get("cover_id") is not None:
        # Re-read from disk in document_print_page.
        stored["background_data"] = ""
        return stored
    background_data = stored.get("background_data") or ""
    if len(background_data) > SESSION_BACKGROUND_MAX_CHARS:
        raise ValueError(
            "Файл подложки слишком большой для альтернативной печати. "
            "Выберите серверную подложку или уменьшите файл."
        )
    return stored


def _resolve_print_background(payload: dict) -> str:
    background_data = payload.get("background_data") or ""
    if background_data:
        return background_data
    cover_id = payload.get("cover_id")
    if cover_id is None:
        return ""
    try:
        cover = get_cover(cover_id)
        return _bytes_to_data_url(read_cover_bytes(cover), cover_content_type(cover))
    except (MenuCover.DoesNotExist, FileNotFoundError):
        return ""


def _get_document(request, token: str) -> dict:
    docs = request.session.get(SESSION_DOCUMENTS_KEY, {})
    payload = docs.get(token)
    if not payload:
        raise Http404("document token not found")
    return payload


def _pdf_response(pdf: bytes, filename: str, *, download: bool = False) -> HttpResponse:
    disposition = "attachment" if download else "inline"
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = (
        f"{disposition}; filename=\"{_ascii_filename(filename)}\"; filename*=UTF-8''{quote(filename)}"
    )
    return response


def _document_pages(payload: dict) -> list[dict]:
    preview = payload.get("preview") or {}
    segments = preview.get("segments")
    if not segments:
        segments = [
            {
                "ru": preview.get("ru") or [],
                "en": preview.get("en") or [],
                "layout": preview.get("layout") or {},
            }
        ]
    pages = []
    for segment in segments:
        layout = segment.get("layout") or {}
        pages.append(
            {
                "label": "RU",
                "items": segment.get("ru") or [],
                "layout": layout.get("ru") or {},
                "footer_note": FOOTER_NOTE_RU,
            }
        )
        pages.append(
            {
                "label": "EN",
                "items": segment.get("en") or [],
                "layout": layout.get("en") or {},
                "footer_note": FOOTER_NOTE_EN,
            }
        )
    return pages


def _menu_font_context() -> dict:
    files = resolve_menu_font_files()
    regular = files[0] if files else None
    return {
        "menu_font_regular_url": reverse("menu:menu_font", args=["regular"]) if files else "",
        "menu_font_bold_url": reverse("menu:menu_font", args=["bold"]) if files else "",
        "baseline_ratio": f"{font_baseline_ratio(regular):.5f}",
    }


@ensure_csrf_cookie
@login_required
def index(request):
    return render(
        request,
        "menu/index.html",
        {
            "app_config": {
                "isAdmin": bool(getattr(request.user, "is_admin", False)),
            },
            "page_frame": page_frame(),
            **_menu_font_context(),
        },
    )


@ensure_csrf_cookie
@login_required
def editor(request):
    is_admin = bool(getattr(request.user, "is_admin", False))
    return render(
        request,
        "menu/editor.html",
        {
            "editor_config": {
                "translationEnabled": is_admin and is_translation_configured(),
                "canEditDatabase": is_admin,
                "isAdmin": is_admin,
            }
        },
    )


@ensure_csrf_cookie
@login_required
def archive_page(request):
    try:
        purge_old_archives()
    except Exception:
        logger.exception("Archive purge on page load failed")
    status = disk_status()
    raw_rows = list_archive_rows()
    type_columns = [
        {"key": MenuArchiveEntry.MenuType.BREAKFAST, "label": MENU_TYPE_LABELS[MenuArchiveEntry.MenuType.BREAKFAST]},
        {"key": MenuArchiveEntry.MenuType.MAIN, "label": MENU_TYPE_LABELS[MenuArchiveEntry.MenuType.MAIN]},
    ]
    rows = []
    for raw in raw_rows:
        cells = []
        for col in type_columns:
            item = raw["types"].get(col["key"])
            cells.append(
                {
                    "key": col["key"],
                    "label": col["label"],
                    "entry_id": item["id"] if item else None,
                }
            )
        rows.append(
            {
                "display_name": raw["display_name"],
                "cells": cells,
            }
        )
    return render(
        request,
        "menu/archive.html",
        {
            "disk": {
                **status,
                "total_label": format_bytes(status["total_bytes"]),
                "used_label": format_bytes(status["used_bytes"]),
                "free_label": format_bytes(status["free_bytes"]),
                "archive_label": format_bytes(status["archive_bytes"]),
                "threshold_label": format_bytes(status["low_space_threshold_bytes"]),
                "used_percent": (
                    format((status["used_bytes"] / status["total_bytes"]) * 100, ".1f")
                    if status["total_bytes"]
                    else "0"
                ),
                "archive_percent": (
                    format((status["archive_bytes"] / status["total_bytes"]) * 100, ".1f")
                    if status["total_bytes"]
                    else "0"
                ),
            },
            "rows": rows,
            "type_columns": type_columns,
        },
    )


@login_required
@require_http_methods(["GET"])
def archive_download(request, entry_id: int):
    try:
        entry, path = get_entry_for_download(entry_id)
    except FileNotFoundError:
        raise Http404("archive file not found") from None
    label = entry.display_name or f"{entry.menu_date.strftime('%d%m%Y')} - {MENU_TYPE_LABELS.get(entry.menu_type, entry.menu_type)}"
    filename = label if label.lower().endswith(".pdf") else f"{label}.pdf"
    pdf = path.read_bytes()
    return _pdf_response(pdf, filename, download=True)


@login_required
@require_http_methods(["POST"])
def preview_api(request):
    try:
        data = _request_payload(request)
        validate_editor_menu_input(data)
        return JsonResponse(build_document_payload(data)["preview"])
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@login_required
@require_http_methods(["POST"])
def analyze_api(request):
    if not _admin_required(request):
        return JsonResponse({"error": "forbidden"}, status=403)
    try:
        data = _request_payload(request)
        text = data.get("text", "")
        if text is None:
            text = ""
        if not isinstance(text, str):
            raise ValueError("text must be a string")
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse({"decisions": analyze_pasted(text)})


@login_required
@require_http_methods(["POST"])
def render_document_api(request):
    try:
        data = _request_payload(request)
        validate_editor_menu_input(data)
        payload = build_document_payload(data)
        stored = _session_safe_payload(payload)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    token = _store_document(request, stored)
    return JsonResponse(
        {
            "token": token,
            "filename": payload["filename"],
            "print_url": reverse("menu:document_print", args=[token]),
        }
    )


@login_required
@require_http_methods(["GET"])
def menu_font(request, weight: str):
    files = resolve_menu_font_files()
    if files is None or weight not in {"regular", "bold"}:
        raise Http404("font not found")
    path = files[0] if weight == "regular" else files[1]
    return FileResponse(path.open("rb"), content_type="font/ttf")


@login_required
def document_print_page(request, token: str):
    payload = _get_document(request, token)
    return render(
        request,
        "menu/print.html",
        {
            "token": token,
            "filename": payload["filename"],
            "display_date": payload["display_date"],
            "show_kcal": payload["show_kcal"],
            "background_data": _resolve_print_background(payload),
            "pages": _document_pages(payload),
            "page_frame": page_frame(),
            **_menu_font_context(),
        },
    )


@login_required
@require_http_methods(["POST"])
def pdf_api(request):
    try:
        data = _request_payload(request)
        validate_editor_menu_input(data)
        payload = build_document_payload(data)
        pdf = build_pdf_from_payload(payload)
        archive_pdf_for_user(request.user, pdf, payload)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        logger.exception("PDF generation failed hard: %s", exc)
        return JsonResponse({"error": "pdf_generation_failed"}, status=500)
    return _pdf_response(pdf, payload["filename"], download=True)


@login_required
@require_http_methods(["GET", "POST"])
def covers_api(request):
    if request.method == "GET":
        return JsonResponse({"covers": [serialize_cover(item) for item in list_covers()]})

    if not _admin_required(request):
        return JsonResponse({"error": "forbidden"}, status=403)
    uploaded = request.FILES.get("file")
    location_name = request.POST.get("location_name") or ""
    try:
        cover = create_cover(location_name=location_name, uploaded=uploaded, user=request.user)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception:
        logger.exception("Cover upload failed")
        return JsonResponse({"error": "cover_upload_failed"}, status=500)
    return JsonResponse({"cover": serialize_cover(cover)}, status=201)


@login_required
@require_http_methods(["PATCH", "DELETE"])
def cover_detail_api(request, cover_id: int):
    if not _admin_required(request):
        return JsonResponse({"error": "forbidden"}, status=403)
    cover = get_object_or_404(MenuCover, id=cover_id)
    if request.method == "DELETE":
        delete_cover(cover)
        return JsonResponse({"deleted": True})
    try:
        payload = _json_body(request)
        cover = update_cover_name(cover, payload.get("location_name") or "")
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse({"cover": serialize_cover(cover)})


@login_required
@require_http_methods(["GET"])
def cover_image_api(request, cover_id: int):
    cover = get_object_or_404(MenuCover, id=cover_id)
    path = cover_absolute_path(cover.relative_path)
    if not path.is_file():
        raise Http404("cover file not found")
    return FileResponse(path.open("rb"), content_type=cover_content_type(cover))
