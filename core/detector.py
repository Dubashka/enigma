"""Keyword-based column detection and type classification (DETC-01, DETC-03)."""
from __future__ import annotations

import pandas as pd


def _natasha_person_columns(df: pd.DataFrame) -> list[str]:
    """Detect columns where majority of values contain Russian person names (Natasha NER).

    Returns empty list if natasha is not installed or raises any error.
    """
    try:
        from natasha import Segmenter, NewsEmbedding, NewsNERTagger, Doc

        segmenter = Segmenter()
        emb = NewsEmbedding()
        ner_tagger = NewsNERTagger(emb)

        found: list[str] = []
        for col in df.columns:
            sample = df[col].dropna().astype(str).unique()[:10]
            if len(sample) == 0:
                continue
            person_hits = 0
            for val in sample:
                doc = Doc(val)
                doc.segment(segmenter)
                doc.tag_ner(ner_tagger)
                if any(span.type == "PER" for span in doc.spans):
                    person_hits += 1
            # Lock column if more than half the sampled values contain a person name
            if person_hits > 0 and person_hits >= len(sample) / 2:
                found.append(col)
        return found
    except Exception:
        return []


def _presidio_sensitive_columns(df: pd.DataFrame) -> list[str]:
    """Scan column values for PII patterns (email, phone, IP) using presidio regex recognizers.

    Works without a spaCy model — pattern-based only.
    Returns empty list if presidio is not installed or raises any error.
    """
    try:
        from presidio_analyzer.predefined_recognizers import (
            EmailRecognizer,
            IpRecognizer,
            PhoneRecognizer,
        )

        recognizers = [EmailRecognizer(), IpRecognizer(), PhoneRecognizer()]
        found: list[str] = []

        for col in df.columns:
            sample = df[col].dropna().astype(str).unique()[:20]
            for val in sample:
                for rec in recognizers:
                    hits = rec.analyze(
                        text=val,
                        entities=rec.supported_entities,
                        nlp_artifacts=None,
                    )
                    if hits:
                        found.append(col)
                        break
                else:
                    continue
                break  # column already flagged, move to next

        return found
    except Exception:
        return []


# Keywords that trigger sensitive column detection
# Source: real file analysis (Данные для маскирования_13.03.xlsx) + domain knowledge
SENSITIVE_KEYWORDS = [
    # Company / contractor names — seen in real file
    "предприятие", "контрагент", "поставщик", "рабочее место",
    "организация", "компания", "подрядчик", "исполнитель",
    # Person / author names — seen in real file
    "фио", "имя", "сотрудник", "создал", "обнаружил",
    "автор", "ответственный",
    # Financial values
    "сумма", "цена", "стоимость", "тариф",
    # Contract / document identifiers (text-masked, not coefficient)
    "договор", "контракт", "номер", "документ", "счёт", "счет",
    "заказ", "заявка", "сообщение", "карточка",
]

# Keywords in numeric-dtype column names that force text masking (MASK-04)
# Source: CONTEXT.md locked decisions + real file analysis
NUMERIC_ID_KEYWORDS = [
    "документ", "договор", "контракт", "номер", "заказ", "заявка",
    "сообщение", "карточка", "счёт", "счет", "код", "артикул",
    "вагон", "позиция", "id", "№",
]


def detect_sensitive_columns(
    sheets: dict[str, pd.DataFrame],
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Return (detected, presidio_required).

    detected:         {sheet_name: [col_names]} — all suggested columns (keyword + presidio + library)
    presidio_required:{sheet_name: [col_names]} — only presidio-found columns (must mask, locked)
    """
    # Columns previously masked — from persistent library
    try:
        from core.library import AttributeLibrary
        known_columns = set(AttributeLibrary().get_known_columns())
    except Exception:
        known_columns = set()

    result: dict[str, list[str]] = {}
    presidio_result: dict[str, list[str]] = {}

    for sheet_name, df in sheets.items():
        sensitive: list[str] = []
        for col in df.columns:
            col_lower = str(col).lower()
            if any(kw in col_lower for kw in SENSITIVE_KEYWORDS):
                sensitive.append(col)

        # Presidio pattern detection (actual cell values: email, phone, IP)
        presidio_cols = _presidio_sensitive_columns(df)

        # Natasha NER — columns where values are Russian person names
        natasha_cols = _natasha_person_columns(df)
        if natasha_cols:
            print(f"[Natasha] Колонки с ФИО на листе '{sheet_name}': {natasha_cols}")

        # Merge: required = presidio + natasha
        required_cols = list(dict.fromkeys(presidio_cols + natasha_cols))

        for col in required_cols:
            if col not in sensitive:
                sensitive.append(col)

        # Library-based detection — columns masked in previous sessions
        for col in df.columns:
            if col in known_columns and col not in sensitive:
                sensitive.append(col)

        result[sheet_name] = sensitive
        presidio_result[sheet_name] = required_cols

    return result, presidio_result


def classify_column_type(col_name: str, series: pd.Series) -> str:
    """Return 'text' or 'numeric' for a given column.

    Rules:
    - object / non-numeric dtype -> 'text' (always)
    - numeric dtype + name matches NUMERIC_ID_KEYWORDS -> 'text'
    - numeric dtype + no ID keyword match -> 'numeric'
    """
    col_lower = str(col_name).lower()
    if pd.api.types.is_numeric_dtype(series):
        if any(kw in col_lower for kw in NUMERIC_ID_KEYWORDS):
            return "text"
        return "numeric"
    return "text"
