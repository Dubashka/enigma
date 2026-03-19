"""Unit tests for core/decryptor.py — decryption engine (DECR-01, DECR-02, DECR-03)."""
import io
import json

import numpy as np
import pandas as pd
import pytest

from core.decryptor import decrypt_sheets, load_mapping_json


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

MAPPING = {
    "text": {"ООО АЛЬФА": "Предприятие A", "ООО БЕТА": "Предприятие B"},
    "numeric": {"Сумма": 1.5},
}


# ---------------------------------------------------------------------------
# load_mapping_json
# ---------------------------------------------------------------------------

def test_load_mapping_valid():
    buf = io.BytesIO(json.dumps(MAPPING).encode("utf-8"))
    result = load_mapping_json(buf)
    assert result is not None
    assert "text" in result
    assert "numeric" in result


def test_load_mapping_invalid():
    buf = io.BytesIO(b"not json")
    result = load_mapping_json(buf)
    assert result is None


# ---------------------------------------------------------------------------
# decrypt_sheets — text decryption
# ---------------------------------------------------------------------------

def test_decrypt_text_values():
    df = pd.DataFrame({"Контрагент": ["Предприятие A", "Предприятие B", None]})
    sheets = {"Sheet1": df}
    result = decrypt_sheets(sheets, MAPPING)
    decrypted_col = result["Sheet1"]["Контрагент"]
    assert decrypted_col.iloc[0] == "ООО АЛЬФА"
    assert decrypted_col.iloc[1] == "ООО БЕТА"


# ---------------------------------------------------------------------------
# decrypt_sheets — numeric decryption
# ---------------------------------------------------------------------------

def test_decrypt_numeric_values():
    df = pd.DataFrame({"Сумма": [150.0, 300.0, None]})
    sheets = {"Sheet1": df}
    result = decrypt_sheets(sheets, MAPPING)
    col = result["Sheet1"]["Сумма"]
    assert abs(col.iloc[0] - 100.0) < 0.01
    assert abs(col.iloc[1] - 200.0) < 0.01


# ---------------------------------------------------------------------------
# NaN passthrough
# ---------------------------------------------------------------------------

def test_decrypt_nan_passthrough():
    df = pd.DataFrame({
        "Контрагент": ["Предприятие A", None],
        "Сумма": [150.0, None],
    })
    sheets = {"Sheet1": df}
    result = decrypt_sheets(sheets, MAPPING)
    sheet = result["Sheet1"]
    assert pd.isna(sheet["Контрагент"].iloc[1])
    assert pd.isna(sheet["Сумма"].iloc[1])


# ---------------------------------------------------------------------------
# Unknown values and columns passthrough
# ---------------------------------------------------------------------------

def test_decrypt_unknown_values_passthrough():
    # "New Corp" is not in the reverse text mapping — must pass through unchanged
    df = pd.DataFrame({"Контрагент": ["Предприятие A", "New Corp"]})
    sheets = {"Sheet1": df}
    result = decrypt_sheets(sheets, MAPPING)
    col = result["Sheet1"]["Контрагент"]
    assert col.iloc[0] == "ООО АЛЬФА"
    assert col.iloc[1] == "New Corp"


def test_decrypt_unknown_columns_passthrough():
    # "LLM Added" is not in mapping — values must be unchanged
    df = pd.DataFrame({"LLM Added": ["yes", "no"]})
    sheets = {"Sheet1": df}
    result = decrypt_sheets(sheets, MAPPING)
    col = result["Sheet1"]["LLM Added"]
    assert col.tolist() == ["yes", "no"]


# ---------------------------------------------------------------------------
# Multi-sheet
# ---------------------------------------------------------------------------

def test_decrypt_multi_sheet():
    df1 = pd.DataFrame({"Контрагент": ["Предприятие A"]})
    df2 = pd.DataFrame({"Сумма": [150.0]})
    sheets = {"Sheet1": df1, "Sheet2": df2}
    result = decrypt_sheets(sheets, MAPPING)
    assert "Sheet1" in result
    assert "Sheet2" in result
    assert result["Sheet1"]["Контрагент"].iloc[0] == "ООО АЛЬФА"
    assert abs(result["Sheet2"]["Сумма"].iloc[0] - 100.0) < 0.01


# ---------------------------------------------------------------------------
# Integer rounding
# ---------------------------------------------------------------------------

def test_decrypt_integer_rounding():
    # Integer dtype column masked by 1.5 -> divide by 1.5 -> round to Int64
    df = pd.DataFrame({"Сумма": pd.array([150, 300], dtype="Int64")})
    sheets = {"Sheet1": df}
    result = decrypt_sheets(sheets, MAPPING)
    col = result["Sheet1"]["Сумма"]
    assert str(col.dtype) == "Int64"
    assert col.iloc[0] == 100
    assert col.iloc[1] == 200
