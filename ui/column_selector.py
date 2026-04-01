"""Column selection widget for Step 2 of the masking flow (DETC-02, MASK-04)."""
from __future__ import annotations

import streamlit as st
import pandas as pd

from core.detector import classify_column_type

_AI_BADGE = {
    "required": (
        "<span style='background:#fde8e8;color:#c0392b;border-radius:4px;"
        "padding:2px 5px;font-size:0.75em;white-space:nowrap'>⚠ Обязательно</span>"
    ),
    "recommended": (
        "<span style='background:#fff3cd;color:#856404;border-radius:4px;"
        "padding:2px 5px;font-size:0.75em;white-space:nowrap'>● Рекомендуется</span>"
    ),
    "safe": (
        "<span style='background:#e8f5e9;color:#2e7d32;border-radius:4px;"
        "padding:2px 5px;font-size:0.75em;white-space:nowrap'>✓ Безопасно</span>"
    ),
}


def _get_sample_values(series: pd.Series, n: int = 3) -> str:
    """Return a string of up to n non-null unique sample values from series."""
    samples = series.dropna().unique()
    samples = samples[:n]
    return ",  ".join(str(v) for v in samples)


def render_column_selector(
    sheets: dict[str, pd.DataFrame],
    detected: dict[str, list[str]],
    ai_results: dict[str, dict[str, str]] | None = None,
    presidio_required: dict[str, list[str]] | None = None,
) -> None:
    """Render per-sheet column checkboxes with type badges, sample values.

    Args:
        sheets:     {sheet_name: DataFrame} — original data
        detected:   {sheet_name: [sensitive_col_names]} — from detect_sensitive_columns
        ai_results: {sheet_name: {col_name: verdict}} — from check_columns_with_ai, or None
        presidio_required: {sheet_name: [col_names]} — columns confirmed by Presidio
    """
    sheet_names = list(sheets.keys())
    tabs = st.tabs(sheet_names)

    for tab, sheet in zip(tabs, sheet_names):
        with tab:
            df = sheets[sheet]
            detected_cols = detected.get(sheet, [])
            sheet_ai = ai_results.get(sheet, {}) if ai_results else {}
            presidio_cols = set(presidio_required.get(sheet, [])) if presidio_required else set()

            # "Выбрать все" / "Снять все"
            btn_col1, btn_col2, _ = st.columns([1, 1, 4])
            with btn_col1:
                if st.button("Выбрать все", key=f"sel_all_{sheet}", use_container_width=True):
                    for col in df.columns:
                        st.session_state[f"cb_{sheet}_{col}"] = True
                    st.rerun()
            with btn_col2:
                if st.button("Снять все", key=f"desel_all_{sheet}", use_container_width=True):
                    for col in df.columns:
                        if sheet_ai.get(col) != "required":
                            st.session_state[f"cb_{sheet}_{col}"] = False
                    st.rerun()

            st.divider()

            # Header row — columns depend on whether AI results are available
            if ai_results is not None:
                h_cb, h_badge, h_samples, h_ai, h_toggle = st.columns([0.30, 0.10, 0.25, 0.20, 0.15])
                with h_ai:
                    st.caption("AI-анализ")
            else:
                h_cb, h_badge, h_samples, h_toggle = st.columns([0.35, 0.12, 0.28, 0.25])

            with h_cb:
                st.caption("Колонка")
            with h_badge:
                st.caption("Тип")
            with h_samples:
                st.caption("Примеры значений")
            with h_toggle:
                st.caption("")

            # One row per column
            for col in df.columns:
                col_type = classify_column_type(col, df[col])
                is_numeric_dtype = pd.api.types.is_numeric_dtype(df[col])
                cb_key = f"cb_{sheet}_{col}"
                verdict = sheet_ai.get(col) if ai_results else None
                is_required = verdict == "required" or col in presidio_cols

                if ai_results is not None:
                    cb_col, badge_col, samples_col, ai_col, toggle_col = st.columns([0.30, 0.10, 0.25, 0.20, 0.15])
                else:
                    cb_col, badge_col, samples_col, toggle_col = st.columns([0.35, 0.12, 0.28, 0.25])
                    ai_col = None

                with cb_col:
                    cb_kwargs: dict = {"key": cb_key, "disabled": is_required}
                    if cb_key not in st.session_state:
                        cb_kwargs["value"] = col in detected_cols
                    st.checkbox(col, **cb_kwargs)

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

                with samples_col:
                    sample_str = _get_sample_values(df[col], n=3)
                    if sample_str:
                        st.markdown(
                            f"<span style='color:#666;font-size:0.8em'>{sample_str}</span>",
                            unsafe_allow_html=True,
                        )

                if ai_col is not None:
                    with ai_col:
                        if verdict and verdict in _AI_BADGE:
                            st.markdown(_AI_BADGE[verdict], unsafe_allow_html=True)

                with toggle_col:
                    if is_numeric_dtype and col_type == "numeric":
                        st.selectbox(
                            "Тип",
                            ["идентификатор", "коэффициент"],
                            key=f"type_{sheet}_{col}",
                            label_visibility="collapsed",
                        )
