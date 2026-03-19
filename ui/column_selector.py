"""Column selection widget for Step 2 of the masking flow (DETC-02, MASK-04)."""
from __future__ import annotations

import streamlit as st
import pandas as pd

from core.detector import classify_column_type


def render_column_selector(
    sheets: dict[str, pd.DataFrame],
    detected: dict[str, list[str]],
) -> None:
    """Render per-sheet column checkboxes with type badges and select-all buttons.

    Args:
        sheets:   {sheet_name: DataFrame} — original data
        detected: {sheet_name: [sensitive_col_names]} — from detect_sensitive_columns
    """
    sheet_names = list(sheets.keys())
    tabs = st.tabs(sheet_names)

    for tab, sheet in zip(tabs, sheet_names):
        with tab:
            df = sheets[sheet]
            detected_cols = detected.get(sheet, [])

            # "Выбрать все" / "Снять все" row
            btn_col1, btn_col2, _ = st.columns([1, 1, 4])
            with btn_col1:
                if st.button("Выбрать все", key=f"sel_all_{sheet}", use_container_width=True):
                    for col in df.columns:
                        st.session_state[f"cb_{sheet}_{col}"] = True
                    st.rerun()
            with btn_col2:
                if st.button("Снять все", key=f"desel_all_{sheet}", use_container_width=True):
                    for col in df.columns:
                        st.session_state[f"cb_{sheet}_{col}"] = False
                    st.rerun()

            st.divider()

            # One row per column
            for col in df.columns:
                col_type = classify_column_type(col, df[col])
                is_numeric_dtype = pd.api.types.is_numeric_dtype(df[col])
                default_checked = st.session_state.get(
                    f"cb_{sheet}_{col}",
                    col in detected_cols,
                )

                cb_col, badge_col, toggle_col = st.columns([0.6, 0.2, 0.2])

                with cb_col:
                    st.checkbox(
                        col,
                        value=default_checked,
                        key=f"cb_{sheet}_{col}",
                    )

                with badge_col:
                    if col_type == "text":
                        st.markdown(
                            "<span style='background:#e8f4f8;border-radius:4px;"
                            "padding:2px 6px;font-size:0.8em'>[текст]</span>",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            "<span style='background:#fff3e0;border-radius:4px;"
                            "padding:2px 6px;font-size:0.8em'>[число]</span>",
                            unsafe_allow_html=True,
                        )

                with toggle_col:
                    # Type toggle only for genuinely numeric-dtype columns
                    # (text-dtype columns classified as "text" via NUMERIC_ID_KEYWORDS
                    # do NOT get a toggle — they always mask as text)
                    if is_numeric_dtype and col_type == "numeric":
                        st.selectbox(
                            "Тип",
                            ["коэффициент", "идентификатор"],
                            key=f"type_{sheet}_{col}",
                            label_visibility="collapsed",
                        )
