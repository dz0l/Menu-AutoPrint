import json

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from .models import Dish
from .services import (
    base_revision,
    check_missing_fixables,
    delete_dish,
    dish_to_dict,
    duplicate_groups,
    export_dishes_csv,
    find_dish_by_ru_name,
    import_dishes_csv,
    list_dishes,
    suggest,
    update_dish,
    upsert_dish,
)


def _json_body(request) -> dict:
    if not request.body:
        return {}
    return json.loads(request.body.decode("utf-8"))


def _editor_required(request):
    return request.user.is_authenticated and request.user.is_active


@require_http_methods(["GET", "POST"])
def dishes(request):
    if request.method == "GET":
        items = [dish_to_dict(dish) for dish in list_dishes(request.GET)]
        return JsonResponse({"revision": base_revision(), "dishes": items})

    if not _editor_required(request):
        return JsonResponse({"error": "forbidden"}, status=403)
    try:
        dish, created = upsert_dish(_json_body(request), request.user)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse(dish_to_dict(dish), status=201 if created else 200)


@require_http_methods(["PATCH", "DELETE"])
def dish_detail(request, dish_id):
    if not _editor_required(request):
        return JsonResponse({"error": "forbidden"}, status=403)
    dish = get_object_or_404(Dish, id=dish_id)
    if request.method == "DELETE":
        delete_dish(dish, request.user)
        return JsonResponse({"deleted": True})
    data = _json_body(request)
    try:
        updated = update_dish(dish, data, request.user)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse(dish_to_dict(updated))


@require_http_methods(["GET"])
def suggest_view(request):
    return JsonResponse({"items": suggest(request.GET.get("q", ""), request.GET.get("lang", "ru"))})


@require_http_methods(["GET"])
def names_view(request):
    lang = request.GET.get("lang", "ru")
    field = "name_en" if lang == "en" else "name_ru"
    items = list(
        Dish.objects.exclude(**{field: ""})
        .order_by(field)
        .values_list(field, flat=True)[:5000]
    )
    return JsonResponse({"items": items})


def _rate_limited(request) -> bool:
    ident = request.user.id if request.user.is_authenticated else request.META.get("REMOTE_ADDR", "unknown")
    key = f"export-csv:{ident}"
    count = cache.get(key, 0)
    if count >= settings.EXPORT_RATE_LIMIT_PER_MINUTE:
        return True
    cache.set(key, count + 1, 60)
    return False


@require_http_methods(["GET"])
def export_csv(request):
    if _rate_limited(request):
        return JsonResponse({"error": "rate limit"}, status=429)
    response = HttpResponse(export_dishes_csv(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="calories.csv"'
    return response


@require_http_methods(["POST"])
def import_csv(request):
    if not _editor_required(request):
        return JsonResponse({"error": "forbidden"}, status=403)
    uploaded = request.FILES.get("file")
    text = uploaded.read().decode("utf-8-sig") if uploaded else request.body.decode("utf-8-sig")
    result = import_dishes_csv(text, request.user, dry_run=request.GET.get("dry_run") == "1")
    return JsonResponse(result.__dict__)


@require_http_methods(["POST"])
def bulk_upsert(request):
    if not _editor_required(request):
        return JsonResponse({"error": "forbidden"}, status=403)
    payload = _json_body(request)
    rows = payload.get("rows", [])
    delete_ids = payload.get("delete_ids", [])
    result = {"created": 0, "updated": 0, "deleted": 0, "errors": []}

    for index, dish_id in enumerate(delete_ids):
        try:
            dish = Dish.objects.get(id=dish_id)
            delete_dish(dish, request.user)
            result["deleted"] += 1
        except Dish.DoesNotExist:
            result["errors"].append({"delete_index": index, "error": "dish not found"})
        except Exception as exc:
            result["errors"].append({"delete_index": index, "error": str(exc)})

    for index, row in enumerate(rows):
        try:
            if row.get("id"):
                dish = Dish.objects.get(id=row["id"])
                update_dish(dish, row, request.user)
                result["updated"] += 1
            else:
                if find_dish_by_ru_name(row.get("ru") or row.get("name_ru") or ""):
                    raise ValueError("duplicate ru name")
                _, created = upsert_dish(row, request.user)
                result["created" if created else "updated"] += 1
        except Exception as exc:
            result["errors"].append({"index": index, "error": str(exc)})
    result["duplicates"] = duplicate_groups(rows)
    return JsonResponse(result)


@require_http_methods(["POST"])
def check_missing_fixables_view(request):
    payload = _json_body(request)
    lines = payload.get("ru_lines") or payload.get("lines") or []
    return JsonResponse(check_missing_fixables(lines))
