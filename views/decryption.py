import streamlit as st
import pandas as pd

from core.parser import parse_upload
from core.decryptor import load_mapping_json, decrypt_sheets
from core.output import generate_masked_xlsx
from core.state_keys import DECR_SHEETS, DECR_MAPPING, DECR_RESULT
from ui.upload_widget import render_preview


def render() -> None:
    st.header("Дешифровка данных")
    st.markdown(
        "Загрузите замаскированный файл и JSON-маппинг, чтобы восстановить оригинальные значения."
    )

    col_file, col_json = st.columns(2)
    with col_file:
        uploaded_file = st.file_uploader(
            "Замаскированный файл (xlsx или csv)",
            type=["xlsx", "csv"],
            key="decr_file_uploader",
        )
    with col_json:
        uploaded_json = st.file_uploader(
            "Файл маппинга (JSON)",
            type=["json"],
            key="decr_json_uploader",
        )

    if uploaded_file is not None and uploaded_json is not None:
        # Parse masked file
        try:
            sheets = parse_upload(uploaded_file)
        except ValueError as e:
            st.error(str(e))
            return

        # Load mapping
        mapping = load_mapping_json(uploaded_json)
        if mapping is None:
            st.error("Невалидный файл маппинга. Убедитесь, что это JSON-файл с ключами 'text' и 'numeric'.")
            return

        st.session_state[DECR_SHEETS] = sheets
        st.session_state[DECR_MAPPING] = mapping

        st.subheader("Замаскированные данные")
        render_preview(sheets)

        if st.button("Дешифровать", type="primary", use_container_width=True):
            result = decrypt_sheets(sheets, mapping)
            st.session_state[DECR_RESULT] = result

    # Show decrypted result if available
    if DECR_RESULT in st.session_state:
        st.subheader("Восстановленные данные")
        result = st.session_state[DECR_RESULT]
        render_preview(result)

        # Derive download filename from uploaded file
        decr_file_name = "decrypted.xlsx"
        if uploaded_file is not None:
            base = uploaded_file.name.rsplit(".", 1)[0] if "." in uploaded_file.name else uploaded_file.name
            decr_file_name = f"{base}_decrypted.xlsx"

        st.download_button(
            label="Скачать восстановленный файл",
            data=generate_masked_xlsx(result),
            file_name=decr_file_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

        if st.button("Сбросить", use_container_width=True):
            for key in [DECR_SHEETS, DECR_MAPPING, DECR_RESULT]:
                st.session_state.pop(key, None)
            st.rerun()
