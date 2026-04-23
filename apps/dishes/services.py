import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from django.db import IntegrityError, transaction
from django.db.models import Max, Q
from django.utils.dateparse import parse_datetime

from apps.core.text import clean_name, normalize_ru, tokens_bag_ru, tokens_sorted_ru

from .csv_io import HEADERS, parse_csv_semicolon, to_csv_semicolon
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


def list_dishes(params) -> list[Dish]:
    qs = Dish.objects.all()
    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(name_ru__icontains=q) | Q(name_en__icontains=q) | Q(category_ru__icontains=q))
    date_from = parse_datetime(params.get("date_from") or "")
    date_to = parse_datetime(params.get("date_to") or "")
    if date_from:
        qs = qs.filter(updated_at__gte=date_from)
    if date_to:
        qs = qs.filter(updated_at__lte=date_to)
    return list(qs[: int(params.get("limit") or 1000)])


def parse_int_or_none(value):
    if value in (None, ""):
        return None
    return int(value)


def upsert_dish(data: dict, actor=None) -> tuple[Dish, bool]:
    name_ru = (data.get("ru") or data.get("name_ru") or "").strip()
    if not name_ru:
        raise ValueError("name_ru required")
    payload = {
        "name_en": (data.get("en") or data.get("name_en") or "").strip(),
        "kcal_per_100": parse_int_or_none(data.get("kcal", data.get("kcal_per_100"))),
        "grams_default": parse_int_or_none(data.get("gr", data.get("grams_default"))),
        "category_ru": (data.get("catRu") or data.get("category_ru") or "").strip(),
        "category_en": (data.get("catEn") or data.get("category_en") or "").strip(),
    }
    if payload["category_ru"] and not payload["category_en"]:
        payload["category_en"] = CAT_RU2EN.get(payload["category_ru"], "")

    norm = normalize_ru(name_ru)
    with transaction.atomic():
        dish = Dish.objects.filter(name_ru_norm=norm).first()
        created = dish is None
        if created:
            dish = Dish(name_ru=name_ru, created_by=actor if getattr(actor, "is_authenticated", False) else None)
        for key, value in payload.items():
            setattr(dish, key, value)
        dish.updated_by = actor if getattr(actor, "is_authenticated", False) else None
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


def suggest(query: str, lang="ru", limit=12) -> list[str]:
    query_norm = clean_name(query)
    if not query_norm:
        return []
    field = "name_en" if lang == "en" else "name_ru"
    names = list(Dish.objects.exclude(**{field: ""}).values_list(field, flat=True))
    tokens = [token for token in query_norm.split(" ") if token]
    scored = []
    for name in names:
        name_norm = clean_name(name)
        name_tokens = name_norm.split(" ")
        score = 100
        for token in tokens:
            starts = any(part.startswith(token) for part in name_tokens)
            contains = token in name_norm
            if starts:
                score = min(score, 10)
            elif contains:
                score = min(score, 30)
            else:
                break
        else:
            if name_norm.startswith(tokens[0]):
                score = min(score, 5)
            scored.append((score, len(name_norm), name))
    scored.sort(key=lambda item: (item[0], item[1], item[2]))
    return [item[2] for item in scored[:limit]]


def simple_score_tokens(left: str, right: str) -> float:
    a = set(clean_name(left).split())
    b = set(clean_name(right).split())
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / max(len(a), len(b), 1)


def _bag_similarity(left: str, right: str) -> float:
    a = set(tokens_bag_ru(left))
    b = set(tokens_bag_ru(right))
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _sequence_ratio(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _candidate_score(query: str, candidate: str) -> float:
    query_norm = normalize_ru(query)
    candidate_norm = normalize_ru(candidate)
    if query_norm == candidate_norm:
        return 1.0

    query_sorted = tokens_sorted_ru(query)
    candidate_sorted = tokens_sorted_ru(candidate)
    if query_sorted and query_sorted == candidate_sorted:
        return 0.985

    return max(
        _sequence_ratio(clean_name(query), clean_name(candidate)),
        _sequence_ratio(query_sorted, candidate_sorted),
        _bag_similarity(query, candidate),
        simple_score_tokens(query, candidate),
    )


def analyze_pasted(text: str) -> list[dict]:
    catalog = list(Dish.objects.values_list("name_ru", flat=True))
    result = []
    for index, raw in enumerate((text or "").splitlines()):
        stripped = re.sub(r"^[•\-*\d.)\s]+", "", raw).strip()
        norm = clean_name(stripped)
        if not norm or stripped.endswith(":"):
            result.append({"i": index, "raw": raw, "norm": norm, "status": "skip"})
            continue

        matches = []
        for name in catalog:
            score = _candidate_score(stripped, name)
            if score >= 0.74:
                matches.append({"name": name, "score": score})
        matches.sort(key=lambda item: (-item["score"], item["name"]))

        if not matches:
            result.append({"i": index, "raw": raw, "norm": norm, "status": "unknown"})
            continue

        best = matches[0]
        if raw.strip() == best["name"]:
            status = "exact"
        elif best["score"] >= 0.97:
            status = "auto"
        else:
            status = "review"

        result.append(
            {
                "i": index,
                "raw": raw,
                "norm": norm,
                "status": status,
                "best": best,
                "options": matches[:3],
            }
        )
    return result


def check_missing_fixables(ru_lines: list[str]) -> dict:
    missing = []
    fixables = []
    seen = set()
    dishes = {dish.name_ru_norm: dish for dish in Dish.objects.all()}
    for raw in ru_lines:
        text = (raw or "").strip()
        if not text or text.endswith(":"):
            continue
        key = normalize_ru(text)
        if not key or key in seen:
            continue
        seen.add(key)
        dish = dishes.get(key)
        if not dish:
            missing.append(text)
            continue
        if dish.kcal_per_100 is None or dish.grams_default is None:
            fixables.append(text)
    return {"missing": missing, "fixables": fixables}


def duplicate_groups(rows: list[dict]) -> dict:
    by_norm: dict[str, list[int]] = {}
    by_tokens: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        ru = row.get("ru") or row.get("name_ru") or ""
        by_norm.setdefault(normalize_ru(ru), []).append(index)
        by_tokens.setdefault(tokens_sorted_ru(ru), []).append(index)
    return {
        "full": [items for items in by_norm.values() if len(items) > 1],
        "tokens": [items for items in by_tokens.values() if len(items) > 1],
    }
