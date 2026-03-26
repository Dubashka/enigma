"""Output generation functions for masked data and mapping files (OUT-01, OUT-02, OUT-03).

Pure logic only — no Streamlit imports.
Takes dicts/DataFrames and returns bytes.
"""
from __future__ import annotations

import io
import json
import copy

import pandas as pd


def generate_masked_xlsx(masked_sheets: dict[str, pd.DataFrame]) -> bytes:
    """Serialize masked sheets dict into xlsx bytes (multi-sheet workbook). No formatting."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        for sheet_name, df in masked_sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    buf.seek(0)
    return buf.read()


def generate_formatted_xlsx(
    source_path: str,
    masked_sheets: dict[str, pd.DataFrame],
) -> bytes:
    """Replace cell values in the original xlsx file in-place, preserving all formatting.

    Strategy:
    - Open the original file with openpyxl (keep_vba=False, data_only=False)
    - For each sheet in masked_sheets, match rows by position (header row = row 1)
    - Replace only data cells; skip header row (row index 0 in DataFrame = Excel row 2)
    - Cells not covered by the DataFrame are left untouched
    - Returns bytes of the modified workbook

    Args:
        source_path:   path to the original uploaded xlsx file on disk
        masked_sheets: {sheet_name: DataFrame} with masked values
    """
    from openpyxl import load_workbook

    wb = load_workbook(source_path)

    for sheet_name, df in masked_sheets.items():
        if sheet_name not in wb.sheetnames:
            continue
        ws = wb[sheet_name]

        # Build column index: col_name -> Excel column number (1-based)
        # Header is assumed to be in row 1
        header_map: dict[str, int] = {}
        for cell in ws[1]:
            if cell.value is not None:
                header_map[str(cell.value)] = cell.column

        # Write DataFrame values starting from Excel row 2
        for df_row_idx, df_row in enumerate(df.itertuples(index=False), start=2):
            for col_name in df.columns:
                if col_name not in header_map:
                    continue
                col_num = header_map[col_name]
                new_val = getattr(df_row, col_name.replace(" ", "_").replace("/", "_"), None)
                # pandas NA / NaN — write None to keep cell empty
                if pd.isna(new_val) if not isinstance(new_val, str) else False:
                    ws.cell(row=df_row_idx, column=col_num).value = None
                else:
                    # Convert numpy/pandas types to native Python for openpyxl
                    if hasattr(new_val, "item"):
                        new_val = new_val.item()
                    ws.cell(row=df_row_idx, column=col_num).value = new_val

    buf = io.BytesIO()
    wb.save(buf)
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
