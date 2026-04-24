import json
import logging
import re
import unicodedata
from collections import OrderedDict
from uuid import uuid4
from urllib.parse import quote

from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from apps.dishes.services import analyze_pasted
from apps.pdf.services import FOOTER_NOTE, build_download_filename, build_menu_pdf, format_print_date

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
    print_date = data.get("print_date") or ""
    background_name = data.get("background_name") or ""
    background_data = data.get("background_data") or ""
    preview = build_preview(ru_lines, en_lines, show_kcal=show_kcal)
    filename = build_download_filename(print_date, background_name)
    return {
        "preview": preview,
        "show_kcal": show_kcal,
        "print_date": print_date,
        "display_date": format_print_date(print_date),
        "background_name": background_name,
        "background_data": background_data,
        "filename": filename,
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
    )


@ensure_csrf_cookie
def index(request):
    return render(request, "menu/index.html")


@ensure_csrf_cookie
def editor(request):
    return render(request, "menu/editor.html")


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
            "pdf_url": reverse("menu:document_pdf", args=[token]),
            "pdf_download_url": f"{reverse('menu:document_pdf', args=[token])}?download=1",
        }
    )


def document_preview_page(request, token: str):
    payload = _get_document(request, token)
    pages = [
        {"label": "RU", "items": payload["preview"].get("ru") or []},
        {"label": "EN", "items": payload["preview"].get("en") or []},
    ]
    return render(
        request,
        "menu/document_preview.html",
        {
            "token": token,
            "filename": payload["filename"],
            "display_date": payload["display_date"],
            "show_kcal": payload["show_kcal"],
            "background_data": payload.get("background_data") or "",
            "footer_note": FOOTER_NOTE,
            "pdf_url": reverse("menu:document_pdf", args=[token]),
            "pdf_download_url": f"{reverse('menu:document_pdf', args=[token])}?download=1",
            "pages": pages,
        },
    )


def document_pdf_page(request, token: str):
    payload = _get_document(request, token)
    try:
        pdf = _build_pdf_from_payload(payload)
    except Exception as exc:
        logger.exception("Token PDF generation failed hard: %s", exc)
        return JsonResponse({"error": "pdf_generation_failed"}, status=500)
    return _pdf_response(pdf, payload["filename"], download=_to_bool(request.GET.get("download")))


@require_http_methods(["POST"])
def pdf_api(request):
    payload = _build_document_payload(_request_payload(request))
    try:
        pdf = _build_pdf_from_payload(payload)
    except Exception as exc:
        logger.exception("PDF generation failed hard: %s", exc)
        return JsonResponse({"error": "pdf_generation_failed"}, status=500)
    return _pdf_response(pdf, payload["filename"])
