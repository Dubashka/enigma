import streamlit as st
from core.output import generate_masked_xlsx, generate_formatted_xlsx, generate_mapping_json, generate_mapping_xlsx
from core.state_keys import (
    SHEETS, RAW_BYTES, STAGE, FILE_NAME, FILE_PATH,
    STAGE_UPLOADED, STAGE_COLUMNS, STAGE_MASKED,
    SELECTED_COLUMNS, MASK_CONFIG, MAPPING, MASKED_SHEETS, STATS,
    DL_XLSX, DL_MAP_JSON, DL_MAP_XLSX, FORMAT_MODE,
)
from core.parser import save_upload, parse_preview, parse_full, cleanup_upload
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
            with st.spinner("Сохраняем и читаем превью файла…"):
                path = save_upload(uploaded_file)
                preview_sheets = parse_preview(path)
            st.session_state[FILE_PATH] = path
            st.session_state[SHEETS] = preview_sheets
            st.session_state[FILE_NAME] = uploaded_file.name
            st.session_state[STAGE] = STAGE_UPLOADED
            st.rerun()
        except ValueError as e:
            st.error(str(e))


def _render_step_preview() -> None:
    render_steps(current=1)
    sheets = st.session_state[SHEETS]
    file_name = st.session_state.get(FILE_NAME, "файл")
    is_xlsx = file_name.lower().endswith(".xlsx")

    st.subheader(f"Превью: {file_name}")
    st.caption("Показаны первые 20 строк каждого листа")
    render_preview(sheets)

    # Format mode selector — only meaningful for xlsx (csv has no formatting)
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
            st.caption("Цвета ячеек, шрифты, границы и ширина колонок будут сохранены из оригинального файла.")
        else:
            st.caption("Выходной файл будет содержать только данные без стилей.")
    else:
        # CSV — formatting not applicable
        st.session_state[FORMAT_MODE] = "raw"

    col_back, col_next = st.columns([1, 1])
    with col_back:
        if st.button("Сбросить", use_container_width=True):
            _cleanup_and_reset()
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
                        col_type = classify_column_type(col, df[col])
                        if (
                            pd.api.types.is_numeric_dtype(df[col])
                            and col_type == "numeric"
                        ):
                            user_choice = st.session_state.get(
                                f"type_{sheet_name}_{col}", "коэффициент"
                            )
                            if user_choice == "идентификатор":
                                sheet_config[col] = "text"
                            else:
                                sheet_config[col] = "numeric"
                        else:
                            sheet_config[col] = "text"
                mask_config[sheet_name] = sheet_config

            if not any_selected:
                st.warning("Выберите хотя бы одну колонку для маскирования")
            else:
                file_path = st.session_state.get(FILE_PATH)
                progress = st.progress(0, text="Читаем файл…")

                if file_path:
                    full_sheets = parse_full(file_path)
                else:
                    full_sheets = sheets

                total_rows = sum(len(df) for df in full_sheets.values())
                progress.progress(25, text=f"Файл прочитан ({total_rows:,} строк). Маскируем…")

                masked_sheets, mapping, stats = mask_sheets(full_sheets, mask_config)
                progress.progress(60, text="Маскирование завершено. Генерируем файлы для скачивания…")

                # Generate output according to chosen format mode
                format_mode = st.session_state.get(FORMAT_MODE, "raw")
                if format_mode == "formatted" and file_path and file_path.lower().endswith(".xlsx"):
                    st.session_state[DL_XLSX] = generate_formatted_xlsx(file_path, masked_sheets)
                else:
                    st.session_state[DL_XLSX] = generate_masked_xlsx(masked_sheets)
                progress.progress(85, text="Замаскированный файл готов. Генерируем маппинги…")

                st.session_state[DL_MAP_JSON] = generate_mapping_json(mapping)
                st.session_state[DL_MAP_XLSX] = generate_mapping_xlsx(mapping)
                progress.progress(100, text="Готово!")

                preview_masked = {name: df.head(20) for name, df in masked_sheets.items()}
                st.session_state[MASKED_SHEETS] = preview_masked
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
    format_mode = st.session_state.get(FORMAT_MODE, "raw")

    st.subheader(f"Результат маскирования: {file_name}")

    # Format mode badge
    if format_mode == "formatted":
        st.caption("✅ Форматирование оригинала сохранено")
    else:
        st.caption("📄 Без форматирования")

    # Statistics
    stat_col1, stat_col2 = st.columns(2)
    with stat_col1:
        st.metric("Замаскировано значений", stats["masked_values"])
    with stat_col2:
        st.metric("Уникальных сущностей", stats["unique_entities"])

    render_preview(masked_sheets)

    base_name = file_name.rsplit(".", 1)[0] if "." in file_name else file_name

    st.download_button(
        label="Скачать замаскированный файл",
        data=st.session_state[DL_XLSX],
        file_name=f"{base_name}_masked.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    st.download_button(
        label="Скачать маппинг (JSON)",
        data=st.session_state[DL_MAP_JSON],
        file_name=f"{base_name}_mapping.json",
        mime="application/json",
        use_container_width=True,
    )
    st.download_button(
        label="Скачать маппинг (Excel)",
        data=st.session_state[DL_MAP_XLSX],
        file_name=f"{base_name}_mapping.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    col_back, col_reset = st.columns([1, 1])
    with col_back:
        if st.button("Назад к выбору колонок", use_container_width=True):
            for key in [MASKED_SHEETS, MAPPING, STATS, DL_XLSX, DL_MAP_JSON, DL_MAP_XLSX]:
                st.session_state.pop(key, None)
            st.session_state[STAGE] = STAGE_COLUMNS
            st.rerun()
    with col_reset:
        if st.button("Сбросить", use_container_width=True):
            _cleanup_and_reset()
            st.rerun()


def _cleanup_and_reset() -> None:
    """Clear all state and remove uploaded file from disk."""
    file_path = st.session_state.get(FILE_PATH)
    if file_path:
        cleanup_upload(file_path)
    keys_to_clear = [k for k in st.session_state if k.startswith(("cb_", "type_"))]
    for key in [
        SHEETS, RAW_BYTES, STAGE, FILE_NAME, FILE_PATH,
        SELECTED_COLUMNS, MASK_CONFIG, MAPPING, MASKED_SHEETS, STATS,
        DL_XLSX, DL_MAP_JSON, DL_MAP_XLSX, FORMAT_MODE,
    ] + keys_to_clear:
        st.session_state.pop(key, None)
