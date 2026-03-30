"""File → Markdown conversion view.

Two conversion engines:
  • MarkItDown (Microsoft) — fast, for text-based files
  • Docling (IBM)          — local OCR for scanned PDFs and images

Docling flow (3 steps, convertio-style):
  1. Загрузка файла
  2. Выбор языков и настройки
  3. Конвертация → скачать

MarkItDown flow (2 steps):
  1. Загрузка файла
  2. Конвертация → скачать
"""
from __future__ import annotations

import os
import tempfile

import streamlit as st

from core.ocr import OCR_LANGUAGES, DEFAULT_LANGUAGES
from ui.step_indicator import render_steps, STEPS_PDF_MD

_STAGE          = "pdf_md_stage"
_STAGE_UPLOAD   = "upload"
_STAGE_SETTINGS = "settings"   # Docling only
_STAGE_CONVERT  = "convert"
_STAGE_RESULT   = "result"

_FILE_PATH   = "pdf_md_file_path"
_FILE_NAME   = "pdf_md_file_name"
_FILE_SIZE   = "pdf_md_file_size"
_MD_RESULT   = "pdf_md_result"
_ENGINE_KEY  = "pdf_md_engine"
_LANGS_KEY   = "pdf_md_languages"

_MARKITDOWN_TYPES = ["pdf", "docx", "pptx", "xlsx", "csv", "json"]
_DOCLING_TYPES    = ["pdf", "png", "jpg", "jpeg", "tiff", "bmp", "webp"]

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
    elif stage == _STAGE_SETTINGS:
        _render_step_settings()
    elif stage == _STAGE_CONVERT:
        _render_step_convert()
    elif stage == _STAGE_RESULT:
        _render_step_result()


# ---------------------------------------------------------------------------
# Step 1 — Upload
# ---------------------------------------------------------------------------

def _render_step_upload() -> None:
    render_steps(current=1, steps=STEPS_PDF_MD)
    st.subheader("Шаг 1. Загрузите файл")

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

    uploaded = st.file_uploader(
        "Выберите файл",
        type=allowed_types,
        key=f"pdf_md_uploader_{engine}",
    )

    if uploaded is not None:
        if st.button("Далее", type="primary", use_container_width=True):
            upload_dir = os.path.join(tempfile.gettempdir(), "enigma_uploads")
            os.makedirs(upload_dir, exist_ok=True)
            file_path  = os.path.join(upload_dir, uploaded.name)
            file_bytes = uploaded.read()
            with open(file_path, "wb") as f:
                f.write(file_bytes)

            st.session_state[_FILE_PATH] = file_path
            st.session_state[_FILE_NAME] = uploaded.name
            st.session_state[_FILE_SIZE] = len(file_bytes)

            # Docling → go to settings; MarkItDown → skip straight to convert
            if engine == "docling":
                st.session_state[_STAGE] = _STAGE_SETTINGS
            else:
                st.session_state[_STAGE] = _STAGE_CONVERT
            st.rerun()


# ---------------------------------------------------------------------------
# Step 2 — Language & settings (Docling only)
# ---------------------------------------------------------------------------

def _render_step_settings() -> None:
    render_steps(current=2, steps=STEPS_PDF_MD)
    file_name = st.session_state.get(_FILE_NAME, "файл")

    st.subheader("Шаг 2. Язык и настройки")
    st.caption(f"Файл: **{file_name}**")

    st.markdown("**Выберите все языки, используемые в документе**")
    st.caption("Чем точнее вы укажете язык, тем выше точность распознавания.")

    all_langs = list(OCR_LANGUAGES.keys())
    saved     = st.session_state.get(_LANGS_KEY, DEFAULT_LANGUAGES)

    selected_langs = st.multiselect(
        "Языки документа",
        options=all_langs,
        default=[l for l in saved if l in all_langs],
        placeholder="Выберите один или несколько языков...",
    )

    if not selected_langs:
        st.warning("Выберите хотя бы один язык.")

    st.divider()
    st.info(
        "⏳ Первый запуск Docling загружает OCR-модель (несколько минут). "
        "Последующие конвертации будут быстрее.",
        icon="ℹ️",
    )

    col_back, col_next = st.columns([1, 1])
    with col_back:
        if st.button("Назад", use_container_width=True):
            _cleanup()
            st.rerun()
    with col_next:
        if st.button(
            "Приступить к распознаванию",
            type="primary",
            use_container_width=True,
            disabled=not selected_langs,
        ):
            st.session_state[_LANGS_KEY] = selected_langs
            st.session_state[_STAGE]     = _STAGE_CONVERT
            st.rerun()


# ---------------------------------------------------------------------------
# Step 3 — Convert
# ---------------------------------------------------------------------------

def _render_step_convert() -> None:
    render_steps(current=3, steps=STEPS_PDF_MD)
    file_name  = st.session_state.get(_FILE_NAME, "файл")
    file_size  = st.session_state.get(_FILE_SIZE, 0)
    engine     = st.session_state.get(_ENGINE_KEY, "markitdown")
    langs      = st.session_state.get(_LANGS_KEY, DEFAULT_LANGUAGES)
    ext        = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    type_label = _TYPE_LABELS.get(ext, "Файл")
    size_str   = f"{file_size / 1_048_576:.2f} MB" if file_size >= 1_048_576 else f"{file_size / 1024:.1f} KB"

    st.subheader("Шаг 3. Конвертация")
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
        langs_str = ", ".join(langs)
        st.info(f"🔍 **Docling OCR** • языки: {langs_str}")
    else:
        st.info("📄 **MarkItDown** — быстрое извлечение текста из файлов с текстовым слоем.")

    col_back, col_convert = st.columns([1, 1])
    with col_back:
        back_stage = _STAGE_SETTINGS if engine == "docling" else _STAGE_UPLOAD
        if st.button("Назад", use_container_width=True):
            st.session_state[_STAGE] = back_stage
            st.rerun()
    with col_convert:
        spinner_msg = (
            "🔍 OCR в процессе… (это может занять несколько минут)"
            if engine == "docling" else "Конвертируем…"
        )
        if st.button("Распознать", type="primary", use_container_width=True):
            with st.spinner(spinner_msg):
                md_text, error = _convert(
                    st.session_state[_FILE_PATH],
                    engine=engine,
                    languages=langs,
                )
            if error:
                st.error(error)
            else:
                st.session_state[_MD_RESULT] = md_text
                st.session_state[_STAGE]     = _STAGE_RESULT
                st.rerun()


# ---------------------------------------------------------------------------
# Step 4 — Result
# ---------------------------------------------------------------------------

def _render_step_result() -> None:
    render_steps(current=4, steps=STEPS_PDF_MD)
    md_text   = st.session_state[_MD_RESULT]
    file_name = st.session_state.get(_FILE_NAME, "файл")
    engine    = st.session_state.get(_ENGINE_KEY, "markitdown")
    langs     = st.session_state.get(_LANGS_KEY, DEFAULT_LANGUAGES)
    base      = file_name.rsplit(".", 1)[0] if "." in file_name else file_name

    st.subheader("Результат конвертации")
    if engine == "docling":
        st.caption(f"🔍 Docling OCR • {', '.join(langs)} • {file_name}")
    else:
        st.caption(f"📄 MarkItDown • {file_name}")

    col1, col2, col3 = st.columns(3)
    col1.metric("Строк",    f"{len(md_text.splitlines()):,}")
    col2.metric("Символов", f"{len(md_text):,}")
    col3.metric("Слов",     f"{len(md_text.split()):,}")

    st.markdown("**Превью (первые 1000 символов)**")
    st.code(md_text[:1000] + ("…" if len(md_text) > 1000 else ""), language="markdown")

    st.download_button(
        label="⬇️ Скачать .md файл",
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
            st.session_state[_STAGE] = _STAGE_CONVERT
            st.rerun()
    with col_reset:
        if st.button("Начать заново", use_container_width=True):
            _cleanup()
            st.rerun()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _file_emoji(ext: str) -> str:
    return {
        "pdf":  "📄", "docx": "📝", "pptx": "📊",
        "xlsx": "📊", "csv":  "📃", "json": "📄",
        "png":  "🖼️", "jpg":  "🖼️", "jpeg": "🖼️",
        "tiff": "🖼️", "bmp":  "🖼️", "webp": "🖼️",
    }.get(ext, "📄")


def _convert(
    file_path: str,
    engine: str = "markitdown",
    languages: list[str] | None = None,
) -> tuple[str, str | None]:
    if engine == "docling":
        from core.ocr import convert_with_docling
        return convert_with_docling(file_path, languages=languages)

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
        return "", 'pip install "markitdown[pdf]"'
    except Exception as e:
        return "", f"Ошибка при конвертации: {e}"


def _cleanup() -> None:
    file_path = st.session_state.get(_FILE_PATH)
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass
    for key in [_FILE_PATH, _FILE_NAME, _FILE_SIZE, _MD_RESULT, _STAGE, _ENGINE_KEY, _LANGS_KEY]:
        st.session_state.pop(key, None)
