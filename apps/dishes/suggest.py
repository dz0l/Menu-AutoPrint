from apps.core.text import clean_name

from .models import Dish


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
