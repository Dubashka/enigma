"""Text pseudonymization and numeric perturbation masking engine (MASK-01..04).

Key design decisions:
- Single shared mapping dict built before any sheet is processed
  (CRITICAL for cross-sheet consistency — see PITFALLS.md Pitfall 1)
- Vectorized via pd.Series.map() — no iterrows()
- NaN values are skipped (not masked, not added to mapping)
- Integer columns stay integer after numeric masking (Int64 nullable)
"""
from __future__ import annotations

import random
import re
import unicodedata

import pandas as pd


# Words to skip when deriving the prefix from a column name
_SKIP_WORDS = {
    "имя", "наименование", "название", "номер", "внеш", "внешний",
    "рабочего",  # "рабочего места" — skip "рабочего", keep "места"
}


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def _normalize(value: str) -> str:
    """NFC normalization + strip + uppercase + remove quote variants + collapse spaces."""
    s = unicodedata.normalize("NFC", str(value))
    s = s.strip().upper()
    # Remove all quote variants: curly, guillemets, apostrophe, straight
    s = re.sub(r'["\u201c\u201d\u00ab\u00bb\u2018\u2019\']', "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _normalize_suffix(word: str) -> str:
    """Convert common Russian genitive suffixes to nominative for cleaner prefixes.

    Examples:
        "предприятия" -> "предприятие"
        "изменения"   -> "изменение"
        "места"       -> "место"
    """
    w = word.lower()
    if w.endswith("ия"):
        return word[:-2] + "ие"
    if w.endswith("ия"):
        return word[:-2] + "ие"
    return word


def _derive_prefix(col_name: str) -> str:
    """Derive a human-readable prefix from a column name.

    Algorithm: split by spaces, filter out _SKIP_WORDS (case-insensitive),
    take the first remaining word, apply suffix normalization, and capitalize it.
    Fallback: first word of col_name capitalized.

    Examples:
        "Имя предприятия"            -> "Предприятие" (skip "имя", normalize genitive)
        "Наименование рабочего места" -> "Рабочего" (skip "наименование", take first remaining)
        "Автор изменения"            -> "Автор" (no skips, take first word)
    """
    words = col_name.split()
    meaningful = [w for w in words if w.lower() not in _SKIP_WORDS]
    if meaningful:
        word = _normalize_suffix(meaningful[0])
        return word.capitalize()
    # Fallback: first word
    return words[0].capitalize() if words else col_name.capitalize()


def _index_to_label(n: int) -> str:
    """Convert 1-based integer to Excel-column-style letter label.

    1 -> A, 2 -> B, 26 -> Z, 27 -> AA, 28 -> AB, ...
    """
    label = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        label = chr(65 + remainder) + label
    return label


# ---------------------------------------------------------------------------
# Mapping builders
# ---------------------------------------------------------------------------

def build_text_mapping(
    sheets: dict[str, pd.DataFrame],
    mask_config: dict[str, dict[str, str]],
) -> dict[str, str]:
    """Build a single shared text mapping: {normalized_value -> pseudonym}.

    CRITICAL: This must be called once before any sheet is processed.
    The mapping and counters are global across all sheets to guarantee
    cross-sheet consistency (same original value -> same pseudonym everywhere).
    """
    mapping: dict[str, str] = {}
    counters: dict[str, int] = {}  # prefix -> current count (global)

    for sheet_name, df in sheets.items():
        config = mask_config.get(sheet_name, {})
        for col, col_type in config.items():
            if col_type != "text" or col not in df.columns:
                continue
            prefix = _derive_prefix(col)
            for raw_val in df[col].dropna().unique():
                key = _normalize(str(raw_val))
                if key not in mapping:
                    counters[prefix] = counters.get(prefix, 0) + 1
                    mapping[key] = f"{prefix} {_index_to_label(counters[prefix])}"
    return mapping


def build_numeric_mapping(
    sheets: dict[str, pd.DataFrame],
    mask_config: dict[str, dict[str, str]],
) -> dict[str, float]:
    """Build {col_name -> coefficient} where coefficient in [0.5, 1.5].

    One coefficient per unique column name, shared across all sheets.
    """
    numeric_cols: set[str] = set()
    for config in mask_config.values():
        for col, col_type in config.items():
            if col_type == "numeric":
                numeric_cols.add(col)
    return {col: random.uniform(0.5, 1.5) for col in numeric_cols}


# ---------------------------------------------------------------------------
# Masking application
# ---------------------------------------------------------------------------

def apply_text_masking(series: pd.Series, mapping: dict[str, str]) -> pd.Series:
    """Vectorized text substitution. NaN cells remain NaN."""
    def lookup(v):
        if pd.isna(v):
            return v
        return mapping.get(_normalize(str(v)), v)

    return series.map(lookup)


def apply_numeric_masking(series: pd.Series, multiplier: float) -> pd.Series:
    """Multiply by coefficient. Integer series stay integer (no float noise).

    Uses nullable Int64 to correctly handle potential NaN in integer columns.
    """
    result = series * multiplier
    if pd.api.types.is_integer_dtype(series):
        return result.round().astype("Int64")
    return result.round(2)


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def mask_sheets(
    sheets: dict[str, pd.DataFrame],
    mask_config: dict[str, dict[str, str]],
) -> tuple[dict[str, pd.DataFrame], dict, dict]:
    """Mask all sheets according to mask_config.

    Args:
        sheets: {sheet_name: DataFrame} — original data
        mask_config: {sheet_name: {col_name: "text"|"numeric"}}

    Returns:
        (masked_sheets, mapping, stats) where:
        - masked_sheets: {sheet_name: masked DataFrame}
        - mapping: {"text": {norm_val: pseudonym}, "numeric": {col: multiplier}}
        - stats: {"masked_values": int, "unique_entities": int}
    """
    # Phase A: Build shared mappings (single pass, all sheets)
    text_mapping = build_text_mapping(sheets, mask_config)
    numeric_mapping = build_numeric_mapping(sheets, mask_config)

    # Phase B: Apply masking sheet by sheet
    masked_sheets: dict[str, pd.DataFrame] = {}
    masked_values_count = 0

    for sheet_name, df in sheets.items():
        masked_df = df.copy()
        config = mask_config.get(sheet_name, {})

        for col, col_type in config.items():
            if col not in masked_df.columns:
                continue
            non_nan_count = masked_df[col].notna().sum()
            masked_values_count += int(non_nan_count)

            if col_type == "text":
                masked_df[col] = apply_text_masking(masked_df[col], text_mapping)
            elif col_type == "numeric" and col in numeric_mapping:
                masked_df[col] = apply_numeric_masking(masked_df[col], numeric_mapping[col])

        masked_sheets[sheet_name] = masked_df

    stats = {
        "masked_values": masked_values_count,
        "unique_entities": len(text_mapping),
    }
    combined_mapping = {"text": text_mapping, "numeric": numeric_mapping}
    return masked_sheets, combined_mapping, stats
