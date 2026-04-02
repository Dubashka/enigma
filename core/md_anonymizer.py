"""MD text anonymization and restoration logic.

Detects PII entities using Natasha (PER, ORG) + Presidio (email, phone, IP)
+ regex (contract numbers, sums, dates) and replaces them with placeholders.
Mapping JSON allows full restoration.
"""
from __future__ import annotations

import json
import re
from typing import Any

# ---------------------------------------------------------------------------
# Regex patterns for structured PII
# ---------------------------------------------------------------------------
_PATTERNS: list[tuple[str, str]] = [
    # Email — before phone to avoid partial overlap
    ("EMAIL", r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"),
    # Russian mobile / landline phones
    ("ТЕЛЕФОН", r"(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}"),
    # IPv4
    ("IP", r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    # Contract / document numbers:  №12345  or  № 12345
    ("ДОГОВОР", r"№\s?\d+[\-/\d]*"),
    # Monetary sums: 1 500 000 руб. / 1500000 руб / 1 500 000,00 ₽
    ("СУММА", r"\d[\d\s]*(?:[.,]\d+)?\s*(?:руб(?:лей|\.)?|₽)"),
    # Dates: 15.03.2024 / 2024-03-15
    ("ДАТА", r"\b(?:\d{2}\.\d{2}\.\d{4}|\d{4}-\d{2}-\d{2})\b"),
]


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
    if use_natasha:
        spans += _natasha_entities(text)
    if use_presidio:
        spans += _presidio_entities(text)
    if use_regex:
        spans += _regex_entities(text)
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
    # value -> placeholder cache to reuse same placeholder for same value
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

    # Build anonymized text (process spans right-to-left to preserve indices)
    result = text
    for start, end, placeholder in sorted(replacements, key=lambda x: -x[0]):
        result = result[:start] + placeholder + result[end:]

    return result, mapping


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
