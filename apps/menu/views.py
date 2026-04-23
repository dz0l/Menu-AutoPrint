import json
import logging

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from apps.dishes.services import analyze_pasted
from apps.pdf.services import build_menu_pdf

from .services import build_preview, normalize_lines, translate_lines


logger = logging.getLogger(__name__)


def _json_body(request) -> dict:
    if not request.body:
        return {}
    return json.loads(request.body.decode("utf-8"))


@ensure_csrf_cookie
def index(request):
    return render(request, "menu/index.html")


@ensure_csrf_cookie
def editor(request):
    return render(request, "menu/editor.html")


@require_http_methods(["POST"])
def preview_api(request):
    data = _json_body(request)
    ru_lines = normalize_lines(data.get("ru") or data.get("ru_lines"))
    en_lines = normalize_lines(data.get("en") or data.get("en_lines"))
    if not en_lines:
        en_lines = translate_lines(ru_lines)
    return JsonResponse(build_preview(ru_lines, en_lines, show_kcal=data.get("show_kcal", True)))


@require_http_methods(["POST"])
def analyze_api(request):
    data = _json_body(request)
    return JsonResponse({"decisions": analyze_pasted(data.get("text") or "")})


@require_http_methods(["POST"])
def pdf_api(request):
    data = _json_body(request)
    ru_lines = normalize_lines(data.get("ru") or data.get("ru_lines"))
    en_lines = normalize_lines(data.get("en") or data.get("en_lines")) or translate_lines(ru_lines)
    preview = build_preview(ru_lines, en_lines, show_kcal=data.get("show_kcal", True))
    context = {
        "preview": preview,
        "print_date": data.get("print_date") or "",
        "title": data.get("title") or "menu",
    }
    html = render_to_string("menu/print.html", context)

    try:
        pdf = build_menu_pdf(
            html=html,
            base_url=request.build_absolute_uri("/"),
            preview=preview,
            print_date=context["print_date"],
        )
    except Exception as exc:
        logger.exception("PDF generation failed hard: %s", exc)
        return JsonResponse({"error": "pdf_generation_failed"}, status=500)

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="menu.pdf"'
    return response
