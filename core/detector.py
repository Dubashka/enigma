"""Keyword-based column detection and type classification (DETC-01, DETC-03)."""
from __future__ import annotations

import pandas as pd


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
) -> dict[str, list[str]]:
    """Return {sheet_name: [col_names_suggested_sensitive]}.

    Detection is case-insensitive substring match against SENSITIVE_KEYWORDS.
    Empty list is returned for sheets with no matching columns.
    """
    result: dict[str, list[str]] = {}
    for sheet_name, df in sheets.items():
        sensitive: list[str] = []
        for col in df.columns:
            col_lower = str(col).lower()
            if any(kw in col_lower for kw in SENSITIVE_KEYWORDS):
                sensitive.append(col)
        result[sheet_name] = sensitive
    return result


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
