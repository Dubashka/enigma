"""Entity resolution for Russian person names using Natasha NER.

Groups values that refer to the same person across all columns in a sheet,
so they receive the same fake value during masking.

Examples of values that resolve to the same entity:
  "Иванов Иван Иванович", "Иванов И.И.", "Иванов" → one group
"""
from __future__ import annotations

import re
from collections import defaultdict

import pandas as pd


# ---------------------------------------------------------------------------
# Natasha setup (lazy init to avoid slow import at module load)
# ---------------------------------------------------------------------------

_segmenter = None
_morph_vocab = None
_names_extractor = None


def _get_natasha():
    global _segmenter, _morph_vocab, _names_extractor
    if _names_extractor is None:
        from natasha import Segmenter, MorphVocab, NamesExtractor
        _segmenter = Segmenter()
        _morph_vocab = MorphVocab()
        _names_extractor = NamesExtractor(_morph_vocab)
    return _segmenter, _morph_vocab, _names_extractor


# ---------------------------------------------------------------------------
# Name parsing
# ---------------------------------------------------------------------------

_ABBR_RE = re.compile(r"^([А-ЯЁ])\.$")  # matches "И."


def _extract_last_name(value: str) -> str | None:
    """Try to extract surname from a value using Natasha NER.

    Returns the surname in nominative case, or None if not found.
    """
    segmenter, morph_vocab, names_extractor = _get_natasha()
    try:
        from natasha import Doc
        doc = Doc(value)
        doc.segment(segmenter)
        doc.tag_morph(morph_vocab)

        for match in names_extractor(value):
            fact = match.fact
            if fact.last:
                return fact.last.capitalize()
            if fact.first:
                return fact.first.capitalize()
    except Exception:
        pass

    # Fallback: first word of 2+ word value that starts with capital Cyrillic
    words = value.strip().split()
    if len(words) >= 2 and re.match(r"^[А-ЯЁ][а-яё]{2,}$", words[0]):
        return words[0].capitalize()

    return None


def _looks_like_person(value: str) -> bool:
    """Quick check: does this value look like it could be a person name?"""
    value = value.strip()
    words = value.split()
    if not words:
        return False
    # At least one word starting with Cyrillic capital
    return any(re.match(r"^[А-ЯЁ]", w) for w in words)


# ---------------------------------------------------------------------------
# Main resolution function
# ---------------------------------------------------------------------------

def build_entity_groups(
    sheets: dict[str, pd.DataFrame],
    mask_config: dict[str, dict[str, str]],
) -> dict[str, str]:
    """Build a mapping: normalized_original_value → canonical_value.

    Values that refer to the same person get the same canonical value
    (the longest / most complete form found).

    Only processes text columns included in mask_config.

    Returns:
        {normalized_value: canonical_value}
        If a value has no match with others, it maps to itself.
    """
    # Collect all unique text values across masked text columns
    # surname_lower → list of (original_value, sheet, col)
    surname_groups: dict[str, list[str]] = defaultdict(list)

    for sheet_name, df in sheets.items():
        config = mask_config.get(sheet_name, {})
        for col, col_type in config.items():
            if col_type != "text" or col not in df.columns:
                continue
            for raw_val in df[col].dropna().unique():
                val_str = str(raw_val).strip()
                if not _looks_like_person(val_str):
                    continue
                last = _extract_last_name(val_str)
                if last:
                    surname_groups[last.lower()].append(val_str)

    # Build canonical map: pick the longest value as canonical for each group
    canonical: dict[str, str] = {}
    for surname, values in surname_groups.items():
        if len(values) <= 1:
            continue  # no grouping needed
        # Canonical = longest string (most complete form)
        canon = max(values, key=len)
        for val in values:
            if val != canon:
                canonical[val] = canon

    return canonical
