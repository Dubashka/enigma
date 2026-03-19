"""Output generation functions for masked data and mapping files (OUT-01, OUT-02, OUT-03).

Pure logic only — no Streamlit imports.
Takes dicts/DataFrames and returns bytes.
"""
from __future__ import annotations

import io
import json

import pandas as pd


def generate_masked_xlsx(masked_sheets: dict[str, pd.DataFrame]) -> bytes:
    """Serialize masked sheets dict into xlsx bytes (multi-sheet workbook)."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        for sheet_name, df in masked_sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    buf.seek(0)
    return buf.read()


def generate_mapping_json(mapping: dict) -> bytes:
    """Serialize mapping dict to UTF-8 JSON bytes with literal Cyrillic characters."""
    return json.dumps(mapping, indent=2, ensure_ascii=False).encode("utf-8")


def generate_mapping_xlsx(mapping: dict) -> bytes:
    """Serialize mapping dict into xlsx bytes with two sheets:
    - 'Текстовый маппинг': columns Оригинал, Псевдоним
    - 'Числовой маппинг': columns Колонка, Коэффициент
    """
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        text_df = pd.DataFrame(
            list(mapping.get("text", {}).items()),
            columns=["Оригинал", "Псевдоним"],
        )
        text_df.to_excel(writer, sheet_name="Текстовый маппинг", index=False)
        numeric_df = pd.DataFrame(
            list(mapping.get("numeric", {}).items()),
            columns=["Колонка", "Коэффициент"],
        )
        numeric_df.to_excel(writer, sheet_name="Числовой маппинг", index=False)
    buf.seek(0)
    return buf.read()
