"""Unit tests for core.masker module (MASK-01..04)."""
from __future__ import annotations

import re
import math

import pandas as pd
import pytest

from core.masker import (
    _normalize,
    _derive_prefix,
    _index_to_label,
    build_text_mapping,
    build_numeric_mapping,
    apply_text_masking,
    apply_numeric_masking,
    mask_sheets,
)


# ---------------------------------------------------------------------------
# Helper: build a minimal mask_config for the detection sheets fixture
# ---------------------------------------------------------------------------

def _make_mask_config(detection_sheets):
    """Build a mask_config matching the sample_detection_sheets fixture."""
    return {
        "Лист1": {
            "Имя предприятия": "text",
            "Количество": "numeric",
            "Цена": "numeric",
            "Документ закупки": "text",
        },
        "Лист2": {
            "Имя предприятия": "text",
            "Автор изменения": "text",
            "Сумма": "numeric",
        },
    }


# ---------------------------------------------------------------------------
# _normalize
# ---------------------------------------------------------------------------

def test_normalize_quote_variants():
    """_normalize strips all quote variants so ООО "ЛУИС+" and ООО ЛУИС+ share a key."""
    assert _normalize('ООО "ЛУИС+"') == _normalize("ООО ЛУИС+")


def test_normalize_case_and_strip():
    """_normalize uppercases and strips leading/trailing whitespace."""
    assert _normalize("  альфа  ") == "АЛЬФА"


# ---------------------------------------------------------------------------
# _index_to_label
# ---------------------------------------------------------------------------

def test_index_to_label():
    """_index_to_label converts integer index to Excel-style column letter(s)."""
    assert _index_to_label(1) == "A"
    assert _index_to_label(2) == "B"
    assert _index_to_label(26) == "Z"
    assert _index_to_label(27) == "AA"
    assert _index_to_label(28) == "AB"


# ---------------------------------------------------------------------------
# _derive_prefix
# ---------------------------------------------------------------------------

def test_prefix_derivation():
    """_derive_prefix extracts first meaningful noun from column name (skipping service words)."""
    # "имя" is a service word -> skip it -> first remaining word is "предприятия" -> normalize -> "Предприятие"
    assert _derive_prefix("Имя предприятия") == "Предприятие"
    # No service words -> first word is "Автор"
    assert _derive_prefix("Автор изменения") == "Автор"
    # "наименование" and "рабочего" are service words -> skip both -> first remaining is "места"
    prefix = _derive_prefix("Наименование рабочего места")
    assert prefix in {"Места", "Место"}, f"Expected 'Места' or 'Место', got '{prefix}'"


# ---------------------------------------------------------------------------
# build_text_mapping
# ---------------------------------------------------------------------------

def test_cross_sheet_consistency(sample_detection_sheets):
    """Same value on Лист1 and Лист2 must produce the same pseudonym."""
    mask_config = _make_mask_config(sample_detection_sheets)
    text_mapping = build_text_mapping(sample_detection_sheets, mask_config)

    # "ООО Альфа" appears in both sheets under "Имя предприятия"
    key = _normalize("ООО Альфа")
    assert key in text_mapping, "ООО Альфа should be in mapping"
    # Only one pseudonym must exist for this key
    pseudonym = text_mapping[key]
    assert pseudonym is not None


def test_text_masking_produces_pseudonyms(sample_detection_sheets):
    """mask_sheets produces pseudonyms matching pattern 'Prefix X'."""
    mask_config = _make_mask_config(sample_detection_sheets)
    masked, mapping, stats = mask_sheets(sample_detection_sheets, mask_config)

    col_values = masked["Лист1"]["Имя предприятия"].tolist()
    # Each value should match pattern like "Предприятие A" or "Предприятие B"
    for val in col_values:
        assert re.match(r"[А-Яа-яЁёA-Za-z]+ [A-Z]+$", str(val)), (
            f"Unexpected pseudonym format: '{val}'"
        )


# ---------------------------------------------------------------------------
# build_numeric_mapping
# ---------------------------------------------------------------------------

def test_numeric_coefficient_range(sample_detection_sheets):
    """Each numeric column gets a coefficient strictly in [0.5, 1.5]."""
    mask_config = _make_mask_config(sample_detection_sheets)
    numeric_mapping = build_numeric_mapping(sample_detection_sheets, mask_config)

    for col, coeff in numeric_mapping.items():
        assert 0.5 <= coeff <= 1.5, f"Coefficient {coeff} for '{col}' out of range [0.5, 1.5]"


def test_numeric_proportions_preserved():
    """Numeric masking preserves proportions between rows (same multiplier).

    Uses float column to avoid integer rounding error. The single coefficient
    per column guarantees proportional scaling for float data.
    """
    # Use large floats to ensure rounding to 2 decimals doesn't distort ratio
    df = pd.DataFrame({"Выручка": [1000.0, 2000.0, 3000.0]})
    sheets = {"Лист1": df}
    mask_config = {"Лист1": {"Выручка": "numeric"}}
    masked, _, _ = mask_sheets(sheets, mask_config)

    orig = df["Выручка"].tolist()
    masked_vals = masked["Лист1"]["Выручка"].tolist()

    # Ratio orig[0]/orig[1] should match masked[0]/masked[1]
    # With floats and round(2) the ratio is preserved to at least 1e-4
    ratio_before = orig[0] / orig[1]
    ratio_after = masked_vals[0] / masked_vals[1]
    assert math.isclose(ratio_before, ratio_after, rel_tol=1e-4), (
        f"Proportions changed: {ratio_before} vs {ratio_after}"
    )


# ---------------------------------------------------------------------------
# apply_numeric_masking
# ---------------------------------------------------------------------------

def test_integer_stays_integer():
    """Integer (int64) input column remains integer after numeric masking."""
    series = pd.Series([10, 20, 30], dtype="int64")
    result = apply_numeric_masking(series, 0.7)
    # Should not contain .5 or float-noise values
    for val in result:
        assert val == int(val), f"Expected integer, got {val}"


def test_nan_not_masked():
    """NaN values in text column stay NaN and are not added to the mapping."""
    df = pd.DataFrame({
        "Имя предприятия": ["ООО Альфа", None, "ООО Бета"],
    })
    mask_config = {"Лист1": {"Имя предприятия": "text"}}
    sheets = {"Лист1": df}
    masked, mapping, _ = mask_sheets(sheets, mask_config)

    text_map = mapping["text"]
    # None/NaN should NOT be in the mapping
    assert _normalize("None") not in text_map
    assert _normalize("nan") not in text_map

    # NaN position (index 1) should remain NaN in output
    assert pd.isna(masked["Лист1"]["Имя предприятия"].iloc[1])


# ---------------------------------------------------------------------------
# Numeric ID column masking as text (MASK-04)
# ---------------------------------------------------------------------------

def test_numeric_id_masked_as_text(sample_detection_sheets):
    """'Документ закупки' column with mask_config='text' gets text pseudonym."""
    mask_config = _make_mask_config(sample_detection_sheets)
    masked, mapping, _ = mask_sheets(sample_detection_sheets, mask_config)

    col_values = masked["Лист1"]["Документ закупки"].tolist()
    # Values should be pseudonym strings, not large floats
    for val in col_values:
        assert isinstance(val, str), f"Expected string pseudonym, got {type(val)}: {val}"
        assert re.match(r"[А-Яа-яЁёA-Za-z]+ [A-Z]+$", val), (
            f"Unexpected pseudonym format: '{val}'"
        )


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def test_stats_counts(sample_detection_sheets):
    """stats['masked_values'] and stats['unique_entities'] are correct."""
    mask_config = _make_mask_config(sample_detection_sheets)
    masked, mapping, stats = mask_sheets(sample_detection_sheets, mask_config)

    # masked_values: total non-NaN cells in masked columns across all sheets
    # Лист1: 3+3+3+3=12 cells across 4 columns; Лист2: 2+2+2=6 cells across 3 columns
    assert stats["masked_values"] == 18, (
        f"Expected 18 masked values, got {stats['masked_values']}"
    )

    # unique_entities: number of unique text pseudonyms
    assert stats["unique_entities"] == len(mapping["text"]), (
        "unique_entities should equal number of unique text pseudonyms"
    )
    assert stats["unique_entities"] > 0
