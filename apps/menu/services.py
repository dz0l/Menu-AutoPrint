from dataclasses import dataclass

from apps.core.text import clean_name
from apps.dishes.models import Dish
from apps.pdf.services import compute_page_layout, enrich_page_items, get_menu_fonts


GROUP_RU2EN = {
    "салаты": "Salads:",
    "закуска": "Starters:",
    "горячая закуска": "Hot Starters:",
    "холодная закуска": "Cold Starters:",
    "супы": "Soups:",
    "горячее": "Main Courses:",
    "гарнир": "Side Dishes:",
    "завтрак": "Breakfast:",
    "шашлык": "BBQ:",
}


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


def translate_group_line(line: str) -> str:
    label = (line or "").strip().rstrip(":").strip().lower()
    return GROUP_RU2EN.get(label, f"{(line or '').strip().rstrip(':')}:" if line else "")


def translate_lines(ru_lines: list[str], current_en: list[str] | None = None) -> list[str]:
    dishes = dish_maps()
    translated = []
    for ru in ru_lines:
        if is_group_line(ru):
            translated.append(translate_group_line(ru))
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


def build_preview(ru_lines: list[str], en_lines: list[str], show_kcal=True, auto_format=True) -> dict:
    missing = []
    ru = []
    en = []
    for index, line in enumerate(ru_lines):
        info = line_info(line)
        if info.missing:
            missing.append(line)
        ru.append(_render_line(info, "ru", show_kcal))

        en_line = en_lines[index] if index < len(en_lines) else "???"
        en_info = line_info(en_line, ru_ref=line)
        if en_info.missing:
            missing.append(line)
        en.append(_render_line(en_info, "en", show_kcal))

    regular_font, bold_font = get_menu_fonts()
    ru_layout = compute_page_layout(ru, auto_format=auto_format, regular_font=regular_font, bold_font=bold_font)
    en_layout = compute_page_layout(en, auto_format=auto_format, regular_font=regular_font, bold_font=bold_font)
    return {
        "ru": enrich_page_items(ru, layout=ru_layout, regular_font=regular_font, bold_font=bold_font),
        "en": enrich_page_items(en, layout=en_layout, regular_font=regular_font, bold_font=bold_font),
        "missing": sorted(set(missing)),
        "layout": {"ru": ru_layout.to_dict(), "en": en_layout.to_dict()},
        "auto_format": bool(auto_format),
    }


def _render_line(info: MenuLine, lang: str, show_kcal: bool) -> dict:
    if info.is_group:
        return {"text": info.raw, "type": "group", "suffix": ""}
    if not show_kcal:
        return {"text": info.raw, "type": "dish", "suffix": ""}
    if lang == "en":
        grams_unit = "g"
        kcal_unit = "kcal"
    else:
        grams_unit = "гр"
        kcal_unit = "ккал"
    return {
        "text": info.raw,
        "type": "dish",
        "suffix": f" ({info.grams or '??'} {grams_unit}, {info.kcal or '??'} {kcal_unit})",
    }
