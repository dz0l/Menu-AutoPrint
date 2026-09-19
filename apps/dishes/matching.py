import re
from difflib import SequenceMatcher

from apps.core.text import clean_name, normalize_ru, tokens_bag_ru, tokens_sorted_ru

from .models import Dish


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
