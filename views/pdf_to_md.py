"""File → Markdown conversion view (3-step flow).

Использует Docling для конвертации всех поддерживаемых форматов.
Docling автоматически определяет тип PDF (текстовый / скан) и применяет
OCR при необходимости — ручной выбор пути не требуется.

Поддерживаемые форматы: PDF, DOCX, PPTX, XLSX, CSV, JSON.
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
_MD_RESULT   = "pdf_md_result"
_CONV_META   = "pdf_md_conv_meta"   # dict с метаданными конвертации

_SUPPORTED_TYPES = ["pdf", "docx", "pptx", "xlsx", "csv", "json"]

_TYPE_LABELS = {
    "pdf":  "PDF документ",
    "docx": "Word документ",
    "pptx": "PowerPoint презентация",
    "xlsx": "Excel таблица",
    "csv":  "CSV файл",
    "json": "JSON файл",
}


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

    uploaded = st.file_uploader(
        " ",
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

            st.session_state[_FILE_PATH] = file_path
            st.session_state[_FILE_NAME] = uploaded.name
            st.session_state[_FILE_SIZE] = len(file_bytes)
            st.session_state[_STAGE]     = _STAGE_CONVERT
            st.rerun()


def _render_step_convert() -> None:
    render_steps(current=2, steps=STEPS_PDF_MD)
    file_name  = st.session_state.get(_FILE_NAME, "файл")
    file_size  = st.session_state.get(_FILE_SIZE, 0)
    ext        = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    type_label = _TYPE_LABELS.get(ext, "Файл")
    size_str   = (
        f"{file_size / 1_048_576:.2f} MB"
        if file_size >= 1_048_576
        else f"{file_size / 1024:.1f} KB"
    )
    is_pdf = ext == "pdf"

    st.subheader("Конвертация")
    st.markdown(
        f"""
        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;
                    padding:1rem 1.2rem;margin-bottom:1rem;display:flex;gap:1rem;align-items:center">
            <span style="font-size:2rem">{_file_emoji(ext)}</span>
            <div>
                <div style="font-weight:600;color:#1e293b">{file_name}</div>
                <div style="font-size:0.85rem;color:#64748b">{type_label} • {size_str}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Опция форсирования OCR — только для PDF
    force_ocr = False
    if is_pdf:
        force_ocr = st.checkbox(
            "Принудительный OCR (для сканов)",
            value=False,
            help=(
                "Docling автоматически определяет тип PDF и применяет OCR при необходимости. "
                "Включите эту опцию только если автоматическое определение не сработало."
            ),
        )
        if not force_ocr:
            st.info(
                "ℹ️ Docling автоматически определит тип PDF и применит OCR для сканов."
            )
        else:
            st.info("⏰ Принудительный OCR может занять несколько минут.")

    col_back, col_convert = st.columns([1, 1])
    with col_back:
        if st.button("Назад", use_container_width=True):
            _cleanup()
            st.rerun()
    with col_convert:
        if st.button("Конвертировать", type="primary", use_container_width=True):
            file_path = st.session_state[_FILE_PATH]
            with st.spinner("Конвертируем через Docling…"):
                md_text, meta, error = _convert_docling(
                    file_path,
                    force_full_ocr=force_ocr,
                )
            if error:
                st.error(error)
            else:
                st.session_state[_MD_RESULT] = md_text
                st.session_state[_CONV_META] = meta
                st.session_state[_STAGE]     = _STAGE_RESULT
                st.rerun()


def _render_step_result() -> None:
    render_steps(current=3, steps=STEPS_PDF_MD)
    file_name = st.session_state.get(_FILE_NAME, "файл")
    base      = file_name.rsplit(".", 1)[0] if "." in file_name else file_name
    md_text   = st.session_state.get(_MD_RESULT, "")
    meta      = st.session_state.get(_CONV_META, {})

    st.subheader("Результат конвертации")

    # Метрики
    col1, col2, col3 = st.columns(3)
    col1.metric("Строк",    f"{len(md_text.splitlines()):,}")
    col2.metric("Символов", f"{len(md_text):,}")
    col3.metric("Слов",     f"{len(md_text.split()):,}")

    # Инфо о методе конвертации
    if meta.get("ocr_applied"):
        st.success("✅ Применён OCR (Docling автоматически определил скан)")
    elif meta.get("force_ocr"):
        st.success("✅ Применён принудительный OCR")
    else:
        st.success("✅ Текст извлечён напрямую (текстовый документ)")

    if meta.get("pages"):
        st.caption(f"Страниц обработано: {meta['pages']}")

    # Превью
    st.markdown("**Превью (первые 1000 символов)**")
    st.code(
        md_text[:1000] + ("…" if len(md_text) > 1000 else ""),
        language="markdown",
    )

    st.download_button(
        label="Скачать .md файл",
        data=md_text.encode("utf-8"),
        file_name=f"{base}.md",
        mime="text/markdown",
        use_container_width=True,
        type="primary",
    )

    col_back, col_reset = st.columns([1, 1])
    with col_back:
        if st.button("Назад к конвертации", use_container_width=True):
            st.session_state.pop(_MD_RESULT, None)
            st.session_state.pop(_CONV_META, None)
            st.session_state[_STAGE] = _STAGE_CONVERT
            st.rerun()
    with col_reset:
        if st.button("Сбросить", use_container_width=True):
            _cleanup()
            st.rerun()


# ---------------------------------------------------------------------------
# Docling конвертер
# ---------------------------------------------------------------------------

def _convert_docling(
    file_path: str,
    force_full_ocr: bool = False,
) -> tuple[str, dict, str | None]:
    """Конвертировать файл в Markdown через Docling.

    Returns:
        (md_text, meta, error)
        meta содержит: ocr_applied, force_ocr, pages
    """
    try:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
    except ImportError:
        return "", {}, 'Установите Docling: pip install "docling>=2.0.0"'

    try:
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = True          # Docling решает когда применять OCR
        pipeline_options.do_table_structure = True

        if force_full_ocr:
            # Форсируем OCR на каждой странице
            pipeline_options.ocr_options.force_full_page_ocr = True

        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )

        result = converter.convert(file_path)
        doc    = result.document
        md_text = doc.export_to_markdown()

        if not md_text or not md_text.strip():
            return "", {}, "Не удалось извлечь текст из документа."

        # Собираем метаданные
        meta: dict = {
            "ocr_applied": getattr(result, "ocr_applied", False),
            "force_ocr":   force_full_ocr,
            "pages":       getattr(doc, "num_pages", None),
        }

        return md_text, meta, None

    except Exception as exc:
        return "", {}, f"Ошибка Docling: {exc}"


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


def _cleanup() -> None:
    file_path = st.session_state.get(_FILE_PATH)
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass
    for key in [_FILE_PATH, _FILE_NAME, _FILE_SIZE, _MD_RESULT, _CONV_META, _STAGE]:
        st.session_state.pop(key, None)
