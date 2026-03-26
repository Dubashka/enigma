"""PDF → Markdown conversion view (3-step flow).

Uses markitdown for fast text-based PDF conversion.
No OCR — works best with native text PDFs.
"""
from __future__ import annotations

import os
import tempfile

import streamlit as st

from ui.step_indicator import render_steps

_STAGE     = "pdf_md_stage"
_STAGE_UPLOAD  = "upload"
_STAGE_CONVERT = "convert"
_STAGE_RESULT  = "result"

_FILE_PATH  = "pdf_md_file_path"
_FILE_NAME  = "pdf_md_file_name"
_PAGE_COUNT = "pdf_md_page_count"
_MD_RESULT  = "pdf_md_result"

STEPS = ["Загрузка PDF", "Настройка", "Результат"]


def render() -> None:
    st.header("Конвертация PDF → Markdown")
    stage = st.session_state.get(_STAGE, _STAGE_UPLOAD)
    if stage == _STAGE_UPLOAD:
        _render_step_upload()
    elif stage == _STAGE_CONVERT:
        _render_step_convert()
    elif stage == _STAGE_RESULT:
        _render_step_result()


def _render_step_upload() -> None:
    render_steps(current=1)
    st.subheader("Загрузите PDF-файл")
    st.caption("Поддерживаются текстовые PDF (не сканы). Максимальный размер: 300 MB.")

    uploaded = st.file_uploader(
        "Выберите PDF-файл",
        type=["pdf"],
        key="pdf_md_uploader",
    )

    if uploaded is not None:
        if st.button("Далее", type="primary", use_container_width=True):
            upload_dir = os.path.join(tempfile.gettempdir(), "enigma_uploads")
            os.makedirs(upload_dir, exist_ok=True)
            file_path = os.path.join(upload_dir, uploaded.name)
            with open(file_path, "wb") as f:
                f.write(uploaded.read())

            st.session_state[_FILE_PATH]  = file_path
            st.session_state[_FILE_NAME]  = uploaded.name
            st.session_state[_PAGE_COUNT] = _count_pages(file_path)
            st.session_state[_STAGE]      = _STAGE_CONVERT
            st.rerun()


def _render_step_convert() -> None:
    render_steps(current=2)
    file_name  = st.session_state.get(_FILE_NAME, "файл")
    page_count = st.session_state.get(_PAGE_COUNT, "?")

    st.subheader("Настройка конвертации")
    st.markdown(
        f"""
        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;
                    padding:1rem 1.2rem;margin-bottom:1rem;display:flex;gap:1rem;align-items:center">
            <span style="font-size:2rem">📄</span>
            <div>
                <div style="font-weight:600;color:#1e293b">{file_name}</div>
                <div style="font-size:0.85rem;color:#64748b">Страниц: {page_count}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.info(
        "🕐 **Быстрый режим** — извлекает текст, заголовки и таблицы из текстового PDF. "
        "Не подходит для сканированных документов."
    )

    col_back, col_convert = st.columns([1, 1])
    with col_back:
        if st.button("Назад", use_container_width=True):
            _cleanup()
            st.rerun()
    with col_convert:
        if st.button("Конвертировать", type="primary", use_container_width=True):
            with st.spinner("Конвертируем…"):
                md_text, error = _convert(st.session_state[_FILE_PATH])
            if error:
                st.error(error)
            else:
                st.session_state[_MD_RESULT] = md_text
                st.session_state[_STAGE]     = _STAGE_RESULT
                st.rerun()


def _render_step_result() -> None:
    render_steps(current=3)
    md_text   = st.session_state[_MD_RESULT]
    file_name = st.session_state.get(_FILE_NAME, "файл")
    base      = file_name.rsplit(".", 1)[0] if "." in file_name else file_name

    st.subheader("Результат конвертации")

    col1, col2, col3 = st.columns(3)
    col1.metric("Строк",    f"{len(md_text.splitlines()):,}")
    col2.metric("Символов", f"{len(md_text):,}")
    col3.metric("Слов",     f"{len(md_text.split()):,}")

    st.markdown("**Превью (первые 2000 символов)**")
    st.code(md_text[:2000] + ("…" if len(md_text) > 2000 else ""), language="markdown")

    st.download_button(
        label="Скачать .md файл",
        data=md_text.encode("utf-8"),
        file_name=f"{base}.md",
        mime="text/markdown",
        use_container_width=True,
    )

    col_back, col_reset = st.columns([1, 1])
    with col_back:
        if st.button("Назад к настройкам", use_container_width=True):
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

def _count_pages(file_path: str) -> int | str:
    try:
        import fitz
        doc = fitz.open(file_path)
        count = doc.page_count
        doc.close()
        return count
    except Exception:
        return "?"


def _convert(file_path: str) -> tuple[str, str | None]:
    try:
        from markitdown import MarkItDown
        md = MarkItDown()
        result = md.convert(file_path)
        text = result.text_content
        if not text or not text.strip():
            return "", (
                "Файл не содержит извлекаемого текста. "
                "Возможно, это сканированный PDF — для него нужен OCR-режим."
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
    for key in [_FILE_PATH, _FILE_NAME, _PAGE_COUNT, _MD_RESULT, _STAGE]:
        st.session_state.pop(key, None)
