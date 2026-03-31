import streamlit as st
import pandas as pd


def _safe_preview(df: pd.DataFrame) -> pd.DataFrame:
    """Return head(5) with object-dtype columns cast to str for Arrow safety."""
    preview = df.head(5).copy()
    for col in preview.columns:
        if preview[col].dtype == object:
            preview[col] = preview[col].astype(str)
    return preview


def render_preview(sheets: dict[str, pd.DataFrame]) -> None:
    """Render preview of parsed sheets. 5 rows per sheet.

    Single sheet: no tabs, just dataframe.
    Multiple sheets: st.tabs with sheet names.
    """
    sheet_names = list(sheets.keys())
    if len(sheet_names) == 1:
        st.dataframe(
            _safe_preview(sheets[sheet_names[0]]),
            use_container_width=True,
        )
    else:
        tabs = st.tabs(sheet_names)
        for tab, name in zip(tabs, sheet_names):
            with tab:
                st.dataframe(
                    _safe_preview(sheets[name]),
                    use_container_width=True,
                )
