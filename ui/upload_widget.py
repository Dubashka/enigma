import streamlit as st
import pandas as pd


def render_preview(sheets: dict[str, pd.DataFrame]) -> None:
    """Render preview of parsed sheets. 20 rows per sheet.

    Single sheet: no tabs, just dataframe.
    Multiple sheets: st.tabs with sheet names.
    """
    sheet_names = list(sheets.keys())
    if len(sheet_names) == 1:
        st.dataframe(
            sheets[sheet_names[0]].head(20),
            use_container_width=True,
        )
    else:
        tabs = st.tabs(sheet_names)
        for tab, name in zip(tabs, sheet_names):
            with tab:
                st.dataframe(
                    sheets[name].head(20),
                    use_container_width=True,
                )
