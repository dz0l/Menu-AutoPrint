import re


STOP_WORDS_RU = {"с", "со", "и", "из", "на", "в", "во", "от", "по", "для", "над", "под", "без", "при", "к", "ко"}


def clean_name(value: str | None) -> str:
    text = str(value or "")
    text = text.replace("\u00a0", " ")
    text = text.replace("ё", "е").replace("Ё", "е")
    text = re.sub(r"[•\-—–]", " ", text)
    text = re.sub(r"[“”„«»\"'’`]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def normalize_ru(value: str | None) -> str:
    text = str(value or "").lower().strip()
    text = text.replace("ё", "е")
    text = re.sub(r"[«»„”\"’'`]", "", text)
    text = re.sub(r"[.]+", "", text)
    text = re.sub(r"[–—−]+", "-", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*-\s*", "-", text)
    return text.strip()


def stem_word_ru(word: str) -> str:
    text = re.sub(
        r"(ыми|ими|ого|ему|ому|ее|ая|ое|ые|ий|ый|ой|ых|ым|ою|омy|его)$",
        "",
        word,
    )
    text = re.sub(r"(ами|ями|ев|ов|ом|ем|ам|ям|ах|ях|ей|ью|ия|ие|ий|ию|ии)$", "", text)
    text = re.sub(r"(у|ю|а|я|е|ы|и|о)$", "", text)
    if len(text) > 4:
        if text.endswith("н"):
            text = text[:-1]
        text = re.sub(r"(ческ|ск)$", "", text)
    return text


def tokens_bag_ru(value: str | None) -> list[str]:
    result: set[str] = set()
    for token in re.split(r"[\s-]+", normalize_ru(value)):
        if not token or token in STOP_WORDS_RU:
            continue
        base = stem_word_ru(token)
        if not base:
            continue
        result.add(base)
        if len(base) > 3:
            if base.endswith("н"):
                result.add(base[:-1])
            if base.endswith("ск"):
                result.add(base[:-2])
            if base.endswith("ческ"):
                result.add(base[:-4])
    return sorted(result)


def tokens_sorted_ru(value: str | None) -> str:
    return " ".join(sorted(t for t in re.split(r"[\s-]+", normalize_ru(value)) if t))
