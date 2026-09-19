from dataclasses import dataclass

from django.db import transaction

from apps.core.text import normalize_ru

from .crud import CAT_RU2EN, dish_to_dict, parse_int_or_none, upsert_dish
from .csv_io import HEADERS, parse_csv_semicolon, to_csv_semicolon
from .matching import find_similar_dishes
from .models import Dish, DishChangeLog


def export_dishes_csv() -> str:
    rows = [
        [
            dish.name_ru,
            dish.name_en,
            dish.kcal_per_100 if dish.kcal_per_100 is not None else "",
            dish.category_ru,
            dish.category_en,
            dish.grams_default if dish.grams_default is not None else "",
        ]
        for dish in Dish.objects.order_by("name_ru")
    ]
    return to_csv_semicolon(rows, HEADERS)


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[dict] | None = None


@dataclass
class ImportReviewResult:
    create_candidates: list[dict]
    exact_matches: list[dict]
    changed_matches: list[dict]
    similar_matches: list[dict]
    skipped: list[dict]
    errors: list[dict]


def import_dishes_csv(text: str, actor=None, dry_run=False) -> ImportResult:
    result = ImportResult(errors=[])
    rows = parse_csv_semicolon(text)
    with transaction.atomic():
        for index, row in enumerate(rows, start=1):
            ru, en, kcal, cat_ru, cat_en, gr = row
            if not ru:
                result.skipped += 1
                continue
            try:
                _, created = upsert_dish({"ru": ru, "en": en, "kcal": kcal, "catRu": cat_ru, "catEn": cat_en, "gr": gr}, actor)
                if created:
                    result.created += 1
                else:
                    result.updated += 1
            except Exception as exc:
                result.errors.append({"row": index, "error": str(exc)})
        if dry_run:
            transaction.set_rollback(True)
    return result


def review_dishes_csv_import(text: str, progress=None) -> ImportReviewResult:
    rows = parse_csv_semicolon(text)
    dishes = list(Dish.objects.all())
    by_norm = {normalize_ru(dish.name_ru): dish for dish in dishes}
    total = len(rows)

    result = ImportReviewResult(
        create_candidates=[],
        exact_matches=[],
        changed_matches=[],
        similar_matches=[],
        skipped=[],
        errors=[],
    )

    for index, row in enumerate(rows, start=1):
        if progress:
            progress(index, total, "review")
        try:
            incoming = _csv_row_to_payload(row)
        except Exception as exc:
            result.errors.append({"row": index, "error": str(exc)})
            continue

        if not incoming["ru"]:
            result.skipped.append({"row": index, "reason": "empty name"})
            continue

        norm = normalize_ru(incoming["ru"])
        existing = by_norm.get(norm)
        if existing:
            changed = _dish_field_changes(existing, incoming)
            payload = {
                "row": index,
                "incoming": incoming,
                "existing": dish_to_dict(existing),
            }
            if changed:
                payload["changed_fields"] = changed
                result.changed_matches.append(payload)
            else:
                result.exact_matches.append(payload)
            continue

        suggestions = find_similar_dishes(incoming["ru"], limit=3, threshold=0.82)
        payload = {"row": index, "incoming": incoming, "suggestions": suggestions}
        if suggestions:
            result.similar_matches.append(payload)
        else:
            result.create_candidates.append(payload)

    if progress and total:
        progress(total, total, "review")
    return result


def replace_dishes_csv(text: str, actor=None, dry_run=False, progress=None) -> dict:
    rows = parse_csv_semicolon(text)
    parsed_rows = []
    errors = []
    skipped = 0
    seen_norms: dict[str, int] = {}
    total = len(rows)

    for index, row in enumerate(rows, start=1):
        if progress:
            progress(index, total, "parse")
        try:
            incoming = _csv_row_to_payload(row)
        except Exception as exc:
            errors.append({"row": index, "error": str(exc)})
            continue

        if not incoming["ru"]:
            skipped += 1
            continue

        norm = normalize_ru(incoming["ru"])
        duplicate_row = seen_norms.get(norm)
        if duplicate_row is not None:
            errors.append(
                {
                    "row": index,
                    "error": f"duplicate ru name in CSV; already seen on row {duplicate_row}: {incoming['ru']}",
                }
            )
            continue

        seen_norms[norm] = index
        parsed_rows.append({"row": index, "incoming": incoming})

    if not parsed_rows:
        errors.append({"row": 0, "error": "CSV does not contain any non-empty dish rows"})

    if errors:
        return {
            "deleted": 0,
            "created": 0,
            "skipped": skipped,
            "errors": errors,
        }

    deleted = Dish.objects.count()
    actor_ref = actor if getattr(actor, "is_authenticated", False) else None

    with transaction.atomic():
        existing = list(Dish.objects.only("id", "name_ru"))
        if existing:
            DishChangeLog.objects.bulk_create(
                [
                    DishChangeLog(
                        dish=dish,
                        dish_id_snapshot=dish.id,
                        name_ru_snapshot=dish.name_ru,
                        actor=actor_ref,
                        action=DishChangeLog.ACTION_DELETE,
                        changed_fields={"mode": "replace_all"},
                    )
                    for dish in existing
                ],
                batch_size=500,
            )
            Dish.objects.all().delete()

        created = 0
        create_total = len(parsed_rows)
        for item in parsed_rows:
            upsert_dish(item["incoming"], actor)
            created += 1
            if progress and create_total:
                progress(created, create_total, "import")

        if dry_run:
            transaction.set_rollback(True)

    if progress and parsed_rows:
        progress(len(parsed_rows), len(parsed_rows), "import")
    return {
        "deleted": deleted,
        "created": created,
        "skipped": skipped,
        "errors": [],
    }


def _csv_row_to_payload(row: list[str]) -> dict:
    padded = list(row) + [""] * (6 - len(row))
    ru, en, kcal, cat_ru, cat_en, gr = padded[:6]
    payload = {
        "ru": (ru or "").strip(),
        "en": (en or "").strip(),
        "kcal": parse_int_or_none(kcal),
        "catRu": (cat_ru or "").strip(),
        "catEn": (cat_en or "").strip(),
        "gr": parse_int_or_none(gr),
    }
    if payload["catRu"] and not payload["catEn"]:
        payload["catEn"] = CAT_RU2EN.get(payload["catRu"], "")
    return payload


def _dish_field_changes(dish: Dish, incoming: dict) -> dict:
    changes = {}
    current = {
        "en": dish.name_en or "",
        "kcal": dish.kcal_per_100,
        "gr": dish.grams_default,
        "catRu": dish.category_ru or "",
        "catEn": dish.category_en or "",
    }
    for key, current_value in current.items():
        incoming_value = incoming.get(key)
        if current_value != incoming_value:
            changes[key] = {"current": current_value, "incoming": incoming_value}
    return changes
