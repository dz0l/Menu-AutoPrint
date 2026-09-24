from __future__ import annotations

from apps.core.text import clean_name
from apps.dishes.crud import base_revision, dish_to_dict
from apps.dishes.matching import find_similar_dishes
from apps.dishes.models import Dish
from apps.menu.services import dish_maps, is_group_line, is_page_break_line

# Same threshold as web CSV / find_similar_dishes default (~80%+).
SIMILAR_THRESHOLD = 0.82


def dish_version(dish: Dish) -> str:
    stamp = dish.updated_at.isoformat() if dish.updated_at else "0"
    return f"{dish.id}:{stamp}"


def missing_fields_for(dish: Dish, *, show_kcal: bool) -> list[str]:
    missing: list[str] = []
    if not (dish.name_en or "").strip():
        missing.append("en")
    if show_kcal:
        if dish.grams_default is None:
            missing.append("gr")
        if dish.kcal_per_100 is None:
            missing.append("kcal")
    return missing


def similar_options(query: str, *, limit: int = 3, threshold: float = SIMILAR_THRESHOLD) -> list[dict]:
    matches = find_similar_dishes(query, limit=limit, threshold=threshold)
    if not matches:
        return []
    names = [item["name"] for item in matches]
    id_by_name = {
        dish.name_ru: dish.id
        for dish in Dish.objects.filter(name_ru__in=names).only("id", "name_ru")
    }
    options: list[dict] = []
    for item in matches:
        dish_id = id_by_name.get(item["name"])
        if dish_id is None:
            continue
        options.append({"id": dish_id, "ru": item["name"], "score": item["score"]})
    return options


def check_menu(ru: str | list[str], *, show_kcal: bool = True, dishes=None) -> dict:
    source_lines = str(ru or "").replace("\u00a0", " ").splitlines() if isinstance(ru, str) else list(ru or [])
    maps = dishes if dishes is not None else dish_maps()
    lines = []
    issues = []
    ready = True
    logical_index = 0

    for source_index, raw in enumerate(source_lines):
        text = str(raw or "").replace("\u00a0", " ").strip()
        if not text:
            continue
        if is_page_break_line(text):
            lines.append(
                {
                    "index": logical_index,
                    "source_line_index": source_index,
                    "kind": "page_break",
                    "input": text,
                    "status": "ok",
                }
            )
            logical_index += 1
            continue
        if is_group_line(text):
            lines.append(
                {
                    "index": logical_index,
                    "source_line_index": source_index,
                    "kind": "group",
                    "input": text,
                    "status": "ok",
                }
            )
            logical_index += 1
            continue

        dish = maps.get(clean_name(text))
        if dish is None:
            ready = False
            lines.append(
                {
                    "index": logical_index,
                    "source_line_index": source_index,
                    "kind": "dish",
                    "input": text,
                    "dish_id": None,
                    "canonical_name": None,
                    "status": "unknown",
                    "missing_fields": ["ru"],
                    "version": None,
                    "current": None,
                    "options": similar_options(text),
                }
            )
            issues.append({"code": "unknown_dish", "line_index": logical_index, "field": "ru"})
            logical_index += 1
            continue

        missing = missing_fields_for(dish, show_kcal=show_kcal)
        status = "ok" if not missing else "incomplete"
        if missing:
            ready = False
        current = dish_to_dict(dish)
        current.pop("created_at", None)
        current.pop("updated_at", None)
        entry = {
            "index": logical_index,
            "source_line_index": source_index,
            "kind": "dish",
            "input": text,
            "dish_id": dish.id,
            "canonical_name": dish.name_ru,
            "status": status,
            "missing_fields": missing,
            "version": dish_version(dish),
            "current": {
                "ru": dish.name_ru,
                "en": dish.name_en or "",
                "gr": dish.grams_default,
                "kcal": dish.kcal_per_100,
                "catRu": dish.category_ru or "",
                "catEn": dish.category_en or "",
            },
            "options": [],
        }
        lines.append(entry)
        for field in missing:
            code = {
                "en": "missing_translation",
                "gr": "missing_grams",
                "kcal": "missing_kcal",
            }.get(field, f"missing_{field}")
            issues.append({"code": code, "line_index": logical_index, "field": field})
        logical_index += 1

    if not any(item["kind"] == "dish" for item in lines):
        ready = False
        if not issues:
            issues.append({"code": "empty_menu", "line_index": None, "field": None})

    return {
        "ready": ready and bool(lines),
        "catalog_revision": base_revision(),
        "lines": lines,
        "issues": issues,
    }


def suggest_with_ids(query: str, *, limit: int = 12) -> list[dict]:
    query_norm = clean_name(query)
    if not query_norm:
        return []
    dishes = list(Dish.objects.exclude(name_ru="").only("id", "name_ru", "name_en"))
    tokens = [token for token in query_norm.split(" ") if token]
    scored = []
    for dish in dishes:
        name = dish.name_ru
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
            scored.append((score, len(name_norm), dish.id, name))
    scored.sort(key=lambda item: (item[0], item[1], item[3]))
    return [{"id": item[2], "ru": item[3]} for item in scored[:limit]]
