import streamlit as st

from core.parser import parse_upload, save_upload, cleanup_upload
from core.decryptor import load_mapping_json, decrypt_sheets
from core.output import generate_masked_xlsx, generate_masked_csv, generate_formatted_xlsx
from core.state_keys import DECR_SHEETS, DECR_MAPPING, DECR_RESULT, DECR_FILE_PATH, FORMAT_MODE
from ui.upload_widget import render_preview
from ui.step_indicator import render_steps, STEPS_DECRYPTION

_STAGE = "decr_stage"
_STAGE_UPLOAD = "upload"
_STAGE_DECRYPT = "decrypt"
_STAGE_RESULT = "result"
_FILE_NAME = "decr_file_name"


def render() -> None:
    st.header("Демаскирование данных")

    stage = st.session_state.get(_STAGE, _STAGE_UPLOAD)

    if stage == _STAGE_UPLOAD:
        _render_step_upload()
    elif stage == _STAGE_DECRYPT:
        _render_step_decrypt()
    elif stage == _STAGE_RESULT:
        _render_step_result()


def _render_step_upload() -> None:
    render_steps(current=1, steps=STEPS_DECRYPTION)
    st.subheader("Загрузите файлы")

    col_file, col_json = st.columns(2)
    with col_file:
        uploaded_file = st.file_uploader(
            "Форматы: Excel (.xlsx) или CSV (.csv). Макс. размер: 200 MB.",
            type=["xlsx", "csv"],
            key="decr_file_uploader",
        )
    with col_json:
        uploaded_json = st.file_uploader(
            "Файл маппинга. Формат: JSON.",
            type=["json"],
            key="decr_json_uploader",
        )

    if uploaded_file is not None and uploaded_json is not None:
        if st.button("Далее", type="primary", use_container_width=True):
            try:
                file_path = save_upload(uploaded_file)
                uploaded_file.seek(0)
                sheets = parse_upload(uploaded_file)
            except ValueError as e:
                st.error(str(e))
                return

            mapping = load_mapping_json(uploaded_json)
            if mapping is None:
                st.error("Невалидный файл маппинга. Убедитесь, что это JSON-файл с ключами 'text' и 'numeric'.")
                return

            st.session_state[DECR_FILE_PATH] = file_path
            st.session_state[DECR_SHEETS] = sheets
            st.session_state[DECR_MAPPING] = mapping
            st.session_state[_FILE_NAME] = uploaded_file.name
            st.session_state[_STAGE] = _STAGE_DECRYPT
            st.rerun()


def _render_step_decrypt() -> None:
    render_steps(current=2, steps=STEPS_DECRYPTION)
    sheets = st.session_state[DECR_SHEETS]
    file_name = st.session_state.get(_FILE_NAME, "файл")
    is_xlsx = file_name.lower().endswith(".xlsx")

    st.subheader(f"Замаскированные данные: {file_name}")
    st.caption("Показаны первые 5 строк")
    render_preview(sheets)

    if is_xlsx:
        st.divider()
        st.markdown("**Формат выходного файла**")
        format_choice = st.radio(
            "Формат",
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

    col_back, col_decrypt = st.columns([1, 1])
    with col_back:
        if st.button("Назад", use_container_width=True):
            _cleanup_and_reset()
            st.rerun()
    with col_decrypt:
        if st.button("Демаскировать", type="primary", use_container_width=True):
            mapping = st.session_state[DECR_MAPPING]
            result = decrypt_sheets(sheets, mapping)
            st.session_state[DECR_RESULT] = result
            st.session_state[_STAGE] = _STAGE_RESULT
            st.rerun()


def _render_step_result() -> None:
    render_steps(current=3, steps=STEPS_DECRYPTION)
    result = st.session_state[DECR_RESULT]
    file_name = st.session_state.get(_FILE_NAME, "файл")
    format_mode = st.session_state.get(FORMAT_MODE, "raw")
    file_path = st.session_state.get(DECR_FILE_PATH)

    is_csv = file_name.lower().endswith(".csv")

    st.subheader(f"Результат демаскирования: {file_name}")
    st.caption("Показаны первые 5 строк")
    render_preview(result)

    base = file_name.rsplit(".", 1)[0] if "." in file_name else file_name

    if is_csv:
        decr_file_name = f"{base}_decrypted.csv"
        output_bytes = generate_masked_csv(result)
        mime = "text/csv"
    elif format_mode == "formatted" and file_path and file_path.lower().endswith(".xlsx"):
        decr_file_name = f"{base}_decrypted.xlsx"
        output_bytes = generate_formatted_xlsx(file_path, result)
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        decr_file_name = f"{base}_decrypted.xlsx"
        output_bytes = generate_masked_xlsx(result)
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    st.download_button(
        label="Скачать восстановленный файл",
        data=output_bytes,
        file_name=decr_file_name,
        mime=mime,
        use_container_width=True,
        type="primary",
    )

    col_back, col_reset = st.columns([1, 1])
    with col_back:
        if st.button("Назад к демаскированию", use_container_width=True):
            st.session_state.pop(DECR_RESULT, None)
            st.session_state[_STAGE] = _STAGE_DECRYPT
            st.rerun()
    with col_reset:
        if st.button("Сбросить", use_container_width=True):
            _cleanup_and_reset()
            st.rerun()


def _cleanup_and_reset() -> None:
    file_path = st.session_state.get(DECR_FILE_PATH)
    if file_path:
        cleanup_upload(file_path)
    for key in [DECR_SHEETS, DECR_MAPPING, DECR_RESULT, DECR_FILE_PATH, FORMAT_MODE, _STAGE, _FILE_NAME]:
        st.session_state.pop(key, None)
