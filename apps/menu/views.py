import base64
import json
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

from apps.dishes.services import analyze_pasted
from apps.dishes.translation import is_translation_configured
from .archive import (
    MENU_TYPE_LABELS,
    disk_status,
    format_bytes,
    get_entry_for_download,
    list_archive_rows,
    purge_old_archives,
    save_menu_pdf_to_archive,
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
from .models import MenuArchiveEntry, MenuCover
from apps.pdf.services import (
    FOOTER_NOTE_EN,
    FOOTER_NOTE_RU,
    UNKNOWN_LOCATION_LABEL,
    build_download_filename,
    build_menu_pdf,
    format_print_date,
)

from .services import build_preview, normalize_lines, translate_lines


logger = logging.getLogger(__name__)
SESSION_DOCUMENTS_KEY = "menu_rendered_documents"
SESSION_DOCUMENTS_LIMIT = 8


def _json_body(request) -> dict:
    if not request.body:
        return {}
    return json.loads(request.body.decode("utf-8"))


def _request_payload(request) -> dict:
    if request.content_type and "application/json" in request.content_type:
        return _json_body(request)
    return request.POST.dict()


def _to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"", "0", "false", "no", "off", "none"}


def _ascii_filename(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    sanitized = re.sub(r'[^A-Za-z0-9._ -]+', "", normalized).strip()
    return sanitized or "menu.pdf"


def _editor_required(request) -> bool:
    return request.user.is_authenticated and request.user.is_active


def _admin_required(request) -> bool:
    return _editor_required(request) and bool(getattr(request.user, "is_admin", False))


def _parse_cover_id(value) -> int | None:
    if value in (None, "", "null", "undefined"):
        return None
    try:
        cover_id = int(value)
    except (TypeError, ValueError):
        return None
    return cover_id if cover_id > 0 else None


def _bytes_to_data_url(data: bytes, content_type: str) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


def _build_document_payload(data: dict) -> dict:
    ru_lines = normalize_lines(data.get("ru") or data.get("ru_lines"))
    en_lines = translate_lines(ru_lines)
    show_kcal = _to_bool(data.get("show_kcal", True))
    auto_format = _to_bool(data.get("auto_format", False))
    print_date = data.get("print_date") or ""
    background_name = data.get("background_name") or ""
    background_data = data.get("background_data") or ""
    background_bytes = None
    location_label = UNKNOWN_LOCATION_LABEL
    location_key = None
    cover_id = _parse_cover_id(data.get("cover_id"))

    if cover_id is not None:
        try:
            cover = get_cover(cover_id)
        except MenuCover.DoesNotExist as exc:
            raise ValueError("Подложка не найдена.") from exc
        background_bytes = read_cover_bytes(cover)
        background_data = _bytes_to_data_url(background_bytes, cover_content_type(cover))
        background_name = cover.original_filename
        location_label = cover.location_name
        location_key = cover.location_key
    else:
        # Custom local file (or no cover): archive as unknown location.
        location_label = UNKNOWN_LOCATION_LABEL
        location_key = "unknown_location"

    preview = build_preview(ru_lines, en_lines, show_kcal=show_kcal, auto_format=auto_format)
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


def _store_document(request, payload: dict) -> str:
    token = uuid4().hex
    docs = OrderedDict(request.session.get(SESSION_DOCUMENTS_KEY, {}))
    docs[token] = payload
    while len(docs) > SESSION_DOCUMENTS_LIMIT:
        docs.popitem(last=False)
    request.session[SESSION_DOCUMENTS_KEY] = dict(docs)
    request.session.modified = True
    return token


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


def _build_pdf_from_payload(payload: dict) -> bytes:
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


def _archive_pdf(request, pdf: bytes, payload: dict) -> None:
    """Persist PDF for archive. Failures are logged and do not block download."""
    try:
        save_menu_pdf_to_archive(
            pdf,
            print_date=payload.get("print_date") or "",
            ru_lines=payload.get("ru_lines"),
            background_name=payload.get("background_name") or "",
            location_key=payload.get("location_key"),
            location_label=payload.get("location_label"),
            user=getattr(request, "user", None),
        )
    except Exception:
        logger.exception("Failed to save menu PDF to archive")


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


@ensure_csrf_cookie
@login_required
def index(request):
    return render(request, "menu/index.html")


@ensure_csrf_cookie
@login_required
def editor(request):
    return render(request, "menu/editor.html", {"editor_config": {"translationEnabled": is_translation_configured()}})


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
        # Banquet column hidden until menu-type trigger is decided.
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
                "used_percent": round((status["used_bytes"] / status["total_bytes"]) * 100, 1)
                if status["total_bytes"]
                else 0,
                "archive_percent": round((status["archive_bytes"] / status["total_bytes"]) * 100, 1)
                if status["total_bytes"]
                else 0,
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
        return JsonResponse(_build_document_payload(_request_payload(request))["preview"])
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@login_required
@require_http_methods(["POST"])
def analyze_api(request):
    data = _request_payload(request)
    return JsonResponse({"decisions": analyze_pasted(data.get("text") or "")})


@login_required
@require_http_methods(["POST"])
def render_document_api(request):
    try:
        payload = _build_document_payload(_request_payload(request))
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    # Session JSON must stay serializable.
    payload.pop("background_bytes", None)
    token = _store_document(request, payload)
    return JsonResponse(
        {
            "token": token,
            "filename": payload["filename"],
            "print_url": reverse("menu:document_print", args=[token]),
        }
    )


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
            "background_data": payload.get("background_data") or "",
            "pages": _document_pages(payload),
        },
    )


@login_required
@require_http_methods(["POST"])
def pdf_api(request):
    try:
        payload = _build_document_payload(_request_payload(request))
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    try:
        pdf = _build_pdf_from_payload(payload)
    except Exception as exc:
        logger.exception("PDF generation failed hard: %s", exc)
        return JsonResponse({"error": "pdf_generation_failed"}, status=500)
    _archive_pdf(request, pdf, payload)
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
