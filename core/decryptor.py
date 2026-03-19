"""Decryption engine — restores masked data using a mapping file (DECR-01, DECR-02, DECR-03).

Pure logic only — no Streamlit imports.
Takes sheets dict + mapping dict, returns restored sheets dict.
"""
from __future__ import annotations

import json

import pandas as pd


def load_mapping_json(uploaded_file) -> dict | None:
    """Load and validate a mapping JSON file.

    Args:
        uploaded_file: file-like object with a .read() method (BytesIO or Streamlit UploadedFile)

    Returns:
        Mapping dict with 'text' and 'numeric' keys, or None on parse error / missing keys.
    """
    try:
        content = uploaded_file.read()
        mapping = json.loads(content if isinstance(content, str) else content.decode("utf-8"))
        if "text" not in mapping or "numeric" not in mapping:
            return None
        return mapping
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def decrypt_sheets(
    sheets: dict[str, pd.DataFrame],
    mapping: dict,
) -> dict[str, pd.DataFrame]:
    """Restore all sheets by reversing text pseudonymisation and dividing numeric columns.

    - Text columns: cells matching any pseudonym are replaced with the original value.
      Unknown values and NaN cells pass through unchanged.
    - Numeric columns: divide by the stored coefficient and round.
      Integer-dtype columns are rounded and cast back to Int64.
    - Columns not in mapping are left unchanged.

    Args:
        sheets:  {sheet_name: DataFrame} — masked data
        mapping: {"text": {orig: pseudonym}, "numeric": {col: multiplier}}

    Returns:
        {sheet_name: DataFrame} — decrypted data
    """
    # Invert text mapping: pseudonym -> original
    reverse_text = {v: k for k, v in mapping.get("text", {}).items()}
    numeric_map = mapping.get("numeric", {})

    result: dict[str, pd.DataFrame] = {}
    for sheet_name, df in sheets.items():
        decrypted = df.copy()
        for col in decrypted.columns:
            if col in numeric_map:
                coeff = numeric_map[col]
                series = decrypted[col]
                divided = series / coeff
                if pd.api.types.is_integer_dtype(series):
                    decrypted[col] = divided.round().astype("Int64")
                else:
                    decrypted[col] = divided.round(2)
            else:
                decrypted[col] = decrypted[col].map(
                    lambda v, rt=reverse_text: rt.get(str(v), v) if pd.notna(v) else v
                )
        result[sheet_name] = decrypted
    return result
