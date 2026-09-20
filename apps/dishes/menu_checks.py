from apps.core.text import normalize_ru, tokens_sorted_ru

from .models import Dish


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


def duplicate_groups(rows: list) -> dict:
    by_norm: dict[str, list[int]] = {}
    by_tokens: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        ru = row.get("ru") or row.get("name_ru") or ""
        if not isinstance(ru, str):
            continue
        by_norm.setdefault(normalize_ru(ru), []).append(index)
        by_tokens.setdefault(tokens_sorted_ru(ru), []).append(index)
    return {
        "full": [items for items in by_norm.values() if len(items) > 1],
        "tokens": [items for items in by_tokens.values() if len(items) > 1],
    }
