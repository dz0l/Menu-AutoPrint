import json

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from apps.dishes.services import analyze_pasted

from .services import build_preview, normalize_lines, translate_lines


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
    context = {
        "preview": build_preview(ru_lines, en_lines, show_kcal=data.get("show_kcal", True)),
        "print_date": data.get("print_date") or "",
        "title": data.get("title") or "menu",
    }
    html = render_to_string("menu/print.html", context)
    try:
        from weasyprint import HTML
    except Exception:
        return HttpResponse(html, content_type="text/html; charset=utf-8")
    pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="menu.pdf"'
    return response
