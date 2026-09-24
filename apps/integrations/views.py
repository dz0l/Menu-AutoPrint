from __future__ import annotations

import logging
from urllib.parse import quote

from django.conf import settings
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from apps.dishes.crud import CAT_RU2EN, dish_to_dict
from apps.dishes.matching import analyze_pasted
from apps.dishes.models import Dish
from apps.menu.covers import cover_absolute_path, cover_content_type, list_covers, serialize_cover
from apps.menu.document import archive_pdf_for_user, build_document_payload, build_pdf_from_payload
from apps.menu.models import MenuCover
from apps.menu.services import dish_maps

from .auth import CONTRACT_VERSION, integration_endpoint, integration_error
from .dishes import IntegrationBadRequest, IntegrationConflict, create_dish_only, fill_missing_fields
from .menu_check import check_menu, dish_version, suggest_with_ids
from .models import IntegrationOperation
from .operations import (
    IntegrationOperationConflict,
    begin_operation,
    mark_failed,
    mark_succeeded,
    read_operation_pdf,
)

logger = logging.getLogger(__name__)


def _strict_bool(value, *, field: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"{field} must be boolean")


def _require_idempotency_key(request) -> str | None:
    key = (request.headers.get("Idempotency-Key") or request.META.get("HTTP_IDEMPOTENCY_KEY") or "").strip()
    if not key:
        return None
    if len(key) > 128:
        raise ValueError("Idempotency-Key too long")
    return key


def _pdf_response(pdf: bytes, filename: str, *, request_id: str) -> HttpResponse:
    response = HttpResponse(pdf, content_type="application/pdf")
    ascii_name = "".join(ch for ch in filename if ch.isascii() and ch not in '"\\') or "menu.pdf"
    response["Content-Disposition"] = (
        f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
    )
    response["X-Request-Id"] = request_id
    return response


@integration_endpoint
@require_http_methods(["GET"])
def capabilities(request):
    return JsonResponse(
        {
            "contract_version": CONTRACT_VERSION,
            "features": {
                "menu_check": True,
                "menu_analyze": True,
                "menu_pdf": True,
                "dish_create": True,
                "dish_fill_missing": True,
                "covers": True,
                "suggest": True,
                "categories": True,
                "operations": True,
                "preview": False,
                "azure_translate": False,
            },
        }
    )


@integration_endpoint
@require_http_methods(["GET"])
def dishes_suggest(request):
    q = (request.GET.get("q") or "").strip()
    try:
        limit = int(request.GET.get("limit") or 12)
    except (TypeError, ValueError):
        limit = 12
    limit = max(1, min(limit, 30))
    return JsonResponse({"items": suggest_with_ids(q, limit=limit)})


@integration_endpoint
@require_http_methods(["GET"])
def categories(request):
    items = [{"catRu": ru, "catEn": en} for ru, en in CAT_RU2EN.items()]
    return JsonResponse({"items": items})


@integration_endpoint
@require_http_methods(["POST"])
def menu_check(request):
    try:
        data = _json(request)
        show_kcal = True
        if "show_kcal" in data:
            show_kcal = _strict_bool(data.get("show_kcal"), field="show_kcal")
        ru = data.get("ru")
        if not isinstance(ru, str):
            return integration_error(400, "invalid_request", "ru must be a string.")
    except ValueError as exc:
        return integration_error(400, "invalid_request", str(exc))
    return JsonResponse(check_menu(ru, show_kcal=show_kcal))


@integration_endpoint
@require_http_methods(["POST"])
def menu_analyze(request):
    """Same matching as web `/api/menu/analyze` (auto / review / unknown)."""
    try:
        data = _json(request)
        text = data.get("text")
        if not isinstance(text, str):
            return integration_error(400, "invalid_request", "text must be a string.")
    except ValueError as exc:
        return integration_error(400, "invalid_request", str(exc))
    return JsonResponse({"decisions": analyze_pasted(text)})


@integration_endpoint
@require_http_methods(["GET"])
def dish_detail(request, dish_id: int):
    dish = get_object_or_404(Dish, pk=dish_id)
    body = dish_to_dict(dish)
    body["version"] = dish_version(dish)
    return JsonResponse(body)


@integration_endpoint
@require_http_methods(["POST"])
def dishes_create(request):
    try:
        data = _json(request)
        key = _require_idempotency_key(request)
        if not key:
            return integration_error(400, "invalid_request", "Idempotency-Key required.")
        op, replay = begin_operation(
            scope="default",
            kind=IntegrationOperation.KIND_CREATE_DISH,
            idempotency_key=key,
            payload=data,
        )
    except ValueError as exc:
        return integration_error(400, "invalid_request", str(exc))
    except IntegrationOperationConflict as exc:
        return integration_error(409, exc.code, exc.message)

    if replay:
        if op.status == IntegrationOperation.STATUS_SUCCEEDED:
            return JsonResponse(op.result_json, status=201)
        if op.status == IntegrationOperation.STATUS_FAILED:
            return integration_error(op.http_status or 400, op.error_code or "failed", op.error_message or "failed", request_id=op.request_id)
        return integration_error(409, "operation_pending", "Operation is still pending.", request_id=op.request_id)

    try:
        dish = create_dish_only(data, request.integration_user)
        body = dish_to_dict(dish)
        body["version"] = dish_version(dish)
        mark_succeeded(op, result_json=body)
        response = JsonResponse(body, status=201)
        response["X-Request-Id"] = op.request_id
        return response
    except IntegrationConflict as exc:
        mark_failed(op, http_status=409, code=exc.code, message=exc.message)
        return integration_error(409, exc.code, exc.message, request_id=op.request_id)
    except IntegrationBadRequest as exc:
        status = 404 if exc.code == "not_found" else 400
        mark_failed(op, http_status=status, code=exc.code, message=exc.message)
        return integration_error(status, exc.code, exc.message, details=exc.details, request_id=op.request_id)
    except Exception:
        logger.exception("integration create dish failed")
        mark_failed(op, http_status=503, code="unavailable", message="Temporary failure.")
        return integration_error(503, "unavailable", "Temporary failure.", request_id=op.request_id)


@integration_endpoint
@require_http_methods(["PATCH"])
def dishes_fill_missing(request, dish_id: int):
    try:
        data = _json(request)
        dish = fill_missing_fields(dish_id, data, request.integration_user)
        body = dish_to_dict(dish)
        body["version"] = dish_version(dish)
        return JsonResponse(body)
    except IntegrationConflict as exc:
        return integration_error(409, exc.code, exc.message)
    except IntegrationBadRequest as exc:
        status = 404 if exc.code == "not_found" else 400
        return integration_error(status, exc.code, exc.message, details=exc.details)
    except ValueError as exc:
        return integration_error(400, "invalid_request", str(exc))


@integration_endpoint
@require_http_methods(["GET"])
def covers_list(request):
    return JsonResponse({"items": [serialize_cover(item) for item in list_covers()]})


@integration_endpoint
@require_http_methods(["GET"])
def cover_image(request, cover_id: int):
    cover = get_object_or_404(MenuCover, pk=cover_id)
    path = cover_absolute_path(cover.relative_path)
    if not path.is_file():
        return integration_error(404, "not_found", "Cover file not found.")
    return FileResponse(path.open("rb"), content_type=cover_content_type(cover))


@integration_endpoint
@require_http_methods(["POST"])
def menu_pdf(request):
    try:
        data = _json(request)
        key = _require_idempotency_key(request)
        if not key:
            return integration_error(400, "invalid_request", "Idempotency-Key required.")
        if "show_kcal" not in data or not isinstance(data.get("show_kcal"), bool):
            return integration_error(400, "invalid_request", "show_kcal must be boolean.")
        if "auto_format" not in data or not isinstance(data.get("auto_format"), bool):
            return integration_error(400, "invalid_request", "auto_format must be boolean.")
        if not isinstance(data.get("ru"), str):
            return integration_error(400, "invalid_request", "ru must be a string.")
        if not isinstance(data.get("print_date"), str) or not data.get("print_date"):
            return integration_error(400, "invalid_request", "print_date required.")
        if not isinstance(data.get("cover_id"), int) or data.get("cover_id") < 1:
            return integration_error(400, "invalid_request", "cover_id must be a positive integer.")
        op, replay = begin_operation(
            scope="default",
            kind=IntegrationOperation.KIND_PDF,
            idempotency_key=key,
            payload=data,
        )
    except ValueError as exc:
        return integration_error(400, "invalid_request", str(exc))
    except IntegrationOperationConflict as exc:
        return integration_error(409, exc.code, exc.message)

    if replay:
        if op.status == IntegrationOperation.STATUS_SUCCEEDED:
            pdf = read_operation_pdf(op)
            if pdf is None:
                return integration_error(503, "unavailable", "Stored PDF is missing.", request_id=op.request_id)
            return _pdf_response(pdf, op.result_json.get("filename") or "menu.pdf", request_id=op.request_id)
        if op.status == IntegrationOperation.STATUS_FAILED:
            return integration_error(
                op.http_status or 422,
                op.error_code or "failed",
                op.error_message or "failed",
                request_id=op.request_id,
            )
        return integration_error(409, "operation_pending", "Operation is still pending.", request_id=op.request_id)

    try:
        # One catalog snapshot for check + translate + preview (W-04).
        catalog = dish_maps()
        result = check_menu(data["ru"], show_kcal=data["show_kcal"], dishes=catalog)
        if not result["ready"]:
            mark_failed(op, http_status=422, code="menu_incomplete", message="Заполните данные блюд.")
            return integration_error(
                422,
                "menu_incomplete",
                "Заполните данные блюд.",
                details=result.get("issues") or [],
                request_id=op.request_id,
            )
        payload = build_document_payload(
            data,
            require_cover=True,
            require_print_date=True,
            dishes=catalog,
        )
        # Re-check types for strict path: show_kcal/auto_format already validated.
        payload["show_kcal"] = data["show_kcal"]
        payload["auto_format"] = data["auto_format"]
        pdf = build_pdf_from_payload(payload)
        # Persist PDF result before archive side-effect so replay can return the file.
        mark_succeeded(op, result_json={"filename": payload["filename"]}, pdf=pdf, filename=payload["filename"])
        try:
            archive_pdf_for_user(request.integration_user, pdf, payload)
        except ValueError as exc:
            logger.exception(
                "integration pdf archive failed after mark_succeeded request_id=%s stage=archive",
                op.request_id,
            )
            return integration_error(
                503,
                "archive_failed",
                f"PDF сохранён для повтора по ключу, архив не записан: {exc}",
                request_id=op.request_id,
            )
        return _pdf_response(pdf, payload["filename"], request_id=op.request_id)
    except ValueError as exc:
        message = str(exc)
        code = "menu_overflow" if "не помещается" in message.lower() else "invalid_request"
        status = 422 if code == "menu_overflow" else 400
        if "Подложка" in message or "подложк" in message:
            status = 404 if "не найдена" in message or "отсутствует" in message else 400
            code = "cover_missing" if status == 404 else "invalid_request"
        mark_failed(op, http_status=status, code=code, message=message)
        return integration_error(status, code, message, request_id=op.request_id)
    except Exception:
        logger.exception("integration pdf failed stage=generate")
        mark_failed(op, http_status=503, code="unavailable", message="Temporary failure.")
        return integration_error(503, "unavailable", "Temporary failure.", request_id=op.request_id)


@integration_endpoint
@require_http_methods(["GET"])
def operation_status(request, request_id: str):
    try:
        op = IntegrationOperation.objects.get(request_id=request_id)
    except IntegrationOperation.DoesNotExist:
        return integration_error(404, "not_found", "Operation not found.")
    body = {
        "request_id": op.request_id,
        "kind": op.kind,
        "status": op.status,
        "result": op.result_json,
        "error": {"code": op.error_code, "message": op.error_message} if op.error_code else None,
        "expires_at": op.expires_at.isoformat() if op.expires_at else None,
    }
    return JsonResponse(body)


def _json(request) -> dict:
    from apps.core.http_utils import json_body

    return json_body(request)
