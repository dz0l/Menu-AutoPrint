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


def _dish_update_payload(data: dict) -> dict:
    payload = {
        "name_en": (data.get("en") or data.get("name_en") or "").strip(),
        "kcal_per_100": parse_int_or_none(data.get("kcal", data.get("kcal_per_100"))),
        "grams_default": parse_int_or_none(data.get("gr", data.get("grams_default"))),
        "category_ru": (data.get("catRu") or data.get("category_ru") or "").strip(),
        "category_en": (data.get("catEn") or data.get("category_en") or "").strip(),
    }
    if payload["category_ru"] and not payload["category_en"]:
        payload["category_en"] = CAT_RU2EN.get(payload["category_ru"], "")
    return payload


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


def update_dish(dish: Dish, data: dict, actor=None) -> Dish:
    name_ru = (data.get("ru") or data.get("name_ru") or dish.name_ru or "").strip()
    if not name_ru:
        raise ValueError("name_ru required")
    payload = _dish_update_payload(data)

    with transaction.atomic():
        duplicate = find_dish_by_ru_name(name_ru, exclude_id=dish.id)
        if duplicate:
            raise ValueError("duplicate ru name")

        dish.name_ru = name_ru
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


def import_dishes_csv_safely(text: str, actor=None, dry_run=False, apply_updates=False, progress=None) -> dict:
    review = review_dishes_csv_import(text, progress=progress)
    outcome = {
        "created": 0,
        "updated": 0,
        "skipped": len(review.skipped) + len(review.exact_matches),
        "changed_matches": review.changed_matches,
        "similar_matches": review.similar_matches,
        "errors": list(review.errors),
    }

    create_total = len(review.create_candidates)
    update_total = len(review.changed_matches) if apply_updates else 0
    apply_total = create_total + update_total
    applied = 0

    with transaction.atomic():
        for item in review.create_candidates:
            try:
                upsert_dish(item["incoming"], actor)
                outcome["created"] += 1
            except Exception as exc:
                outcome["errors"].append({"row": item["row"], "error": str(exc)})
            applied += 1
            if progress and apply_total:
                progress(applied, apply_total, "import")

        if apply_updates:
            for item in review.changed_matches:
                try:
                    upsert_dish(item["incoming"], actor)
                    outcome["updated"] += 1
                except Exception as exc:
                    outcome["errors"].append({"row": item["row"], "error": str(exc)})
                applied += 1
                if progress and apply_total:
                    progress(applied, apply_total, "import")

        if dry_run:
            transaction.set_rollback(True)

    if progress and apply_total:
        progress(apply_total, apply_total, "import")
    return outcome


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


def find_similar_dishes(query: str, limit=3, threshold=0.82) -> list[dict]:
    query_norm = clean_name(query)
    if not query_norm:
        return []

    matches = []
    for entry in _prepared_catalog():
        score = _candidate_score(query, entry["name"])
        if score >= threshold:
            matches.append({"name": entry["name"], "score": round(score, 4)})
    matches.sort(key=lambda item: (-item["score"], item["name"]))
    return matches[:limit]


def analyze_pasted(text: str) -> list[dict]:
    catalog = _prepared_catalog()
    exact_lookup = {entry["norm"]: entry for entry in catalog}
    result = []
    for index, raw in enumerate((text or "").splitlines()):
        stripped = re.sub(r"^[•\-*\d.)\s]+", "", raw).strip()
        norm = clean_name(stripped)
        if not norm or stripped.endswith(":") or stripped == "---":
            result.append({"i": index, "raw": raw, "norm": norm, "status": "skip"})
            continue

        exact = exact_lookup.get(norm)
        if exact:
            result.append(
                {
                    "i": index,
                    "raw": raw,
                    "norm": norm,
                    "status": "exact" if raw.strip() == exact["name"] else "auto",
                    "best": {"name": exact["name"], "score": 1.0},
                    "options": [{"name": exact["name"], "score": 1.0}],
                }
            )
            continue

        query_sorted = tokens_sorted_ru(stripped)
        query_bag = set(tokens_bag_ru(stripped))
        first_char = norm[:1]

        shortlist = []
        for entry in catalog:
            if entry["sorted"] == query_sorted:
                shortlist.append(entry)
                continue
            if query_bag and entry["bag"] and query_bag & entry["bag"]:
                shortlist.append(entry)
                continue
            if first_char and entry["norm"].startswith(first_char):
                shortlist.append(entry)

        matches = []
        for entry in shortlist or catalog:
            score = max(
                _sequence_ratio(norm, entry["norm"]),
                _sequence_ratio(query_sorted, entry["sorted"]),
                len(query_bag & entry["bag"]) / len(query_bag | entry["bag"]) if query_bag and entry["bag"] else 0.0,
                simple_score_tokens(stripped, entry["name"]),
            )
            if score >= 0.74:
                matches.append({"name": entry["name"], "score": score})
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


def _prepared_catalog() -> list[dict]:
    names = list(Dish.objects.values_list("name_ru", flat=True))
    prepared = []
    for name in names:
        prepared.append(
            {
                "name": name,
                "norm": clean_name(name),
                "sorted": tokens_sorted_ru(name),
                "bag": set(tokens_bag_ru(name)),
            }
        )
    return prepared


def check_missing_fixables(ru_lines: list[str], *, show_kcal: bool = True) -> dict:
    missing = []
    fixables = []
    seen = set()
    dishes = {normalize_ru(dish.name_ru): dish for dish in Dish.objects.all()}
    for raw in ru_lines:
        text = (raw or "").strip()
        if not text or text.endswith(":") or text == "---":
            continue
        key = normalize_ru(text)
        if not key or key in seen:
            continue
        seen.add(key)
        dish = dishes.get(key)
        if not dish:
            missing.append(text)
            continue
        if not dish.name_en:
            fixables.append(text)
            continue
        if show_kcal and (dish.kcal_per_100 is None or dish.grams_default is None):
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
