from __future__ import annotations

from django.db import IntegrityError, transaction

from apps.dishes.crud import (
    CAT_RU2EN,
    _apply_dish_fields,
    _dish_update_payload,
    find_dish_by_ru_name,
    parse_int_or_none,
)
from apps.dishes.models import Dish, DishChangeLog

from .menu_check import dish_version, missing_fields_for


class IntegrationConflict(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class IntegrationBadRequest(Exception):
    def __init__(self, code: str, message: str, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or []


def create_dish_only(data: dict, actor) -> Dish:
    if not isinstance(data, dict):
        raise IntegrationBadRequest("invalid_request", "JSON object required.")
    forbidden = {"id", "created_by", "updated_by", "name_ru_norm"}
    if forbidden.intersection(data):
        raise IntegrationBadRequest("invalid_request", "Unsupported fields.")
    ru = data.get("ru")
    if not isinstance(ru, str) or not ru.strip():
        raise IntegrationBadRequest("invalid_request", "ru required.")
    name_ru = ru.strip()
    if len(name_ru) > 255:
        raise IntegrationBadRequest("invalid_request", "ru too long.")

    cat_ru = data.get("catRu")
    if cat_ru is None:
        cat_ru = ""
    if not isinstance(cat_ru, str):
        raise IntegrationBadRequest("invalid_request", "catRu must be a string.")
    cat_ru = cat_ru.strip()
    if cat_ru and cat_ru not in CAT_RU2EN:
        raise IntegrationBadRequest("invalid_request", "Unknown category.")

    payload_src = {
        "en": data.get("en", ""),
        "gr": data.get("gr"),
        "kcal": data.get("kcal"),
        "catRu": cat_ru,
    }
    try:
        payload = _dish_update_payload(payload_src)
    except ValueError as exc:
        raise IntegrationBadRequest("invalid_request", str(exc)) from exc
    if cat_ru:
        payload["category_en"] = CAT_RU2EN[cat_ru]
    else:
        payload["category_en"] = ""

    with transaction.atomic():
        if find_dish_by_ru_name(name_ru) is not None:
            raise IntegrationConflict("dish_exists", "Dish already exists.")
        dish = Dish(name_ru=name_ru, created_by=actor)
        _apply_dish_fields(dish, payload, actor)
        try:
            dish.save()
        except IntegrityError as exc:
            raise IntegrationConflict("dish_exists", "Dish already exists.") from exc
        DishChangeLog.objects.create(
            dish=dish,
            dish_id_snapshot=dish.id,
            name_ru_snapshot=dish.name_ru,
            actor=actor,
            action=DishChangeLog.ACTION_CREATE,
            changed_fields=payload,
        )
    return dish


def fill_missing_fields(dish_id: int, data: dict, actor, *, show_kcal: bool = True) -> Dish:
    if not isinstance(data, dict):
        raise IntegrationBadRequest("invalid_request", "JSON object required.")
    expected_version = data.get("version")
    if not isinstance(expected_version, str) or not expected_version:
        raise IntegrationBadRequest("invalid_request", "version required.")

    allowed_keys = {"version", "en", "gr", "kcal", "catRu"}
    unknown = set(data) - allowed_keys
    if unknown:
        raise IntegrationBadRequest("invalid_request", "Unsupported fields.", details=sorted(unknown))

    with transaction.atomic():
        try:
            dish = Dish.objects.select_for_update().get(pk=dish_id)
        except Dish.DoesNotExist as exc:
            raise IntegrationBadRequest("not_found", "Dish not found.") from exc

        if dish_version(dish) != expected_version:
            raise IntegrationConflict("version_conflict", "Dish was changed.")

        allowed_missing = set(missing_fields_for(dish, show_kcal=True))
        # Category fill is optional even when not required for print.
        if not (dish.category_ru or "").strip():
            allowed_missing.add("catRu")

        updates = {}
        if "en" in data:
            if "en" not in allowed_missing:
                raise IntegrationConflict("field_filled", "Field en is already set.")
            if not isinstance(data["en"], str):
                raise IntegrationBadRequest("invalid_request", "en must be a string.")
            value = data["en"].strip()
            if len(value) > 255:
                raise IntegrationBadRequest("invalid_request", "en too long.")
            updates["name_en"] = value
        if "gr" in data:
            if "gr" not in allowed_missing:
                raise IntegrationConflict("field_filled", "Field gr is already set.")
            try:
                updates["grams_default"] = parse_int_or_none(data["gr"])
            except ValueError as exc:
                raise IntegrationBadRequest("invalid_request", "invalid gr") from exc
        if "kcal" in data:
            if "kcal" not in allowed_missing:
                raise IntegrationConflict("field_filled", "Field kcal is already set.")
            try:
                updates["kcal_per_100"] = parse_int_or_none(data["kcal"])
            except ValueError as exc:
                raise IntegrationBadRequest("invalid_request", "invalid kcal") from exc
        if "catRu" in data:
            if "catRu" not in allowed_missing:
                raise IntegrationConflict("field_filled", "Field catRu is already set.")
            if not isinstance(data["catRu"], str):
                raise IntegrationBadRequest("invalid_request", "catRu must be a string.")
            cat_ru = data["catRu"].strip()
            if cat_ru and cat_ru not in CAT_RU2EN:
                raise IntegrationBadRequest("invalid_request", "Unknown category.")
            updates["category_ru"] = cat_ru
            updates["category_en"] = CAT_RU2EN.get(cat_ru, "")

        if not updates:
            raise IntegrationBadRequest("invalid_request", "No fields to update.")

        _apply_dish_fields(dish, updates, actor)
        dish.save()
        DishChangeLog.objects.create(
            dish=dish,
            dish_id_snapshot=dish.id,
            name_ru_snapshot=dish.name_ru,
            actor=actor,
            action=DishChangeLog.ACTION_UPDATE,
            changed_fields=updates,
        )
    return dish
