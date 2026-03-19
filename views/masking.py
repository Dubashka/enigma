import streamlit as st
from core.state_keys import SHEETS, RAW_BYTES, STAGE, FILE_NAME, STAGE_UPLOADED
from core.parser import parse_upload
from ui.upload_widget import render_preview
from ui.step_indicator import render_steps


def render() -> None:
    st.header("Маскирование данных")

    stage = st.session_state.get(STAGE)

    if stage is None:
        _render_step_upload()
    elif stage == STAGE_UPLOADED:
        _render_step_preview()


def _render_step_upload() -> None:
    render_steps(current=1)
    st.subheader("Загрузите файл для маскирования")

    uploaded_file = st.file_uploader(
        "Выберите файл Excel (.xlsx) или CSV (.csv)",
        type=["xlsx", "csv"],
        key="file_uploader_mask",
    )

    if uploaded_file is not None:
        try:
            sheets = parse_upload(uploaded_file)
            st.session_state[SHEETS] = sheets
            st.session_state[FILE_NAME] = uploaded_file.name
            st.session_state[STAGE] = STAGE_UPLOADED
            st.rerun()
        except ValueError as e:
            st.error(str(e))


def _render_step_preview() -> None:
    render_steps(current=1)
    sheets = st.session_state[SHEETS]
    file_name = st.session_state.get(FILE_NAME, "файл")

    st.subheader(f"Превью: {file_name}")
    render_preview(sheets)

    col_back, col_next = st.columns([1, 1])
    with col_back:
        if st.button("Сбросить", use_container_width=True):
            for key in [SHEETS, RAW_BYTES, STAGE, FILE_NAME]:
                st.session_state.pop(key, None)
            st.rerun()
    with col_next:
        if st.button("Далее", type="primary", use_container_width=True, disabled=True):
            pass  # Phase 2 will enable this
