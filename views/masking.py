import streamlit as st
from core.output import generate_masked_xlsx, generate_mapping_json, generate_mapping_xlsx
from core.state_keys import (
    SHEETS, RAW_BYTES, STAGE, FILE_NAME,
    STAGE_UPLOADED, STAGE_COLUMNS, STAGE_MASKED,
    SELECTED_COLUMNS, MASK_CONFIG, MAPPING, MASKED_SHEETS, STATS,
)
from core.parser import parse_upload
from core.detector import detect_sensitive_columns, classify_column_type
from core.masker import mask_sheets
from ui.upload_widget import render_preview
from ui.step_indicator import render_steps
from ui.column_selector import render_column_selector

import pandas as pd


def render() -> None:
    st.header("Маскирование данных")

    stage = st.session_state.get(STAGE)

    if stage is None:
        _render_step_upload()
    elif stage == STAGE_UPLOADED:
        _render_step_preview()
    elif stage == STAGE_COLUMNS:
        _render_step_columns()
    elif stage == STAGE_MASKED:
        _render_step_masked()


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
        if st.button("Далее", type="primary", use_container_width=True):
            st.session_state[STAGE] = STAGE_COLUMNS
            st.rerun()


def _render_step_columns() -> None:
    render_steps(current=2)
    sheets = st.session_state[SHEETS]

    # Recompute detection — fast and stateless
    detected = detect_sensitive_columns(sheets)

    # Show warning if nothing was auto-detected
    all_detected = [col for cols in detected.values() for col in cols]
    if not all_detected:
        st.warning(
            "Автоматически чувствительные колонки не обнаружены, выберите вручную"
        )

    render_column_selector(sheets, detected)

    col_back, col_mask = st.columns([1, 1])
    with col_back:
        if st.button("Назад", use_container_width=True):
            st.session_state[STAGE] = STAGE_UPLOADED
            st.rerun()
    with col_mask:
        if st.button("Замаскировать", type="primary", use_container_width=True):
            # Build mask_config from checkbox and selectbox states
            mask_config: dict[str, dict[str, str]] = {}
            any_selected = False

            for sheet_name, df in sheets.items():
                sheet_config: dict[str, str] = {}
                for col in df.columns:
                    checked = st.session_state.get(f"cb_{sheet_name}_{col}", False)
                    if checked:
                        any_selected = True
                        # Determine masking type
                        col_type = classify_column_type(col, df[col])
                        if (
                            pd.api.types.is_numeric_dtype(df[col])
                            and col_type == "numeric"
                        ):
                            # User may have toggled to "идентификатор"
                            user_choice = st.session_state.get(
                                f"type_{sheet_name}_{col}", "коэффициент"
                            )
                            if user_choice == "идентификатор":
                                sheet_config[col] = "text"
                            else:
                                sheet_config[col] = "numeric"
                        else:
                            # Text-dtype columns always get text masking
                            sheet_config[col] = "text"
                mask_config[sheet_name] = sheet_config

            if not any_selected:
                st.warning("Выберите хотя бы одну колонку для маскирования")
            else:
                masked_sheets, mapping, stats = mask_sheets(sheets, mask_config)
                st.session_state[MASKED_SHEETS] = masked_sheets
                st.session_state[MAPPING] = mapping
                st.session_state[STATS] = stats
                st.session_state[MASK_CONFIG] = mask_config
                st.session_state[STAGE] = STAGE_MASKED
                st.rerun()


def _render_step_masked() -> None:
    render_steps(current=3)
    masked_sheets = st.session_state[MASKED_SHEETS]
    stats = st.session_state[STATS]
    file_name = st.session_state.get(FILE_NAME, "файл")

    st.subheader(f"Результат маскирования: {file_name}")

    # Statistics
    stat_col1, stat_col2 = st.columns(2)
    with stat_col1:
        st.metric("Замаскировано значений", stats["masked_values"])
    with stat_col2:
        st.metric("Уникальных сущностей", stats["unique_entities"])

    # Masked data preview (reuse existing render_preview widget)
    render_preview(masked_sheets)

    # --- Download buttons ---
    mapping = st.session_state[MAPPING]
    base_name = file_name.rsplit(".", 1)[0] if "." in file_name else file_name

    st.download_button(
        label="Скачать замаскированный файл",
        data=generate_masked_xlsx(masked_sheets),
        file_name=f"{base_name}_masked.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    st.download_button(
        label="Скачать маппинг (JSON)",
        data=generate_mapping_json(mapping),
        file_name=f"{base_name}_mapping.json",
        mime="application/json",
        use_container_width=True,
    )
    st.download_button(
        label="Скачать маппинг (Excel)",
        data=generate_mapping_xlsx(mapping),
        file_name=f"{base_name}_mapping.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    # Navigation
    col_back, col_reset = st.columns([1, 1])
    with col_back:
        if st.button("Назад к выбору колонок", use_container_width=True):
            # Clear masking results but preserve checkbox states
            for key in [MASKED_SHEETS, MAPPING, STATS]:
                st.session_state.pop(key, None)
            st.session_state[STAGE] = STAGE_COLUMNS
            st.rerun()
    with col_reset:
        if st.button("Сбросить", use_container_width=True):
            # Clear all state including dynamic checkbox/type keys
            keys_to_clear = [k for k in st.session_state if k.startswith(("cb_", "type_"))]
            for key in [
                SHEETS, RAW_BYTES, STAGE, FILE_NAME,
                SELECTED_COLUMNS, MASK_CONFIG, MAPPING, MASKED_SHEETS, STATS,
            ] + keys_to_clear:
                st.session_state.pop(key, None)
            st.rerun()
