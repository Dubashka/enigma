import io
import zipfile
import streamlit as st
from core.output import generate_masked_xlsx, generate_formatted_xlsx, generate_mapping_json, generate_mapping_xlsx
from core.state_keys import (
    SHEETS, RAW_BYTES, STAGE, FILE_NAME, FILE_PATH,
    STAGE_UPLOADED, STAGE_COLUMNS, STAGE_MASKED,
    SELECTED_COLUMNS, MASK_CONFIG, MAPPING, MASKED_SHEETS, STATS,
    DL_XLSX, DL_MAP_JSON, DL_MAP_XLSX, FORMAT_MODE,
    AI_RESULTS,
)
from core.ai_checker import check_columns_with_ai
from core.parser import save_upload, parse_preview, parse_full, cleanup_upload
from core.detector import detect_sensitive_columns, classify_column_type
from core.masker import mask_sheets
from ui.upload_widget import render_preview
from ui.step_indicator import render_steps
from ui.column_selector import render_column_selector

import pandas as pd
import requests


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
       # "Форматы: Excel (.xlsx) или CSV (.csv). Максимальный размер: 200 MB.",
       # type=["xlsx", "csv"],
       # key="file_uploader_mask",
        label="Загрузить файл для маскирования",  # ← русский
        type=["xlsx", "xls"],
        key="masking_upload",
        help="Поддерживаемые форматы: XLSX, XLS. Максимум 200 MB."
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

    col_back, col_next, col_ai = st.columns([1, 1, 1])
    with col_back:
        if st.button("Сбросить", use_container_width=True):
            _cleanup_and_reset()
            st.rerun()
    with col_next:
        if st.button("Далее", use_container_width=True):
            st.session_state[STAGE] = STAGE_COLUMNS
            st.rerun()
    with col_ai:
        if st.button("Маскирование с AI", type="primary", use_container_width=True):
            with st.status("Анализируем столбцы с помощью AI…", expanded=True) as status:
                st.write("🔍 Сканируем данные на наличие email, телефонов, IP…")
                _, presidio_required = detect_sensitive_columns(sheets)
                st.write("📤 Отправляем данные в LM Studio…")
                try:
                    result = check_columns_with_ai(sheets, presidio_required=presidio_required)
                except requests.exceptions.ConnectionError:
                    status.update(label="Ошибка подключения", state="error")
                    st.error("Не удалось подключиться к LM Studio. Убедитесь, что он запущен на http://127.0.0.1:1234")
                    st.stop()
                except Exception as exc:
                    status.update(label="Ошибка", state="error")
                    st.error(f"Ошибка при обращении к AI: {exc}")
                    st.stop()
                st.write("✅ Ответ получен, применяем рекомендации…")
                for sheet_name, cols in presidio_required.items():
                    for col in cols:
                        if sheet_name in result:
                            result[sheet_name][col] = "required"
                st.session_state[AI_RESULTS] = result
                _apply_ai_to_checkboxes(sheets, result)
                status.update(label="Анализ завершён!", state="complete")
            st.session_state[STAGE] = STAGE_COLUMNS
            st.rerun()


def _render_step_columns() -> None:
    render_steps(current=2)
    sheets = st.session_state[SHEETS]
    ai_results = st.session_state.get(AI_RESULTS)

    # Show AI results summary (collapsed by default)
    if ai_results is not None:
        _render_ai_summary(ai_results)

    st.info("При необходимости отредактируйте выбор колонок вручную.")

    # Recompute detection — fast and stateless
    detected, presidio_required = detect_sensitive_columns(sheets)

    render_column_selector(sheets, detected, ai_results=ai_results, presidio_required=presidio_required)

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
                # Save verdicts to library based on user's actual selection
                ai_results = st.session_state.get(AI_RESULTS, {})
                try:
                    from core.library import AttributeLibrary
                    lib = AttributeLibrary()
                    for sheet_name, df in sheets.items():
                        sheet_ai = ai_results.get(sheet_name, {})
                        selected_cols = set(mask_config.get(sheet_name, {}).keys())
                        for col in df.columns:
                            if col in selected_cols:
                                # User chose to mask: keep AI verdict, but at least "required"
                                ai_verdict = sheet_ai.get(col, "required")
                                verdict = ai_verdict if ai_verdict in ("required", "recommended") else "required"
                            else:
                                # User chose not to mask
                                verdict = "safe"
                            lib.save_classification(col, verdict)
                except Exception:
                    pass

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


def _render_ai_summary(ai_results: dict[str, dict[str, str]]) -> None:
    """Render a summary panel showing AI column classification counts."""
    required_cols: list[str] = []
    recommended_cols: list[str] = []
    safe_cols: list[str] = []

    for sheet_name, cols in ai_results.items():
        for col, verdict in cols.items():
            label = f"{col}" if len(ai_results) == 1 else f"{sheet_name} → {col}"
            if verdict == "required":
                required_cols.append(label)
            elif verdict == "recommended":
                recommended_cols.append(label)
            else:
                safe_cols.append(label)

    with st.expander("Результат AI-анализа", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("⚠ Обязательно маскировать", len(required_cols))
            for name in required_cols:
                st.markdown(
                    f"<span style='font-size:0.8em;color:#c0392b'>• {name}</span>",
                    unsafe_allow_html=True,
                )
        with c2:
            st.metric("● Рекомендуется маскировать", len(recommended_cols))
            for name in recommended_cols:
                st.markdown(
                    f"<span style='font-size:0.8em;color:#856404'>• {name}</span>",
                    unsafe_allow_html=True,
                )
        with c3:
            st.metric("✓ Маскировать не нужно", len(safe_cols))
            for name in safe_cols:
                st.markdown(
                    f"<span style='font-size:0.8em;color:#2e7d32'>• {name}</span>",
                    unsafe_allow_html=True,
                )


def _apply_ai_to_checkboxes(
    sheets: dict,
    ai_results: dict[str, dict[str, str]],
) -> None:
    """Pre-set checkbox session-state keys based on AI verdicts."""
    for sheet_name, df in sheets.items():
        sheet_ai = ai_results.get(sheet_name, {})
        for col in df.columns:
            verdict = sheet_ai.get(col, "safe")
            st.session_state[f"cb_{sheet_name}_{col}"] = verdict in ("required", "recommended")


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
        DL_XLSX, DL_MAP_JSON, DL_MAP_XLSX, FORMAT_MODE, AI_RESULTS,
    ] + keys_to_clear:
        st.session_state.pop(key, None)
