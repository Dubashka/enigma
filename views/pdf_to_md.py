"""File → Markdown conversion view (3-step flow).

Two conversion engines:
  • MarkItDown (Microsoft) — fast, for text-based files (PDF with text layer,
    DOCX, PPTX, XLSX, CSV, JSON)
  • Docling (IBM) — local OCR, for scanned PDFs and images
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
_ENGINE_KEY  = "pdf_md_engine"

# Formats by engine
_MARKITDOWN_TYPES = ["pdf", "docx", "pptx", "xlsx", "csv", "json"]
_DOCLING_TYPES    = ["pdf", "png", "jpg", "jpeg", "tiff", "bmp", "webp"]
_ALL_TYPES        = sorted(set(_MARKITDOWN_TYPES + _DOCLING_TYPES))

_TYPE_LABELS = {
    "pdf":  "PDF документ",
    "docx": "Word документ",
    "pptx": "PowerPoint презентация",
    "xlsx": "Excel таблица",
    "csv":  "CSV файл",
    "json": "JSON файл",
    "png":  "PNG изображение",
    "jpg":  "JPG изображение",
    "jpeg": "JPEG изображение",
    "tiff": "TIFF изображение",
    "bmp":  "BMP изображение",
    "webp": "WebP изображение",
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

    # Engine selector
    engine = st.radio(
        "Движок конвертации",
        options=["markitdown", "docling"],
        format_func=lambda x: (
            "📄 MarkItDown — текстовые файлы (PDF, DOCX, PPTX, XLSX, CSV, JSON)"
            if x == "markitdown"
            else "🔍 Docling OCR — сканы и изображения (PDF, PNG, JPG, TIFF и др.)"
        ),
        horizontal=True,
        index=0 if st.session_state.get(_ENGINE_KEY, "markitdown") == "markitdown" else 1,
        key="engine_radio",
    )
    st.session_state[_ENGINE_KEY] = engine

    if engine == "markitdown":
        allowed_types = _MARKITDOWN_TYPES
        st.caption(
            "Форматы: "
            + ", ".join(f"**.{t}**" for t in _MARKITDOWN_TYPES)
            + ". Работает только с файлами, содержащими текстовый слой."
        )
    else:
        allowed_types = _DOCLING_TYPES
        st.caption(
            "Форматы: "
            + ", ".join(f"**.{t}**" for t in _DOCLING_TYPES)
            + ". OCR выполняется локально, без отправки данных во внешние сервисы."
        )
        st.info(
            "⏳ Первый запуск Docling загружает модель (несколько минут). "
            "Последующие конвертации будут быстрее.",
            icon="ℹ️",
        )

    uploaded = st.file_uploader(
        "Выберите файл",
        type=allowed_types,
        key=f"pdf_md_uploader_{engine}",
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
    engine     = st.session_state.get(_ENGINE_KEY, "markitdown")
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
                <div style="font-size:0.85rem;color:#64748b">{type_label} • {size_str}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if engine == "docling":
        st.info(
            "🔍 Движок: **Docling OCR** — локальное распознавание текста с сохранением структуры и таблиц. "
            "Обработка может занять несколько минут в зависимости от размера файла."
        )
    else:
        st.info(
            "📄 Движок: **MarkItDown** — быстрое извлечение текста из файлов с текстовым слоем. "
            "Не подходит для сканов."
        )

    col_back, col_convert = st.columns([1, 1])
    with col_back:
        if st.button("Назад", use_container_width=True):
            _cleanup()
            st.rerun()
    with col_convert:
        if st.button("Конвертировать", type="primary", use_container_width=True):
            spinner_msg = (
                "🔍 OCR в процессе… (это может занять несколько минут)"
                if engine == "docling"
                else "Конвертируем…"
            )
            with st.spinner(spinner_msg):
                md_text, error = _convert(
                    st.session_state[_FILE_PATH],
                    engine=engine,
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
    engine    = st.session_state.get(_ENGINE_KEY, "markitdown")
    base      = file_name.rsplit(".", 1)[0] if "." in file_name else file_name

    st.subheader("Результат конвертации")
    engine_badge = "🔍 Docling OCR" if engine == "docling" else "📄 MarkItDown"
    st.caption(f"{engine_badge} • {file_name}")

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
        "png":  "🖼️",
        "jpg":  "🖼️",
        "jpeg": "🖼️",
        "tiff": "🖼️",
        "bmp":  "🖼️",
        "webp": "🖼️",
    }.get(ext, "📄")


def _convert(file_path: str, engine: str = "markitdown") -> tuple[str, str | None]:
    """Dispatch conversion to the selected engine."""
    if engine == "docling":
        from core.ocr import convert_with_docling
        return convert_with_docling(file_path)

    # MarkItDown path
    try:
        from markitdown import MarkItDown
        md = MarkItDown()
        result = md.convert(file_path)
        text = result.text_content
        if not text or not text.strip():
            return "", (
                "Файл не содержит извлекаемого текста. "
                "Если это скан, выберите движок 🔍 Docling OCR."
            )
        return text, None
    except ImportError:
        return "", (
            "Библиотека markitdown не установлена. "
            'pip install "markitdown[pdf]"'
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
    for key in [_FILE_PATH, _FILE_NAME, _FILE_SIZE, _MD_RESULT, _STAGE, _ENGINE_KEY]:
        st.session_state.pop(key, None)
