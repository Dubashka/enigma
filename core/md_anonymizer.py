"""MD text anonymization and restoration logic.

Detects PII entities using Natasha (PER, ORG) + Presidio (email, phone, IP)
+ regex (contract numbers, sums, dates, legal entities, person names with initials, addresses).
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

# Cyrillic helpers (no quantifier — add explicitly per pattern)
_C  = r'[А-ЯЁ]'   # one uppercase Cyrillic letter
_cl = r'[а-яё]'   # one lowercase Cyrillic letter

# ---------------------------------------------------------------------------
# Address building blocks
# ---------------------------------------------------------------------------
# Street-type keywords: ул., улица, пр., проспект, пер., наб., шоссе, пл., площадь, б-р, бульвар, проезд, тупик
_STREET_KW = (
    r'(?:ул(?:\.|[и]ца)'
    r'|пр(?:\.|[о]спект)'
    r'|пер(?:\.|[е]улок)'
    r'|наб(?:\.|[е]режная)'
    r'|шоссе'
    r'|пл(?:\.|[о]щадь)'
    r'|б(?:-р|ульвар)'
    r'|проезд'
    r'|тупик)'
)
# Street name: 1-4 words (letters, digits, hyphens)
_STREET_NAME = r'[А-ЯЁа-яё0-9][\wа-яёА-ЯЁ\-]*(?:\s+[А-ЯЁа-яё0-9][\wа-яёА-ЯЁ\-]*){0,3}'
# House / building / office suffixes
_HOUSE = r'(?:,?\s*д(?:\.|ом\.?)\s*\d+[\w\-/]*)'
_BLDG  = r'(?:,?\s*(?:к(?:\.|орп\.?)|стр(?:\.)?)\s*\d+[\w\-/]*)'
_FLAT  = r'(?:,?\s*(?:кв(?:\.|арт\.?)|оф(?:\.)?)\s*\d+)'
# City/settlement prefixes
_CITY_KW = r'(?:г(?:\.|[о]род)|п(?:\.|[о]с(?:\.|[е]лок))|с(?:\.|[е]ло)|д(?:\.|[е]ревня))'
_CITY_NAME = r'[А-ЯЁ][а-яёА-ЯЁ\-]+(?:-[А-ЯЁ][а-яёА-ЯЁ\-]+)*'

_PATTERNS: list[tuple[str, str]] = [
    # Email — before phone to avoid partial overlap
    ("EMAIL", r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"),
    # Russian mobile / landline phones
    ("ТЕЛЕФОН", r"(?<!\d)(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}(?!\d)"),
    # IPv4
    ("IP", r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    # Russian legal entities
    (
        "ОРГ",
        r"(?:" + _ORG_PREFIX_RE + r")"
        r"(?:"
        r"\s+" + _ORG_OPEN + r"[А-ЯЁа-яёA-Za-z0-9][\w\s\-]*?" + _ORG_CLOSE
        + r"|\s+[А-ЯЁ][а-яёА-ЯЁ\w\-]{1,40}(?:\s+[А-ЯЁ][а-яёА-ЯЁ\w\-]{1,40}){0,3}"
        + r")?",
    ),
    # ---- Person name formats (ФИО) — initials-based, high precision ----
    # Format 1: Фамилия И.О. / Фамилия И.  e.g. Скорочкина А.А.
    (
        "ФИО",
        _C + _cl + r"+\s+" + _C + r"\.(?:" + _C + r"\.)?",
    ),
    # Format 2: И.О. Фамилия  e.g. А.А. Скорочкина
    (
        "ФИО",
        _C + r"\." + _C + r"\.\s+" + _C + _cl + r"+",
    ),
    # ---- Address patterns (АДРЕС) ----
    # Format A: г. Москва, ул. Ленина, д. 5[, кв. 12]
    (
        "АДРЕС",
        _CITY_KW + r"\s+" + _CITY_NAME + r",\s*" + _STREET_KW + r"\s+" + _STREET_NAME + _HOUSE + r"?" + _BLDG + r"?" + _FLAT + r"?",
    ),
    # Format B: ул. Ленина, д. 5[, к. 2][, кв. 12]  (no city prefix)
    (
        "АДРЕС",
        _STREET_KW + r"\s+" + _STREET_NAME + r",\s*" + _HOUSE[len(r"(?:,?\s*"):],
    ),
    # Postal index (Format C) intentionally omitted — too many false positives.
    #
    # Contract / document numbers
    ("ДОГОВОР", r"№\s?\d+[\-/\d]*"),
    # Monetary sums
    ("СУММА", r"\d[\d\s]*(?:[.,]\d+)?\s*(?:руб(?:лей|\.)?|₽)"),
    # Dates: 15.03.2024 / 2024-03-15
    ("ДАТА", r"\b(?:\d{2}\.\d{2}\.\d{4}|\d{4}-\d{2}-\d{2})\b"),
]

# Sentinel prefix injected around each line when feeding to Natasha.
_NER_PREFIX = "Работник "
_NER_PREFIX_LEN = len(_NER_PREFIX)


def _extract_org_core(org_value: str) -> str | None:
    """Extract the bare company name from a full ORG match."""
    value = org_value.strip()
    for prefix in sorted(_ORG_PREFIXES, key=len, reverse=True):
        if value.upper().startswith(prefix):
            value = value[len(prefix):].strip()
            break
    if not value:
        return None
    value = re.sub(r'^[«"\']|[»"\']$', "", value).strip()
    if re.match(r'^[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ]\.){1,2}\s*$', value):
        return None
    if re.match(r'^[А-ЯЁA-Z]', value) and len(value) >= 3:
        return value
    return None


def _org_stem(name: str) -> str:
    """Return the root stem to match inflected forms."""
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
    """For every ORG span add inflected bare-name occurrences."""
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
    found: list[tuple[int, int, str, str]] = []
    for label, pattern in _PATTERNS:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            found.append((m.start(), m.end(), label, m.group()))
    return found


def _natasha_entities(text: str) -> list[tuple[int, int, str, str]]:
    """Run Natasha NER on full text (catches names inside sentences)."""
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


def _natasha_entities_per_line(text: str) -> list[tuple[int, int, str, str]]:
    """Run Natasha line-by-line with a context prefix to catch isolated full names."""
    try:
        from natasha import Segmenter, NewsEmbedding, NewsNERTagger, Doc
        seg = Segmenter()
        emb = NewsEmbedding()
        tagger = NewsNERTagger(emb)
    except Exception:
        return []

    result: list[tuple[int, int, str, str]] = []
    label_map = {"PER": "ФИО", "ORG": "ОРГ"}

    line_offset = 0
    for raw_line in text.split("\n"):
        stripped = raw_line.strip()
        if stripped and re.match(
            r'^[А-ЯЁ][а-яёА-ЯЁ\-]+(?:\s+[А-ЯЁ][а-яёА-ЯЁ\-]+){1,3}$',
            stripped
        ):
            probe = _NER_PREFIX + stripped
            try:
                doc = Doc(probe)
                doc.segment(seg)
                doc.tag_ner(tagger)
                for span in doc.spans:
                    if span.type not in label_map:
                        continue
                    if span.start < _NER_PREFIX_LEN:
                        continue
                    orig_start = line_offset + (span.start - _NER_PREFIX_LEN)
                    orig_end   = line_offset + (span.stop  - _NER_PREFIX_LEN)
                    value = text[orig_start:orig_end]
                    result.append((orig_start, orig_end, label_map[span.type], value))
            except Exception:
                pass

        line_offset += len(raw_line) + 1

    return result


def _presidio_entities(text: str) -> list[tuple[int, int, str, str]]:
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
    """Detect all PII entities in text."""
    spans: list[tuple[int, int, str, str]] = []
    if use_regex:
        spans += _regex_entities(text)
    if use_natasha:
        spans += _natasha_entities(text)
        spans += _natasha_entities_per_line(text)
    if use_presidio:
        spans += _presidio_entities(text)
    spans = _expand_org_spans(text, spans)
    spans = _merge_spans(spans)
    if labels:
        spans = [s for s in spans if s[2] in labels]
    return spans


def anonymize(
    text: str,
    enabled_labels: set[str] | None = None,
) -> tuple[str, dict[str, dict[str, str]]]:
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
