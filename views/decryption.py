import streamlit as st
import pandas as pd

from core.parser import parse_upload, save_upload, cleanup_upload
from core.decryptor import load_mapping_json, decrypt_sheets
from core.output import generate_masked_xlsx, generate_formatted_xlsx
from core.state_keys import DECR_SHEETS, DECR_MAPPING, DECR_RESULT, DECR_FILE_PATH, FORMAT_MODE
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
        # Save file to disk so we can use it for formatted output
        try:
            file_path = save_upload(uploaded_file)
            st.session_state[DECR_FILE_PATH] = file_path
            uploaded_file.seek(0)
            sheets = parse_upload(uploaded_file)
        except ValueError as e:
            st.error(str(e))
            return

        mapping = load_mapping_json(uploaded_json)
        if mapping is None:
            st.error("Невалидный файл маппинга. Убедитесь, что это JSON-файл с ключами 'text' и 'numeric'.")
            return

        st.session_state[DECR_SHEETS] = sheets
        st.session_state[DECR_MAPPING] = mapping

        st.subheader("Замаскированные данные")
        render_preview(sheets)

        # Format mode selector — only for xlsx
        is_xlsx = uploaded_file.name.lower().endswith(".xlsx")
        if is_xlsx:
            st.divider()
            st.markdown("**Формат выходного файла**")
            format_choice = st.radio(
                "Формат выходного файла",
                options=["raw", "formatted"],
                format_func=lambda x: (
                    "Без форматирования (быстро)" if x == "raw"
                    else "Сохранить форматирование оригинала"
                ),
                index=0 if st.session_state.get(FORMAT_MODE, "raw") == "raw" else 1,
                horizontal=True,
                label_visibility="collapsed",
            )
            st.session_state[FORMAT_MODE] = format_choice
            if format_choice == "formatted":
                st.caption("Цвета ячеек, шрифты, границы и ширина колонок будут сохранены из замаскированного файла.")
            else:
                st.caption("Выходной файл будет содержать только данные без стилей.")
        else:
            st.session_state[FORMAT_MODE] = "raw"

        if st.button("Дешифровать", type="primary", use_container_width=True):
            result = decrypt_sheets(sheets, mapping)
            st.session_state[DECR_RESULT] = result

    # Show decrypted result if available
    if DECR_RESULT in st.session_state:
        st.subheader("Восстановленные данные")
        result = st.session_state[DECR_RESULT]
        render_preview(result)

        decr_file_name = "decrypted.xlsx"
        if uploaded_file is not None:
            base = uploaded_file.name.rsplit(".", 1)[0] if "." in uploaded_file.name else uploaded_file.name
            decr_file_name = f"{base}_decrypted.xlsx"

        format_mode = st.session_state.get(FORMAT_MODE, "raw")
        file_path = st.session_state.get(DECR_FILE_PATH)
        if format_mode == "formatted" and file_path and file_path.lower().endswith(".xlsx"):
            output_bytes = generate_formatted_xlsx(file_path, result)
        else:
            output_bytes = generate_masked_xlsx(result)

        if format_mode == "formatted":
            st.caption("✅ Форматирование оригинала сохранено")
        else:
            st.caption("📄 Без форматирования")

        st.download_button(
            label="Скачать восстановленный файл",
            data=output_bytes,
            file_name=decr_file_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

        if st.button("Сбросить", use_container_width=True):
            file_path = st.session_state.get(DECR_FILE_PATH)
            if file_path:
                cleanup_upload(file_path)
            for key in [DECR_SHEETS, DECR_MAPPING, DECR_RESULT, DECR_FILE_PATH, FORMAT_MODE]:
                st.session_state.pop(key, None)
            st.rerun()
