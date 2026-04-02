"""MD text anonymization and restoration logic.

Detects PII entities using Natasha (PER, ORG) + Presidio (email, phone, IP)
+ regex (contract numbers, sums, dates, legal entities, person names) and replaces them with placeholders.
User-defined extra terms are masked after automatic detection.
Mapping JSON allows full restoration.
"""
from __future__ import annotations

import json
import re
from typing import Any

# ---------------------------------------------------------------------------
# Regex patterns for structured PII
# ---------------------------------------------------------------------------

# ORG opening/closing quote characters: « » " '
_ORG_OPEN  = r'[«"\']'
_ORG_CLOSE = r'[»"\']'

# Legal-form prefixes used to detect org names
_ORG_PREFIXES = ("ООО", "ОАО", "ЗАО", "АО", "ПАО", "ИП", "НКО", "ФГУП", "ГУП", "АНО")
_ORG_PREFIX_RE = "|".join(_ORG_PREFIXES)

# Cyrillic uppercase letter
_CYR_UP = r'[А-ЯЁ]'
# Cyrillic lowercase letters (1+)
_CYR_LO = r'[а-яё]+'

_PATTERNS: list[tuple[str, str]] = [
    # Email — before phone to avoid partial overlap
    ("EMAIL", r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"),
    # Russian mobile / landline phones
    ("ТЕЛЕФОН", r"(?<!\d)(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}(?!\d)"),
    # IPv4
    ("IP", r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    # Russian legal entities: ООО "Ромашка", АО Северсталь, ИП Иванов А.А. etc.
    (
        "ОРГ",
        r"(?:" + _ORG_PREFIX_RE + r")"
        r"(?:"
        r"\s+" + _ORG_OPEN + r"[А-ЯЁа-яёA-Za-z0-9][\w\s\-]*?" + _ORG_CLOSE
        + r"|\s+[А-ЯЁ][а-яёА-ЯЁ\w\-]{1,40}(?:\s+[А-ЯЁ][а-яёА-ЯЁ\w\-]{1,40}){0,3}"
        + r")?",
    ),
    # ---- Person name formats (ФИО) ----
    # Format 1: Фамилия И.О.  or  Фамилия И.  e.g. Скорочкина А.А.
    (
        "ФИО",
        _CYR_UP + _CYR_LO + r"\s+" + _CYR_UP + r"\.(?:" + _CYR_UP + r"\.)?",
    ),
    # Format 2: И.О. Фамилия  e.g. А.А. Скорочкина
    (
        "ФИО",
        _CYR_UP + r"\." + _CYR_UP + r"\.\s+" + _CYR_UP + _CYR_LO,
    ),
    # Format 3: Full name Фамилия Имя [Отчество]  e.g. Иванов Иван Иванович
    # Require all words 3+ chars to avoid false positives on short common words
    (
        "ФИО",
        _CYR_UP + _CYR_LO + r"{2,}\s+" + _CYR_UP + _CYR_LO + r"{2,}(?:\s+" + _CYR_UP + _CYR_LO + r"{4,})?",
    ),
    # Contract / document numbers:  №12345  or  № 12345
    ("ДОГОВОР", r"№\s?\d+[\-/\d]*"),
    # Monetary sums: 1 500 000 руб. / 1500000 руб / 1 500 000,00 ₽
    ("СУММА", r"\d[\d\s]*(?:[.,]\d+)?\s*(?:руб(?:лей|\.)?|₽)"),
    # Dates: 15.03.2024 / 2024-03-15
    ("ДАТА", r"\b(?:\d{2}\.\d{2}\.\d{4}|\d{4}-\d{2}-\d{2})\b"),
]


def _extract_org_core(org_value: str) -> str | None:
    """Extract the bare company name from a full ORG match.

    Examples:
        'ООО "Рексофт"'  -> 'Рексофт'
        "ООО 'Ромашка'" -> 'Ромашка'
        'АО Северсталь'    -> 'Северсталь'
        'ИП Иванов А.А.'    -> None  (person name, skip)
    Returns None if no extractable core is found.
    """
    value = org_value.strip()
    for prefix in sorted(_ORG_PREFIXES, key=len, reverse=True):
        if value.upper().startswith(prefix):
            value = value[len(prefix):].strip()
            break

    if not value:
        return None

    # Remove surrounding quotes
    value = re.sub(r'^[«"\']|[»"\']$', "", value).strip()

    # Skip if looks like a person name (initials pattern: Word A.A.)
    if re.match(r'^[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ]\.){1,2}\s*$', value):
        return None

    if re.match(r'^[А-ЯЁA-Z]', value) and len(value) >= 3:
        return value

    return None


def _org_stem(name: str) -> str:
    """Return the root stem to match inflected forms.

    For Cyrillic words we strip common noun endings to get a stable root.
    We require at least 4 chars in the stem to avoid over-matching short words.
    """
    endings = ["овой", "овый", "евой", "евый", "еской", "еский",
               "овое", "евое", "еское",
               "ами", "ах", "ом", "ой", "ого",
               "ем", "ей", "его",
               "ю", "я", "е", "и", "у", "а"]
    word = name.split()[0]
    lower = word.lower()
    for ending in endings:
        if lower.endswith(ending) and len(lower) - len(ending) >= 4:
            return lower[: len(lower) - len(ending)]
    return lower


def _expand_org_spans(
    text: str,
    spans: list[tuple[int, int, str, str]],
) -> list[tuple[int, int, str, str]]:
    """For every ORG span, find bare-name and inflected occurrences in text
    and add them as additional spans with the same label.
    """
    extra: list[tuple[int, int, str, str]] = []
    existing_starts = {s[0] for s in spans}

    org_spans = [s for s in spans if s[2] == "ОРГ"]
    if not org_spans:
        return spans

    seen_cores: set[str] = set()
    for _, _, _, value in org_spans:
        core = _extract_org_core(value)
        if not core or core.lower() in seen_cores:
            continue
        seen_cores.add(core.lower())

        stem = _org_stem(core)
        if len(stem) < 4:
            continue

        pattern = r'(?<![\wа-яёА-ЯЁ])' + re.escape(stem) + r'[а-яёА-ЯЁA-Za-z]*(?![\wа-яёА-ЯЁA-Za-z])'
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            if m.start() not in existing_starts:
                extra.append((m.start(), m.end(), "ОРГ", m.group()))
                existing_starts.add(m.start())

    return spans + extra


def _regex_entities(text: str) -> list[tuple[int, int, str, str]]:
    """Return list of (start, end, label, value) from regex patterns."""
    found: list[tuple[int, int, str, str]] = []
    for label, pattern in _PATTERNS:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            found.append((m.start(), m.end(), label, m.group()))
    return found


def _natasha_entities(text: str) -> list[tuple[int, int, str, str]]:
    """Return PER and ORG spans from Natasha NER."""
    try:
        from natasha import Segmenter, NewsEmbedding, NewsNERTagger, Doc
        seg = Segmenter()
        emb = NewsEmbedding()
        tagger = NewsNERTagger(emb)
        doc = Doc(text)
        doc.segment(seg)
        doc.tag_ner(tagger)
        label_map = {"PER": "ФИО", "ORG": "ОРГ"}
        result = []
        for span in doc.spans:
            if span.type in label_map:
                result.append((span.start, span.stop, label_map[span.type], text[span.start:span.stop]))
        return result
    except Exception:
        return []


def _presidio_entities(text: str) -> list[tuple[int, int, str, str]]:
    """Return email / phone / IP spans from Presidio pattern recognizers."""
    try:
        from presidio_analyzer.predefined_recognizers import (
            EmailRecognizer, IpRecognizer, PhoneRecognizer,
        )
        label_map = {"EMAIL_ADDRESS": "EMAIL", "IP_ADDRESS": "IP", "PHONE_NUMBER": "ТЕЛЕФОН"}
        recognizers = [EmailRecognizer(), IpRecognizer(), PhoneRecognizer()]
        result = []
        for rec in recognizers:
            hits = rec.analyze(text=text, entities=rec.supported_entities, nlp_artifacts=None)
            for hit in hits:
                label = label_map.get(hit.entity_type, hit.entity_type)
                result.append((hit.start, hit.end, label, text[hit.start:hit.end]))
        return result
    except Exception:
        return []


def _merge_spans(
    spans: list[tuple[int, int, str, str]]
) -> list[tuple[int, int, str, str]]:
    """Sort spans and remove overlapping ones (keep longer span)."""
    spans = sorted(spans, key=lambda s: (s[0], -(s[1] - s[0])))
    merged: list[tuple[int, int, str, str]] = []
    last_end = -1
    for span in spans:
        if span[0] >= last_end:
            merged.append(span)
            last_end = span[1]
    return merged


def detect_entities(
    text: str,
    use_natasha: bool = True,
    use_presidio: bool = True,
    use_regex: bool = True,
    labels: set[str] | None = None,
) -> list[tuple[int, int, str, str]]:
    """Detect all PII entities in text.

    Returns sorted, non-overlapping list of (start, end, label, value).
    If `labels` is provided, only those entity types are returned.
    """
    spans: list[tuple[int, int, str, str]] = []
    if use_regex:
        spans += _regex_entities(text)
    if use_natasha:
        spans += _natasha_entities(text)
    if use_presidio:
        spans += _presidio_entities(text)

    # Expand ORG spans to cover bare-name inflections (e.g. Рексофта, Рексофту)
    spans = _expand_org_spans(text, spans)

    spans = _merge_spans(spans)
    if labels:
        spans = [s for s in spans if s[2] in labels]
    return spans


def anonymize(
    text: str,
    enabled_labels: set[str] | None = None,
) -> tuple[str, dict[str, dict[str, str]]]:
    """Replace detected entities with placeholders.

    Returns:
        anonymized_text: str
        mapping: {label: {placeholder: original_value}}
    """
    spans = detect_entities(text, labels=enabled_labels)

    counters: dict[str, int] = {}
    mapping: dict[str, dict[str, str]] = {}
    value_cache: dict[str, str] = {}

    replacements: list[tuple[int, int, str]] = []
    for start, end, label, value in spans:
        if value in value_cache:
            placeholder = value_cache[value]
        else:
            counters[label] = counters.get(label, 0) + 1
            placeholder = f"[{label}_{counters[label]}]"
            value_cache[value] = placeholder
            mapping.setdefault(label, {})[placeholder] = value
        replacements.append((start, end, placeholder))

    result = text
    for start, end, placeholder in sorted(replacements, key=lambda x: -x[0]):
        result = result[:start] + placeholder + result[end:]

    return result, mapping


def anonymize_extra_terms(
    text: str,
    terms: list[str],
    mapping: dict[str, dict[str, str]],
) -> tuple[str, dict[str, dict[str, str]]]:
    """Replace user-defined extra terms with [СКРЫТО_N] placeholders.

    Matching is case-insensitive. Already-replaced placeholders are skipped.
    Applied after main anonymize() to avoid conflicts with auto-detected entities.
    """
    counter = len(mapping.get("СКРЫТО", {}))
    value_cache: dict[str, str] = {}

    for term in terms:
        term = term.strip()
        if not term:
            continue
        term_lower = term.lower()
        if term_lower in value_cache:
            placeholder = value_cache[term_lower]
        else:
            counter += 1
            placeholder = f"[СКРЫТО_{counter}]"
            value_cache[term_lower] = placeholder
            mapping.setdefault("СКРЫТО", {})[placeholder] = term

        text = re.sub(re.escape(term), placeholder, text, flags=re.IGNORECASE)

    return text, mapping


def restore(anonymized_text: str, mapping: dict[str, Any]) -> str:
    """Replace placeholders back with original values using mapping JSON."""
    result = anonymized_text
    for label_dict in mapping.values():
        for placeholder, original in label_dict.items():
            result = result.replace(placeholder, original)
    return result


def mapping_to_json(mapping: dict[str, dict[str, str]]) -> bytes:
    return json.dumps(mapping, ensure_ascii=False, indent=2).encode("utf-8")


def mapping_from_json(data: bytes | str) -> dict[str, Any]:
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    return json.loads(data)
