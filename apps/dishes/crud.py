from django.db import IntegrityError, transaction
from django.db.models import Max, Q
from django.utils.dateparse import parse_datetime

from apps.core.text import normalize_ru

from .models import Dish, DishChangeLog


CAT_RU2EN = {
    "Салаты": "Salads",
    "Закуска": "Starters",
    "Горячая Закуска": "Hot Starters",
    "Холодная Закуска": "Cold Starters",
    "Супы": "Soups",
    "Горячее": "Main Courses",
    "Гарнир": "Side Dishes",
    "Завтрак": "Breakfast",
    "Шашлык": "BBQ",
}


def dish_to_dict(dish: Dish) -> dict:
    return {
        "id": dish.id,
        "ru": dish.name_ru,
        "en": dish.name_en,
        "kcal": dish.kcal_per_100,
        "gr": dish.grams_default,
        "catRu": dish.category_ru,
        "catEn": dish.category_en,
        "created_at": dish.created_at.isoformat() if dish.created_at else None,
        "updated_at": dish.updated_at.isoformat() if dish.updated_at else None,
    }


def base_revision() -> str:
    latest = Dish.objects.aggregate(value=Max("updated_at"))["value"]
    count = Dish.objects.count()
    return f"{count}:{latest.isoformat() if latest else 'empty'}"


def _parse_positive_int(value, default: int, *, minimum: int = 0, maximum: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if parsed < minimum:
        parsed = minimum
    if maximum is not None and parsed > maximum:
        parsed = maximum
    return parsed


def _parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def list_dishes_queryset(params):
    qs = Dish.objects.all()
    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(name_ru__icontains=q) | Q(name_en__icontains=q) | Q(category_ru__icontains=q))
    names_raw = (params.get("names") or "").strip()
    if names_raw:
        names = [item.strip() for item in names_raw.split("|") if item.strip()][:200]
        if names:
            qs = qs.filter(name_ru__in=names)
    if _parse_bool(params.get("missing_kcal")):
        qs = qs.filter(kcal_per_100__isnull=True)
    if _parse_bool(params.get("missing_gr")):
        qs = qs.filter(grams_default__isnull=True)
    if _parse_bool(params.get("missing_group")):
        qs = qs.filter(Q(category_ru="") | Q(category_ru__isnull=True) | Q(category_ru__iexact="Без группы"))
    date_from = parse_datetime(params.get("date_from") or "")
    date_to = parse_datetime(params.get("date_to") or "")
    if date_from:
        qs = qs.filter(updated_at__gte=date_from)
    if date_to:
        qs = qs.filter(updated_at__lte=date_to)
    return qs.order_by("name_ru", "id")


def list_dishes_page(params) -> dict:
    """Paginated dish list ordered by RU. Returns dishes + total/limit/offset."""
    qs = list_dishes_queryset(params)
    total = qs.count()
    limit = _parse_positive_int(params.get("limit"), 20, minimum=1, maximum=100)
    offset = _parse_positive_int(params.get("offset"), 0, minimum=0)
    if offset and offset >= total:
        offset = max(0, ((total - 1) // limit) * limit) if total else 0
    dishes = list(qs[offset : offset + limit])
    return {
        "dishes": dishes,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def parse_int_or_none(value):
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid integer") from exc
    if parsed < 0 or parsed > 32767:
        raise ValueError("integer out of range")
    return parsed


def _dish_update_payload(data: dict, *, partial: bool = False) -> dict:
    """Build update fields. partial=True keeps only keys present in the request."""
    if not isinstance(data, dict):
        raise ValueError("invalid payload")

    def has(*keys):
        return any(key in data for key in keys)

    payload = {}
    if not partial or has("en", "name_en"):
        payload["name_en"] = (data.get("en") or data.get("name_en") or "").strip()
        if len(payload["name_en"]) > 255:
            raise ValueError("name_en too long")
    if not partial or has("kcal", "kcal_per_100"):
        payload["kcal_per_100"] = parse_int_or_none(data.get("kcal", data.get("kcal_per_100")))
    if not partial or has("gr", "grams_default"):
        payload["grams_default"] = parse_int_or_none(data.get("gr", data.get("grams_default")))
    if not partial or has("catRu", "category_ru"):
        payload["category_ru"] = (data.get("catRu") or data.get("category_ru") or "").strip()
        if len(payload["category_ru"]) > 120:
            raise ValueError("category_ru too long")
    if not partial or has("catEn", "category_en"):
        payload["category_en"] = (data.get("catEn") or data.get("category_en") or "").strip()
        if len(payload["category_en"]) > 120:
            raise ValueError("category_en too long")
    if payload.get("category_ru") and not payload.get("category_en"):
        payload["category_en"] = CAT_RU2EN.get(payload["category_ru"], "")
    return payload


def _apply_dish_fields(dish: Dish, payload: dict, actor=None) -> None:
    """Shared setattr of payload fields + updated_by (used by upsert and update)."""
    for key, value in payload.items():
        setattr(dish, key, value)
    dish.updated_by = actor if getattr(actor, "is_authenticated", False) else None


def find_dish_by_ru_name(name_ru: str, *, exclude_id: int | None = None) -> Dish | None:
    norm = normalize_ru(name_ru)
    if not norm:
        return None

    qs = Dish.objects.all()
    if exclude_id is not None:
        qs = qs.exclude(id=exclude_id)

    dish = qs.filter(name_ru_norm=norm).first()
    if dish:
        return dish

    for candidate in qs.only("id", "name_ru", "name_ru_norm"):
        if normalize_ru(candidate.name_ru) == norm:
            return candidate
    return None


def upsert_dish(data: dict, actor=None) -> tuple[Dish, bool]:
    name_ru = (data.get("ru") or data.get("name_ru") or "").strip()
    if not name_ru:
        raise ValueError("name_ru required")
    payload = _dish_update_payload(data)

    with transaction.atomic():
        dish = find_dish_by_ru_name(name_ru)
        created = dish is None
        if created:
            dish = Dish(name_ru=name_ru, created_by=actor if getattr(actor, "is_authenticated", False) else None)
        _apply_dish_fields(dish, payload, actor)
        try:
            dish.save()
        except IntegrityError as exc:
            raise ValueError("блюдо уже существует") from exc
        DishChangeLog.objects.create(
            dish=dish,
            dish_id_snapshot=dish.id,
            name_ru_snapshot=dish.name_ru,
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            action=DishChangeLog.ACTION_CREATE if created else DishChangeLog.ACTION_UPDATE,
            changed_fields=payload,
        )
    return dish, created


def update_dish(dish: Dish, data: dict, actor=None) -> Dish:
    name_ru = dish.name_ru
    if "ru" in data or "name_ru" in data:
        name_ru = (data.get("ru") or data.get("name_ru") or "").strip()
    if not name_ru:
        raise ValueError("name_ru required")
    if len(name_ru) > 255:
        raise ValueError("name_ru too long")
    payload = _dish_update_payload(data, partial=True)

    with transaction.atomic():
        duplicate = find_dish_by_ru_name(name_ru, exclude_id=dish.id)
        if duplicate:
            raise ValueError("duplicate ru name")

        dish.name_ru = name_ru
        _apply_dish_fields(dish, payload, actor)
        try:
            dish.save()
        except IntegrityError as exc:
            raise ValueError("блюдо уже существует") from exc
        DishChangeLog.objects.create(
            dish=dish,
            dish_id_snapshot=dish.id,
            name_ru_snapshot=dish.name_ru,
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            action=DishChangeLog.ACTION_UPDATE,
            changed_fields=payload | {"name_ru": name_ru},
        )
    return dish


def delete_dish(dish: Dish, actor=None) -> None:
    DishChangeLog.objects.create(
        dish=dish,
        dish_id_snapshot=dish.id,
        name_ru_snapshot=dish.name_ru,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=DishChangeLog.ACTION_DELETE,
        changed_fields={},
    )
    dish.delete()
