"""Realistic fake value generation using Faker (ru_RU locale).

Type detection priority:
  1. Value-based: regex patterns on actual cell samples
  2. Column-name-based: keyword matching (fallback)
"""
from __future__ import annotations

import re

import pandas as pd
from faker import Faker

_ru = Faker("ru_RU")
_en = Faker("en_US")

# Column name keywords → category (fallback only)
_NAME_KEYWORDS: list[tuple[list[str], str]] = [
    (["фио", "сотрудник", "автор", "ответственный", "создал", "обнаружил", "специалист"], "person"),
    (["контрагент", "предприятие", "организация", "компания",
      "поставщик", "подрядчик", "исполнитель", "рабочее место"], "company"),
    (["телефон", "тел.", "phone", "моб"], "phone"),
    (["email", "почта", "e-mail", "mail"], "email"),
    (["адрес", "address", "местонахождение"], "address"),
    (["город", "населённый пункт"], "city"),
]

# Regex patterns for value-based detection
_EMAIL_RE    = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE    = re.compile(r"^[\+7\(8][\d\s\-\(\)]{8,}$")
_IP_RE       = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
_COMPANY_RE  = re.compile(r"^(ООО|АО|ПАО|ЗАО|ИП|ОАО|НКО|ФГУП|МУП|ГУП)\s", re.IGNORECASE)

# Lazy-loaded Natasha components for person name detection
_natasha_segmenter = None
_natasha_ner_tagger = None


def _get_natasha():
    global _natasha_segmenter, _natasha_ner_tagger
    if _natasha_segmenter is None:
        from natasha import Segmenter, NewsEmbedding, NewsNERTagger
        _natasha_segmenter = Segmenter()
        _natasha_ner_tagger = NewsNERTagger(NewsEmbedding())
    return _natasha_segmenter, _natasha_ner_tagger


def _is_person(val: str) -> bool:
    """Return True if val contains a Russian person name (Natasha NER)."""
    try:
        from natasha import Doc
        segmenter, ner_tagger = _get_natasha()
        doc = Doc(val)
        doc.segment(segmenter)
        doc.tag_ner(ner_tagger)
        return any(span.type == "PER" for span in doc.spans)
    except Exception:
        return False


def _category_from_values(series: pd.Series) -> str | None:
    """Detect data category from sample values. Returns None if unclear."""
    samples = series.dropna().astype(str).str.strip().unique()[:20]
    if len(samples) == 0:
        return None

    counts: dict[str, int] = {
        "email": 0, "phone": 0, "ip": 0, "company": 0, "person": 0
    }
    for val in samples:
        if _EMAIL_RE.match(val):
            counts["email"] += 1
        elif _PHONE_RE.match(val):
            counts["phone"] += 1
        elif _IP_RE.match(val):
            counts["ip"] += 1
        elif _COMPANY_RE.match(val):
            counts["company"] += 1
        elif _is_person(val):
            counts["person"] += 1

    total = len(samples)
    # Return the category if at least 30 % of samples match
    best = max(counts, key=counts.__getitem__)
    if counts[best] / total >= 0.3:
        return best
    return None


def _category_from_name(col_name: str) -> str | None:
    col_lower = col_name.lower()
    for keywords, category in _NAME_KEYWORDS:
        if any(kw in col_lower for kw in keywords):
            return category
    return None


def detect_category(col_name: str, series: pd.Series | None = None) -> str | None:
    """Detect data category: value-based first, column-name fallback."""
    if series is not None:
        cat = _category_from_values(series)
        if cat:
            return cat
    return _category_from_name(col_name)


def generate_fake_for_category(category: str) -> str:
    """Generate one realistic fake value for the given category."""
    if category == "person":
        return _ru.name()
    if category == "company":
        return _ru.company()
    if category == "phone":
        return _ru.phone_number()
    if category == "email":
        return _en.email()
    if category == "ip":
        return _en.ipv4()
    if category == "address":
        return _ru.address().replace("\n", ", ")
    if category == "city":
        return _ru.city()
    return ""


def generate_fake_value(col_name: str, series: pd.Series | None = None) -> str | None:
    """Return a realistic fake value, or None if type is unknown."""
    category = detect_category(col_name, series)
    if category is None:
        return None
    return generate_fake_for_category(category)
