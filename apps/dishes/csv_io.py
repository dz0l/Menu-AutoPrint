import csv
import io


HEADERS = ["ru", "en", "kcal", "catRu", "catEn", "gr"]
HEADER_SETS = {
    ("ru", "en", "kcal", "catru", "caten", "gr"),
    ("блюдо_ru", "dish_en", "ккал", "категория_ru", "category_en", "gr"),
}


def _is_header(row: list[str]) -> bool:
    normalized = tuple((cell or "").strip().lower() for cell in row[:6])
    return normalized in HEADER_SETS


def parse_csv_semicolon(text: str) -> list[list[str]]:
    text = (text or "").lstrip("\ufeff")
    reader = csv.reader(io.StringIO(text), delimiter=";", quotechar='"')
    rows = []
    for row in reader:
        if not row or _is_header(row):
            continue
        padded = (row + [""] * 6)[:6]
        if any(cell.strip() for cell in padded):
            rows.append([cell.strip() for cell in padded])
    return rows


def to_csv_semicolon(rows: list[list[str]], header: list[str] | None = None) -> str:
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", quotechar='"', lineterminator="\n")
    if header:
        writer.writerow(header)
    writer.writerows(rows)
    return out.getvalue()
