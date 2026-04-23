from dataclasses import dataclass

from apps.core.text import clean_name
from apps.dishes.models import Dish


@dataclass
class MenuLine:
    raw: str
    is_group: bool
    grams: str | None = None
    kcal: str | None = None
    missing: bool = False


def normalize_lines(value: str | list[str] | None) -> list[str]:
    if isinstance(value, list):
        source = value
    else:
        source = str(value or "").replace("\u00a0", " ").splitlines()
    return [line.strip() for line in source if line and line.strip()]


def is_group_line(value: str) -> bool:
    return (value or "").strip().endswith(":")


def dish_maps() -> dict[str, Dish]:
    return {clean_name(dish.name_ru): dish for dish in Dish.objects.all()}


def translate_lines(ru_lines: list[str], current_en: list[str] | None = None) -> list[str]:
    current_en = current_en or []
    dishes = dish_maps()
    translated = []
    for index, ru in enumerate(ru_lines):
        existing = current_en[index] if index < len(current_en) else ""
        if existing and existing != "???":
            translated.append(existing)
            continue
        dish = dishes.get(clean_name(ru))
        translated.append(dish.name_en if dish and dish.name_en else "???")
    return translated


def line_info(line: str, ru_ref: str | None = None) -> MenuLine:
    ref = ru_ref or line
    if is_group_line(ref):
        return MenuLine(raw=line, is_group=True)
    dish = dish_maps().get(clean_name(ref))
    if not dish:
        return MenuLine(raw=line, is_group=False, grams="??", kcal="??", missing=True)
    if dish.kcal_per_100 is None and dish.grams_default is None:
        return MenuLine(raw=line, is_group=False, grams="??", kcal="??", missing=True)
    if dish.kcal_per_100 is not None and dish.grams_default is None:
        return MenuLine(raw=line, is_group=False, grams="??", kcal=str(dish.kcal_per_100), missing=True)
    if dish.kcal_per_100 is None and dish.grams_default is not None:
        return MenuLine(raw=line, is_group=False, grams=str(dish.grams_default), kcal="??", missing=True)
    kcal = round((dish.kcal_per_100 or 0) * (dish.grams_default or 0) / 100)
    return MenuLine(raw=line, is_group=False, grams=str(dish.grams_default), kcal=str(kcal), missing=False)


def build_preview(ru_lines: list[str], en_lines: list[str], show_kcal=True) -> dict:
    missing = []
    ru = []
    en = []
    for index, line in enumerate(ru_lines):
        info = line_info(line)
        if info.missing:
            missing.append(line)
        ru.append(_render_line(info, "ru", show_kcal))
        if index < len(en_lines) and en_lines[index]:
            en_info = line_info(en_lines[index], ru_ref=line)
            if en_info.missing:
                missing.append(line)
            en.append(_render_line(en_info, "en", show_kcal))
    return {"ru": ru, "en": en, "missing": sorted(set(missing))}


def _render_line(info: MenuLine, lang: str, show_kcal: bool) -> dict:
    if info.is_group:
        return {"text": info.raw, "type": "group", "suffix": ""}
    if not show_kcal:
        return {"text": info.raw, "type": "dish", "suffix": ""}
    grams_unit = "г" if lang == "ru" else "g"
    kcal_unit = "ккал" if lang == "ru" else "kcal"
    return {
        "text": info.raw,
        "type": "dish",
        "suffix": f" ({info.grams or '??'} {grams_unit}, {info.kcal or '??'} {kcal_unit})",
    }
