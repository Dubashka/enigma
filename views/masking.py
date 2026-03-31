import io
import zipfile
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


def _build_zip(xlsx_bytes: bytes, json_bytes: bytes, base_name: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{base_name}_masked.xlsx", xlsx_bytes)
        zf.writestr(f"{base_name}_mapping.json", json_bytes)
    return buf.getvalue()


def _generate_masked_csv(masked_sheets: dict) -> bytes:
    first_df = next(iter(masked_sheets.values()))
    return first_df.to_csv(index=False).encode("utf-8")


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
        "Форматы: Excel (.xlsx) или CSV (.csv). Максимальный размер: 200 MB.",
        type=["xlsx", "csv"],
        key="file_uploader_mask",
    )

    if uploaded_file is not None:
        try:
            with st.spinner("Читаем файл…"):
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

    st.subheader(f"Превью: {file_name}")
    st.caption("Показаны первые 5 строк")
    render_preview(sheets)

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
    file_name = st.session_state.get(FILE_NAME, "файл")
    is_xlsx = file_name.lower().endswith(".xlsx")

    detected = detect_sensitive_columns(sheets)
    render_column_selector(sheets, detected)

    # Format mode selector — moved here from step 1, only for xlsx
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
        st.session_state[FORMAT_MODE] = "raw"

    col_back, col_mask = st.columns([1, 1])
    with col_back:
        if st.button("Назад", use_container_width=True):
            st.session_state[STAGE] = STAGE_UPLOADED
            st.rerun()
    with col_mask:
        if st.button("Замаскировать", type="primary", use_container_width=True):
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
                progress.progress(60, text="Маскирование завершено. Генерируем файлы…")

                format_mode = st.session_state.get(FORMAT_MODE, "raw")
                if format_mode == "formatted" and file_path and file_path.lower().endswith(".xlsx"):
                    st.session_state[DL_XLSX] = generate_formatted_xlsx(file_path, masked_sheets)
                else:
                    st.session_state[DL_XLSX] = generate_masked_xlsx(masked_sheets)
                progress.progress(85, text="Файл готов. Генерируем маппинг…")

                st.session_state[DL_MAP_JSON] = generate_mapping_json(mapping)
                st.session_state[DL_MAP_XLSX] = generate_mapping_xlsx(mapping)
                progress.progress(100, text="Готово!")

                preview_masked = {name: df.head(5) for name, df in masked_sheets.items()}
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
    is_csv = file_name.lower().endswith(".csv")

    st.subheader(f"Результат маскирования: {file_name}")

    stat_col1, stat_col2 = st.columns(2)
    with stat_col1:
        st.metric("Замаскировано значений", stats["masked_values"])
    with stat_col2:
        st.metric("Уникальных сущностей", stats["unique_entities"])

    render_preview(masked_sheets)

    base_name = file_name.rsplit(".", 1)[0] if "." in file_name else file_name

    st.markdown("Скачать результат")
    col1, col2 = st.columns(2)

    with col1:
        if is_csv:
            csv_bytes = _generate_masked_csv(masked_sheets)
            st.download_button(
                label="Замаскированный файл (.csv)",
                data=csv_bytes,
                file_name=f"{base_name}_masked.csv",
                mime="text/csv",
                use_container_width=True,
                type="primary",
            )
        else:
            st.download_button(
                label="Замаскированный файл (.xlsx)",
                data=st.session_state[DL_XLSX],
                file_name=f"{base_name}_masked.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                type="primary",
            )

    with col2:
        st.download_button(
            label="Маппинг (.json)",
            data=st.session_state[DL_MAP_JSON],
            file_name=f"{base_name}_mapping.json",
            mime="application/json",
            use_container_width=True,
            type="primary",
        )

    st.download_button(
        label="Маппинг (Excel)",
        data=st.session_state[DL_MAP_XLSX],
        file_name=f"{base_name}_mapping.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        type="primary",
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
