"""Unit tests for core.detector module (DETC-01, DETC-03)."""
import pandas as pd
import pytest

from core.detector import (
    SENSITIVE_KEYWORDS,
    NUMERIC_ID_KEYWORDS,
    detect_sensitive_columns,
    classify_column_type,
)


def test_detect_sensitive_columns(sample_detection_sheets):
    """detect_sensitive_columns returns correct sensitive columns per sheet."""
    result, _ = detect_sensitive_columns(sample_detection_sheets)

    # Лист1 checks
    assert "Имя предприятия" in result["Лист1"], "'Имя предприятия' should be detected (keyword 'имя')"
    assert "Цена" in result["Лист1"], "'Цена' should be detected (keyword 'цена')"
    assert "Документ закупки" in result["Лист1"], "'Документ закупки' should be detected (keyword 'документ')"
    assert "Количество" not in result["Лист1"], "'Количество' should NOT be detected"

    # Лист2 checks
    assert "Имя предприятия" in result["Лист2"], "'Имя предприятия' should be detected on Лист2"
    assert "Автор изменения" in result["Лист2"], "'Автор изменения' should be detected (keyword 'автор')"
    assert "Сумма" in result["Лист2"], "'Сумма' should be detected (keyword 'сумма')"


def test_detect_no_match_returns_empty():
    """detect_sensitive_columns returns empty lists when no columns match."""
    df = pd.DataFrame({"Дата": ["2024-01-01", "2024-01-02"], "Статус": ["OK", "NG"]})
    result, _ = detect_sensitive_columns({"Лист1": df})
    assert result["Лист1"] == [], "No sensitive columns expected"


def test_detect_case_insensitive():
    """Detection is case-insensitive: 'АВТОР Изменения' matches keyword 'автор'."""
    df = pd.DataFrame({"АВТОР Изменения": ["Иванов", "Петров"]})
    result, _ = detect_sensitive_columns({"Лист1": df})
    assert "АВТОР Изменения" in result["Лист1"], "Case-insensitive match should work"


def test_classify_object_is_text():
    """object dtype column always classified as 'text'."""
    series = pd.Series(["ООО Альфа", "ООО Бета"], dtype=object)
    assert classify_column_type("Имя предприятия", series) == "text"


def test_classify_quantity_is_numeric():
    """int64 column without ID keywords classified as 'numeric'."""
    series = pd.Series([10, 20, 30], dtype="int64")
    assert classify_column_type("Количество", series) == "numeric"


def test_classify_numeric_id_is_text():
    """int64 column with 'документ' in name classified as 'text'."""
    series = pd.Series([4500001, 4500002, 4500003], dtype="int64")
    assert classify_column_type("Документ закупки", series) == "text"


def test_classify_number_sign_is_text():
    """int64 column with '№' + 'договор' in name classified as 'text'."""
    series = pd.Series([100, 200, 300], dtype="int64")
    assert classify_column_type("№ договора", series) == "text"


def test_sensitive_keywords_count():
    """SENSITIVE_KEYWORDS contains at least 20 keywords."""
    assert len(SENSITIVE_KEYWORDS) >= 20, f"Expected 20+, got {len(SENSITIVE_KEYWORDS)}"


def test_numeric_id_keywords_count():
    """NUMERIC_ID_KEYWORDS contains at least 10 keywords."""
    assert len(NUMERIC_ID_KEYWORDS) >= 10, f"Expected 10+, got {len(NUMERIC_ID_KEYWORDS)}"
