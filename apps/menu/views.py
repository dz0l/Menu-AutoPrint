import json
import logging
import re
import unicodedata
from collections import OrderedDict
from uuid import uuid4
from urllib.parse import quote

from django.http import Http404, HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
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
from .models import MenuArchiveEntry
from apps.pdf.services import FOOTER_NOTE_EN, FOOTER_NOTE_RU, build_download_filename, build_menu_pdf, format_print_date

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


def _build_document_payload(data: dict) -> dict:
    ru_lines = normalize_lines(data.get("ru") or data.get("ru_lines"))
    en_lines = translate_lines(ru_lines)
    show_kcal = _to_bool(data.get("show_kcal", True))
    auto_format = _to_bool(data.get("auto_format", False))
    print_date = data.get("print_date") or ""
    background_name = data.get("background_name") or ""
    background_data = data.get("background_data") or ""
    preview = build_preview(ru_lines, en_lines, show_kcal=show_kcal, auto_format=auto_format)
    filename = build_download_filename(print_date, background_name, ru_lines=ru_lines)
    return {
        "preview": preview,
        "show_kcal": show_kcal,
        "auto_format": auto_format,
        "print_date": print_date,
        "display_date": format_print_date(print_date),
        "background_name": background_name,
        "background_data": background_data,
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
        {"key": MenuArchiveEntry.MenuType.BANQUET, "label": MENU_TYPE_LABELS[MenuArchiveEntry.MenuType.BANQUET]},
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
                "display_date": raw["display_date"],
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
    label = MENU_TYPE_LABELS.get(entry.menu_type, entry.menu_type)
    filename = f"{entry.menu_date.strftime('%d.%m.%Y')} - {label}.pdf"
    pdf = path.read_bytes()
    return _pdf_response(pdf, filename, download=True)


@require_http_methods(["POST"])
def preview_api(request):
    data = _request_payload(request)
    return JsonResponse(_build_document_payload(data)["preview"])


@require_http_methods(["POST"])
def analyze_api(request):
    data = _request_payload(request)
    return JsonResponse({"decisions": analyze_pasted(data.get("text") or "")})


@require_http_methods(["POST"])
def render_document_api(request):
    payload = _build_document_payload(_request_payload(request))
    token = _store_document(request, payload)
    return JsonResponse(
        {
            "token": token,
            "filename": payload["filename"],
            "preview_url": reverse("menu:document_preview", args=[token]),
            "print_url": reverse("menu:document_print", args=[token]),
            "pdf_url": reverse("menu:document_pdf", args=[token]),
            "pdf_download_url": f"{reverse('menu:document_pdf', args=[token])}?download=1",
        }
    )


def document_preview_page(request, token: str):
    payload = _get_document(request, token)
    return render(
        request,
        "menu/document_preview.html",
        {
            "token": token,
            "filename": payload["filename"],
            "display_date": payload["display_date"],
            "show_kcal": payload["show_kcal"],
            "background_data": payload.get("background_data") or "",
            "pdf_url": reverse("menu:document_pdf", args=[token]),
            "pdf_download_url": f"{reverse('menu:document_pdf', args=[token])}?download=1",
            "pages": _document_pages(payload),
        },
    )


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


def document_pdf_page(request, token: str):
    payload = _get_document(request, token)
    try:
        pdf = _build_pdf_from_payload(payload)
    except Exception as exc:
        logger.exception("Token PDF generation failed hard: %s", exc)
        return JsonResponse({"error": "pdf_generation_failed"}, status=500)
    _archive_pdf(request, pdf, payload)
    return _pdf_response(pdf, payload["filename"], download=_to_bool(request.GET.get("download")))


@require_http_methods(["POST"])
def pdf_api(request):
    payload = _build_document_payload(_request_payload(request))
    try:
        pdf = _build_pdf_from_payload(payload)
    except Exception as exc:
        logger.exception("PDF generation failed hard: %s", exc)
        return JsonResponse({"error": "pdf_generation_failed"}, status=500)
    _archive_pdf(request, pdf, payload)
    return _pdf_response(pdf, payload["filename"])
