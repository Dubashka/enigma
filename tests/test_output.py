"""Unit tests for core/output.py — output generators (OUT-01, OUT-02, OUT-03)."""
import io
import json

import pandas as pd
import pytest

from core.output import generate_masked_xlsx, generate_mapping_json, generate_mapping_xlsx


# ---------------------------------------------------------------------------
# Fixtures / shared test data
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_sheets():
    df1 = pd.DataFrame({"Name": ["A", "B"], "Value": [1, 2]})
    df2 = pd.DataFrame({"City": ["X"]})
    return {"Sheet1": df1, "Sheet2": df2}


@pytest.fixture()
def sample_mapping():
    return {
        "text": {"ООО АЛЬФА": "Предприятие A", "ООО БЕТА": "Предприятие B"},
        "numeric": {"Сумма": 1.234},
    }


# ---------------------------------------------------------------------------
# generate_masked_xlsx
# ---------------------------------------------------------------------------

def test_masked_xlsx_has_all_sheets(sample_sheets):
    result = generate_masked_xlsx(sample_sheets)
    loaded = pd.read_excel(io.BytesIO(result), sheet_name=None)
    assert "Sheet1" in loaded
    assert "Sheet2" in loaded


def test_masked_xlsx_row_counts(sample_sheets):
    result = generate_masked_xlsx(sample_sheets)
    loaded = pd.read_excel(io.BytesIO(result), sheet_name=None)
    assert len(loaded["Sheet1"]) == 2
    assert len(loaded["Sheet2"]) == 1


def test_masked_xlsx_preserves_columns(sample_sheets):
    result = generate_masked_xlsx(sample_sheets)
    loaded = pd.read_excel(io.BytesIO(result), sheet_name=None)
    assert list(loaded["Sheet1"].columns) == ["Name", "Value"]
    assert list(loaded["Sheet2"].columns) == ["City"]


# ---------------------------------------------------------------------------
# generate_mapping_json
# ---------------------------------------------------------------------------

def test_mapping_json_format(sample_mapping):
    result = generate_mapping_json(sample_mapping)
    assert isinstance(result, bytes)
    parsed = json.loads(result.decode("utf-8"))
    assert "text" in parsed
    assert "numeric" in parsed


def test_mapping_json_cyrillic(sample_mapping):
    result = generate_mapping_json(sample_mapping)
    # Cyrillic characters must appear literally, not as \u escapes
    text = result.decode("utf-8")
    assert "ООО АЛЬФА" in text
    assert "Предприятие A" in text
    assert "\\u" not in text


# ---------------------------------------------------------------------------
# generate_mapping_xlsx
# ---------------------------------------------------------------------------

def test_mapping_xlsx_two_sheets(sample_mapping):
    result = generate_mapping_xlsx(sample_mapping)
    loaded = pd.read_excel(io.BytesIO(result), sheet_name=None)
    assert "Текстовый маппинг" in loaded
    assert "Числовой маппинг" in loaded


def test_mapping_xlsx_text_columns(sample_mapping):
    result = generate_mapping_xlsx(sample_mapping)
    loaded = pd.read_excel(io.BytesIO(result), sheet_name=None)
    text_sheet = loaded["Текстовый маппинг"]
    assert list(text_sheet.columns) == ["Оригинал", "Псевдоним"]


def test_mapping_xlsx_numeric_columns(sample_mapping):
    result = generate_mapping_xlsx(sample_mapping)
    loaded = pd.read_excel(io.BytesIO(result), sheet_name=None)
    numeric_sheet = loaded["Числовой маппинг"]
    assert list(numeric_sheet.columns) == ["Колонка", "Коэффициент"]
