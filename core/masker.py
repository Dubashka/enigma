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

def _normalize_key(value: str) -> str:
    """NFC normalization + strip + uppercase + remove quote variants + collapse spaces."""
    s = unicodedata.normalize("NFC", str(value))
    s = s.strip().upper()
    s = re.sub(r'["\u201c\u201d\u00ab\u00bb\u2018\u2019\']', "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _normalize_original(value: str) -> str:
    """NFC normalization + strip + remove quote variants + collapse spaces (preserves casing)."""
    s = unicodedata.normalize("NFC", str(value))
    s = s.strip()
    s = re.sub(r'["\u201c\u201d\u00ab\u00bb\u2018\u2019\']', "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _normalize(value: str) -> str:
    return _normalize_key(value)


def _normalize_suffix(word: str) -> str:
    w = word.lower()
    if w.endswith("ия"):
        return word[:-2] + "ие"
    return word


def _derive_prefix(col_name: str) -> str:
    words = col_name.split()
    meaningful = [w for w in words if w.lower() not in _SKIP_WORDS]
    if meaningful:
        word = _normalize_suffix(meaningful[0])
        return word.capitalize()
    return words[0].capitalize() if words else col_name.capitalize()


def _index_to_label(n: int) -> str:
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
    """Build a single shared text mapping: {original_value -> pseudonym}."""
    mapping: dict[str, str] = {}
    seen_keys: set[str] = set()
    counters: dict[str, int] = {}

    for sheet_name, df in sheets.items():
        config = mask_config.get(sheet_name, {})
        for col, col_type in config.items():
            if col_type != "text" or col not in df.columns:
                continue
            prefix = _derive_prefix(col)
            for raw_val in df[col].dropna().unique():
                norm_key = _normalize_key(str(raw_val))
                if norm_key not in seen_keys:
                    seen_keys.add(norm_key)
                    counters[prefix] = counters.get(prefix, 0) + 1
                    original = _normalize_original(str(raw_val))
                    mapping[original] = f"{prefix} {_index_to_label(counters[prefix])}"
    return mapping


def build_numeric_mapping(
    sheets: dict[str, pd.DataFrame],
    mask_config: dict[str, dict[str, str]],
) -> dict[str, float]:
    """Build {col_name -> coefficient} where coefficient in [0.5, 1.5]."""
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
    """Vectorized text substitution. NaN cells remain NaN.

    Performance: builds raw->pseudonym lookup in a single pass using
    pre-normalised keys — no nested loops or repeated dict scans.
    """
    # Pre-build uppercase key -> pseudonym for O(1) lookup
    key_to_pseudo: dict[str, str] = {
        _normalize_key(k): v for k, v in mapping.items()
    }

    # Build raw_value -> pseudonym for every unique value in this series
    raw_lookup: dict = {}
    for raw_val in series.dropna().unique():
        norm_key = _normalize_key(str(raw_val))
        pseudo = key_to_pseudo.get(norm_key)
        if pseudo is not None:
            raw_lookup[raw_val] = pseudo

    if not raw_lookup:
        return series

    return series.map(lambda v: raw_lookup.get(v, v) if not pd.isna(v) else v)


def apply_numeric_masking(series: pd.Series, multiplier: float) -> pd.Series:
    """Multiply by coefficient. Integer series stay integer (no float noise)."""
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
    """Mask all sheets according to mask_config."""
    text_mapping = build_text_mapping(sheets, mask_config)
    numeric_mapping = build_numeric_mapping(sheets, mask_config)

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
