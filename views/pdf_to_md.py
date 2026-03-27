"""File → Markdown conversion view (3-step flow).

Supported formats: PDF, DOCX, PPTX, XLSX, CSV, JSON.
Uses markitdown for conversion — works best with text-based files.
For large xlsx files (>30 MB or >500k rows) the user can choose to
convert only N rows instead of the full file.
"""
from __future__ import annotations

import os
import tempfile

import streamlit as st

from ui.step_indicator import render_steps, STEPS_PDF_MD

_STAGE         = "pdf_md_stage"
_STAGE_UPLOAD  = "upload"
_STAGE_CONVERT = "convert"
_STAGE_RESULT  = "result"

_FILE_PATH   = "pdf_md_file_path"
_FILE_NAME   = "pdf_md_file_name"
_FILE_SIZE   = "pdf_md_file_size"
_XLSX_ROWS   = "pdf_md_xlsx_rows"   # total row count for xlsx (int | None)
_MD_RESULT   = "pdf_md_result"

_SUPPORTED_TYPES = ["pdf", "docx", "pptx", "xlsx", "csv", "json"]

_TYPE_LABELS = {
    "pdf":  "PDF документ",
    "docx": "Word документ",
    "pptx": "PowerPoint презентация",
    "xlsx": "Excel таблица",
    "csv":  "CSV файл",
    "json": "JSON файл",
}

# Thresholds for large-xlsx warning
_XLSX_SIZE_THRESHOLD  = 30 * 1_048_576   # 30 MB
_XLSX_ROWS_THRESHOLD  = 500_000


def render() -> None:
    st.header("Конвертация в Markdown")
    stage = st.session_state.get(_STAGE, _STAGE_UPLOAD)
    if stage == _STAGE_UPLOAD:
        _render_step_upload()
    elif stage == _STAGE_CONVERT:
        _render_step_convert()
    elif stage == _STAGE_RESULT:
        _render_step_result()


def _render_step_upload() -> None:
    render_steps(current=1, steps=STEPS_PDF_MD)
    st.subheader("Загрузите файл")
    st.caption(
        "Поддерживаемые форматы: "
        + ", ".join(f"**.{t}**" for t in _SUPPORTED_TYPES)
        + ". Максимальный размер: 300 MB."
    )

    uploaded = st.file_uploader(
        "Выберите файл",
        type=_SUPPORTED_TYPES,
        key="pdf_md_uploader",
    )

    if uploaded is not None:
        if st.button("Далее", type="primary", use_container_width=True):
            upload_dir = os.path.join(tempfile.gettempdir(), "enigma_uploads")
            os.makedirs(upload_dir, exist_ok=True)
            file_path = os.path.join(upload_dir, uploaded.name)
            file_bytes = uploaded.read()
            with open(file_path, "wb") as f:
                f.write(file_bytes)

            ext = uploaded.name.rsplit(".", 1)[-1].lower() if "." in uploaded.name else ""
            xlsx_rows: int | None = None
            if ext == "xlsx":
                xlsx_rows = _count_xlsx_rows(file_path)

            st.session_state[_FILE_PATH]  = file_path
            st.session_state[_FILE_NAME]  = uploaded.name
            st.session_state[_FILE_SIZE]  = len(file_bytes)
            st.session_state[_XLSX_ROWS]  = xlsx_rows
            st.session_state[_STAGE]      = _STAGE_CONVERT
            st.rerun()


def _render_step_convert() -> None:
    render_steps(current=2, steps=STEPS_PDF_MD)
    file_name  = st.session_state.get(_FILE_NAME, "файл")
    file_size  = st.session_state.get(_FILE_SIZE, 0)
    xlsx_rows  = st.session_state.get(_XLSX_ROWS)
    ext        = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    type_label = _TYPE_LABELS.get(ext, "Файл")
    size_str   = f"{file_size / 1_048_576:.2f} MB" if file_size >= 1_048_576 else f"{file_size / 1024:.1f} KB"

    st.subheader("Конвертация")
    st.markdown(
        f"""
        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;
                    padding:1rem 1.2rem;margin-bottom:1rem;display:flex;gap:1rem;align-items:center">
            <span style="font-size:2rem">{_file_emoji(ext)}</span>
            <div>
                <div style="font-weight:600;color:#1e293b">{file_name}</div>
                <div style="font-size:0.85rem;color:#64748b">{type_label} • {size_str}{f" • {xlsx_rows:,} строк" if xlsx_rows else ""}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- Large xlsx warning + row-limit choice ---
    row_limit: int | None = None  # None = convert all
    is_large_xlsx = (
        ext == "xlsx"
        and (file_size > _XLSX_SIZE_THRESHOLD or (xlsx_rows and xlsx_rows > _XLSX_ROWS_THRESHOLD))
    )

    if is_large_xlsx:
        st.warning(
            "⚠️ **Большой Excel-файл** — конвертация всего файла может занять **5–15 минут**. "
            "Вы можете ограничить количество строк для быстрого результата.",
            icon=None,
        )
        limit_mode = st.radio(
            "Что конвертировать?",
            options=["Только N строк (быстро)", "Весь файл (долго)"],
            index=0,
            horizontal=True,
            key="xlsx_limit_mode",
        )
        if limit_mode == "Только N строк (быстро)":
            row_limit = st.number_input(
                "Количество строк",
                min_value=1,
                max_value=xlsx_rows or 1_000_000,
                value=min(10_000, xlsx_rows or 10_000),
                step=1_000,
                key="xlsx_row_limit",
            )
    else:
        st.info(
            "🕐 Извлекает текст и структуру из файла и переводит в формат Markdown. "
            "Не подходит для сканированных PDF."
        )

    col_back, col_convert = st.columns([1, 1])
    with col_back:
        if st.button("Назад", use_container_width=True):
            _cleanup()
            st.rerun()
    with col_convert:
        if st.button("Конвертировать", type="primary", use_container_width=True):
            with st.spinner("Конвертируем…"):
                md_text, error = _convert(
                    st.session_state[_FILE_PATH],
                    row_limit=int(row_limit) if row_limit is not None else None,
                )
            if error:
                st.error(error)
            else:
                st.session_state[_MD_RESULT] = md_text
                st.session_state[_STAGE]     = _STAGE_RESULT
                st.rerun()


def _render_step_result() -> None:
    render_steps(current=3, steps=STEPS_PDF_MD)
    md_text   = st.session_state[_MD_RESULT]
    file_name = st.session_state.get(_FILE_NAME, "файл")
    base      = file_name.rsplit(".", 1)[0] if "." in file_name else file_name

    st.subheader("Результат конвертации")

    col1, col2, col3 = st.columns(3)
    col1.metric("Строк",    f"{len(md_text.splitlines()):,}")
    col2.metric("Символов", f"{len(md_text):,}")
    col3.metric("Слов",     f"{len(md_text.split()):,}")

    st.markdown("**Превью (первые 1000 символов)**")
    st.code(md_text[:1000] + ("…" if len(md_text) > 1000 else ""), language="markdown")

    st.download_button(
        label="Скачать .md файл",
        data=md_text.encode("utf-8"),
        file_name=f"{base}.md",
        mime="text/markdown",
        use_container_width=True,
    )

    col_back, col_reset = st.columns([1, 1])
    with col_back:
        if st.button("Назад к конвертации", use_container_width=True):
            st.session_state.pop(_MD_RESULT, None)
            st.session_state[_STAGE] = _STAGE_CONVERT
            st.rerun()
    with col_reset:
        if st.button("Сбросить", use_container_width=True):
            _cleanup()
            st.rerun()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _file_emoji(ext: str) -> str:
    return {
        "pdf":  "📄",
        "docx": "📝",
        "pptx": "📊",
        "xlsx": "📊",
        "csv":  "📃",
        "json": "📄",
    }.get(ext, "📄")


def _count_xlsx_rows(file_path: str) -> int | None:
    """Count total data rows across all sheets (fast, header excluded)."""
    try:
        import pandas as pd
        sheets = pd.read_excel(file_path, sheet_name=None, engine="calamine", nrows=None)
        return sum(len(df) for df in sheets.values())
    except Exception:
        return None


def _convert(file_path: str, row_limit: int | None = None) -> tuple[str, str | None]:
    """Convert file to Markdown.

    For xlsx files with row_limit set, read only N rows per sheet,
    write to a temp file and convert that instead.
    """
    try:
        from markitdown import MarkItDown

        actual_path = file_path

        # If row limit requested for xlsx — write trimmed version to temp file
        if row_limit is not None and file_path.lower().endswith(".xlsx"):
            import pandas as pd
            sheets = pd.read_excel(file_path, sheet_name=None, engine="calamine")
            trimmed = {name: df.head(row_limit) for name, df in sheets.items()}
            tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
            tmp.close()
            with pd.ExcelWriter(tmp.name, engine="xlsxwriter") as writer:
                for name, df in trimmed.items():
                    df.to_excel(writer, sheet_name=name, index=False)
            actual_path = tmp.name

        md = MarkItDown()
        result = md.convert(actual_path)
        text = result.text_content

        # Cleanup temp file if created
        if actual_path != file_path:
            try:
                os.remove(actual_path)
            except OSError:
                pass

        if not text or not text.strip():
            return "", (
                "Файл не содержит извлекаемого текста. "
                "Проверьте, что файл не пустой и не является сканом."
            )
        return text, None

    except ImportError:
        return "", (
            "Библиотека markitdown не установлена. "
            "Запустите: pip install \"markitdown[pdf]\""
        )
    except Exception as e:
        return "", f"Ошибка при конвертации: {e}"


def _cleanup() -> None:
    file_path = st.session_state.get(_FILE_PATH)
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass
    for key in [_FILE_PATH, _FILE_NAME, _FILE_SIZE, _XLSX_ROWS, _MD_RESULT, _STAGE]:
        st.session_state.pop(key, None)
