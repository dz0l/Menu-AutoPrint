from __future__ import annotations

from dataclasses import dataclass

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics


BASE_MENU_FONT_SIZE = 20
BASE_MENU_LEADING = 28
BASE_GROUP_FONT_SIZE = 20
BASE_GROUP_LEADING = 28
BASE_CONTINUATION_LEADING = 24
BASE_GROUP_SPACE_BEFORE = 20
BASE_AFTER_GROUP_SPACE_BEFORE = 6
BASE_DISH_SPACE_BEFORE = 2
MIN_MENU_FONT_SIZE = 12
SPACING_SCALE_STEPS = (1.0, 0.95, 0.9, 0.85, 0.8, 0.75, 0.7, 0.65, 0.6, 0.55, 0.5)

PAGE_MARGIN_LEFT = 42
PAGE_MARGIN_RIGHT = 42
PAGE_CONTENT_TOP_OFFSET = 48
PAGE_CONTENT_BOTTOM = 78
PAGE_FOOTER_Y = 28


@dataclass
class PageLayout:
    menu_font_size: int
    menu_leading: int
    group_font_size: int
    group_leading: int
    continuation_leading: int
    group_space_before: int
    after_group_space_before: int
    dish_space_before: int

    @classmethod
    def from_menu_font_size(cls, menu_font_size: int, spacing_scale: float = 1.0) -> PageLayout:
        return cls.create(menu_font_size, spacing_scale=spacing_scale)

    @classmethod
    def create(cls, menu_font_size: int, *, spacing_scale: float = 1.0) -> PageLayout:
        font_scale = menu_font_size / BASE_MENU_FONT_SIZE
        space_scale = spacing_scale
        menu_leading = max(1, round(BASE_MENU_LEADING * font_scale * space_scale))
        dish_space_before = max(1, round(BASE_DISH_SPACE_BEFORE * font_scale * space_scale))
        scaled_continuation = round(BASE_CONTINUATION_LEADING * font_scale * space_scale)
        min_continuation = max(4, round(menu_leading * 0.72))
        max_continuation = max(min_continuation + 1, menu_leading + dish_space_before - 2)
        continuation_leading = max(min_continuation, min(scaled_continuation, max_continuation))
        return cls(
            menu_font_size=menu_font_size,
            menu_leading=menu_leading,
            group_font_size=menu_font_size,
            group_leading=max(1, round(BASE_GROUP_LEADING * font_scale * space_scale)),
            continuation_leading=continuation_leading,
            group_space_before=max(1, round(BASE_GROUP_SPACE_BEFORE * font_scale * space_scale)),
            after_group_space_before=max(1, round(BASE_AFTER_GROUP_SPACE_BEFORE * font_scale * space_scale)),
            dish_space_before=dish_space_before,
        )

    def to_dict(self) -> dict:
        return {
            "menu_font_size": self.menu_font_size,
            "menu_leading": self.menu_leading,
            "group_font_size": self.group_font_size,
            "group_leading": self.group_leading,
            "continuation_leading": self.continuation_leading,
            "group_space_before": self.group_space_before,
            "after_group_space_before": self.after_group_space_before,
            "dish_space_before": self.dish_space_before,
        }


@dataclass
class TextBlock:
    lines: list[str]
    font_name: str
    font_size: int
    leading: int
    continuation_leading: int
    space_before: int
    is_dish: bool = False


def _page_content_top() -> float:
    return A4[1] - PAGE_CONTENT_TOP_OFFSET


def _page_max_width() -> float:
    return A4[0] - PAGE_MARGIN_LEFT - PAGE_MARGIN_RIGHT


def _block_height(block: TextBlock) -> float:
    height = block.space_before
    if not block.lines:
        return height
    for line_index in range(1, len(block.lines)):
        if block.is_dish and line_index == 1:
            height += block.continuation_leading
        else:
            height += block.leading
    height += block.leading
    return height


def _total_blocks_height(blocks: list[TextBlock]) -> float:
    return sum(_block_height(block) for block in blocks)


def compute_page_layout(
    items: list[dict],
    *,
    auto_format: bool,
    regular_font: str,
    bold_font: str,
) -> PageLayout:
    if not auto_format:
        return PageLayout.from_menu_font_size(BASE_MENU_FONT_SIZE)

    available_height = _page_content_top() - PAGE_CONTENT_BOTTOM

    def fits(layout: PageLayout) -> bool:
        blocks = _build_blocks(
            items,
            max_width=_page_max_width(),
            regular_font=regular_font,
            bold_font=bold_font,
            layout=layout,
        )
        return _total_blocks_height(blocks) <= available_height

    for spacing_scale in SPACING_SCALE_STEPS:
        layout = PageLayout.create(BASE_MENU_FONT_SIZE, spacing_scale=spacing_scale)
        if fits(layout):
            return layout

    for font_size in range(BASE_MENU_FONT_SIZE - 1, MIN_MENU_FONT_SIZE - 1, -1):
        for spacing_scale in SPACING_SCALE_STEPS:
            layout = PageLayout.create(font_size, spacing_scale=spacing_scale)
            if fits(layout):
                return layout

    layout = PageLayout.create(MIN_MENU_FONT_SIZE, spacing_scale=SPACING_SCALE_STEPS[-1])
    if not fits(layout):
        raise ValueError(
            "Меню не помещается на лист. Добавьте разделитель --- или сократите список."
        )
    return layout


def enrich_page_items(
    items: list[dict],
    *,
    layout: PageLayout,
    regular_font: str,
    bold_font: str,
) -> list[dict]:
    max_width = _page_max_width()
    enriched: list[dict] = []
    for item in items:
        copy = dict(item)
        if item.get("type") == "group":
            text = f"{item.get('text', '')}{item.get('suffix', '')}".strip()
            copy["lines"] = _wrap_text(
                text,
                max_width=max_width,
                font_name=bold_font,
                font_size=layout.group_font_size,
            )
        else:
            copy["lines"] = _wrap_dish_lines(
                item.get("text", ""),
                item.get("suffix", ""),
                max_width=max_width,
                font_name=regular_font,
                font_size=layout.menu_font_size,
            )
        enriched.append(copy)
    return enriched


def _build_blocks(
    items: list[dict],
    *,
    max_width: float,
    regular_font: str,
    bold_font: str,
    layout: PageLayout,
) -> list[TextBlock]:
    blocks: list[TextBlock] = []
    previous_type = None
    for index, item in enumerate(items):
        is_group = item.get("type") == "group"
        if index == 0:
            space_before = 0
        elif is_group:
            space_before = layout.group_space_before
        elif previous_type == "group":
            space_before = layout.after_group_space_before
        else:
            space_before = layout.dish_space_before

        if is_group:
            text = f"{item.get('text', '')}{item.get('suffix', '')}".strip()
            block_lines = _wrap_text(
                text,
                max_width=max_width,
                font_name=bold_font,
                font_size=layout.group_font_size,
            )
            blocks.append(
                TextBlock(
                    lines=block_lines,
                    font_name=bold_font,
                    font_size=layout.group_font_size,
                    leading=layout.group_leading,
                    continuation_leading=layout.group_leading,
                    space_before=space_before,
                    is_dish=False,
                )
            )
            previous_type = "group"
            continue

        block_lines = _wrap_dish_lines(
            item.get("text", ""),
            item.get("suffix", ""),
            max_width=max_width,
            font_name=regular_font,
            font_size=layout.menu_font_size,
        )
        blocks.append(
            TextBlock(
                lines=block_lines,
                font_name=regular_font,
                font_size=layout.menu_font_size,
                leading=layout.menu_leading,
                continuation_leading=layout.continuation_leading,
                space_before=space_before,
                is_dish=True,
            )
        )
        previous_type = "dish"
    return blocks


def _wrap_dish_lines(text: str, suffix: str, *, max_width: float, font_name: str, font_size: int) -> list[str]:
    bullet = "• "
    raw = (text or "").strip()
    full = f"{bullet}{raw}{suffix}"
    if _text_width(full, font_name, font_size) <= max_width:
        return [full]

    if not suffix:
        return _wrap_text(full, max_width=max_width, font_name=font_name, font_size=font_size)

    words = raw.split()
    for split_index in range(len(words) - 1, 0, -1):
        head = " ".join(words[:split_index]).strip()
        tail = " ".join(words[split_index:]).strip()
        first_line = f"{bullet}{head}".rstrip()
        second_line = f"{tail}{suffix}".strip()
        if (
            head
            and tail
            and _text_width(first_line, font_name, font_size) <= max_width
            and _text_width(second_line, font_name, font_size) <= max_width
        ):
            return [first_line, second_line]

    return _wrap_head_and_tail(raw, suffix, max_width=max_width, font_name=font_name, font_size=font_size)


def _wrap_head_and_tail(text: str, suffix: str, *, max_width: float, font_name: str, font_size: int) -> list[str]:
    bullet = "• "
    words = (text or "").split()
    if not words:
        return [f"{bullet}{suffix}".strip()]
    if len(words) == 1:
        return _wrap_text(f"{bullet}{words[0]}{suffix}", max_width=max_width, font_name=font_name, font_size=font_size)

    head_words = words[:-1]
    tail = f"{words[-1]}{suffix}"
    lines: list[str] = []
    current = bullet.rstrip()

    for word in head_words:
        candidate = f"{current} {word}".strip()
        if current and _text_width(candidate, font_name, font_size) > max_width and current != bullet.rstrip():
            lines.append(current)
            current = word
        else:
            current = candidate

    if current:
        lines.append(current)
    lines.append(tail)
    return lines


def _wrap_text(text: str, *, max_width: float, font_name: str, font_size: int) -> list[str]:
    words = (text or "").split()
    if not words:
        return [""]

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}".strip()
        if _text_width(candidate, font_name, font_size) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _text_width(text: str, font_name: str, font_size: int) -> float:
    return pdfmetrics.stringWidth(text, font_name, font_size)
