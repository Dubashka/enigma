"""File → Markdown / OCR conversion view (3-step flow).

Supported formats: PDF, DOCX, PPTX, XLSX, CSV, JSON.

Two conversion paths for PDF:
- Text-based PDF  → markitdown (fast, preserves structure)
- Scanned PDF     → Tesseract OCR via core.ocr (pdf2image + pytesseract)

The path is chosen automatically: if markitdown returns < 50 non-whitespace
chars the file is treated as a scan and the OCR branch is activated.
The user can also force OCR manually via a checkbox on the convert step.
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

_FILE_PATH    = "pdf_md_file_path"
_FILE_NAME    = "pdf_md_file_name"
_FILE_SIZE    = "pdf_md_file_size"
_MD_RESULT    = "pdf_md_result"      # str  — markitdown path
_OCR_PAGES    = "pdf_md_ocr_pages"   # list[dict] — OCR path
_IS_OCR       = "pdf_md_is_ocr"      # bool

_SUPPORTED_TYPES = ["pdf", "docx", "pptx", "xlsx", "csv", "json"]

_TYPE_LABELS = {
    "pdf":  "PDF документ",
    "docx": "Word документ",
    "pptx": "PowerPoint презентация",
    "xlsx": "Excel таблица",
    "csv":  "CSV файл",
    "json": "JSON файл",
}

_LANG_OPTIONS = {
    "Русский + Английский": "rus+eng",
    "Только русский":       "rus",
    "Только английский":    "eng",
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
    size_str   = f"{file_size / 1_048_576:.2f} MB" if file_size >= 1_048_576 else f"{file_size / 1024:.1f} KB"
    is_pdf     = ext == "pdf"

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

    # OCR options — shown only for PDF files
    force_ocr = False
    ocr_lang  = "rus+eng"
    if is_pdf:
        force_ocr = st.checkbox(
            "📖 Это сканированный PDF (использовать OCR)",
            value=False,
            help=(
                "Включите, если PDF состоит из отсканированных страниц "
                "и не содержит выделяемого текста. "
                "Требует установленного Tesseract."
            ),
        )
        if force_ocr:
            lang_label = st.selectbox(
                "Язык распознавания",
                options=list(_LANG_OPTIONS.keys()),
                index=0,
            )
            ocr_lang = _LANG_OPTIONS[lang_label]
            st.info(
                "⏰ OCR обрабатывает каждую страницу отдельно — это может занять "
                "несколько минут для многостраничных документов."
            )
        else:
            st.info(
                "⏰ Извлекает текст и структуру из файла и переводит в формат Markdown. "
                "Не подходит для сканированных PDF — включите чекбокс выше."
            )

    col_back, col_convert = st.columns([1, 1])
    with col_back:
        if st.button("Назад", use_container_width=True):
            _cleanup()
            st.rerun()
    with col_convert:
        if st.button("Конвертировать", type="primary", use_container_width=True):
            file_path = st.session_state[_FILE_PATH]
            if is_pdf and force_ocr:
                # --- OCR branch ---
                with st.spinner("Распознаём текст через Tesseract…"):
                    pages, error = _run_ocr(file_path, lang=ocr_lang)
                if error:
                    st.error(error)
                else:
                    st.session_state[_OCR_PAGES] = pages
                    st.session_state[_IS_OCR]    = True
                    st.session_state[_STAGE]     = _STAGE_RESULT
                    st.rerun()
            else:
                # --- markitdown branch ---
                with st.spinner("Конвертируем…"):
                    md_text, error = _convert_markitdown(file_path)
                if error:
                    st.error(error)
                elif _is_scanned(md_text):
                    # Auto-detect: markitdown returned nothing — prompt user
                    st.warning(
                        "⚠️ Не удалось извлечь текст из PDF. "
                        "Похоже, это сканированный документ. "
                        "Включите чекбокс **\"Это сканированный PDF\"** и попробуйте снова."
                    )
                else:
                    st.session_state[_MD_RESULT] = md_text
                    st.session_state[_IS_OCR]    = False
                    st.session_state[_STAGE]     = _STAGE_RESULT
                    st.rerun()


def _render_step_result() -> None:
    render_steps(current=3, steps=STEPS_PDF_MD)
    is_ocr    = st.session_state.get(_IS_OCR, False)
    file_name = st.session_state.get(_FILE_NAME, "файл")
    base      = file_name.rsplit(".", 1)[0] if "." in file_name else file_name

    st.subheader("Результат конвертации")

    if is_ocr:
        _render_ocr_result(base)
    else:
        _render_md_result(base)

    col_back, col_reset = st.columns([1, 1])
    with col_back:
        if st.button("Назад к конвертации", use_container_width=True):
            st.session_state.pop(_MD_RESULT, None)
            st.session_state.pop(_OCR_PAGES, None)
            st.session_state.pop(_IS_OCR, None)
            st.session_state[_STAGE] = _STAGE_CONVERT
            st.rerun()
    with col_reset:
        if st.button("Сбросить", use_container_width=True):
            _cleanup()
            st.rerun()


def _render_md_result(base: str) -> None:
    """Result section for markitdown path."""
    md_text = st.session_state[_MD_RESULT]

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
    )


def _render_ocr_result(base: str) -> None:
    """Result section for OCR path — three download formats."""
    from core.output import generate_ocr_txt, generate_ocr_md, generate_ocr_json

    pages = st.session_state[_OCR_PAGES]
    total_chars = sum(len(p["text"]) for p in pages)
    total_words = sum(len(p["text"].split()) for p in pages)

    col1, col2, col3 = st.columns(3)
    col1.metric("Страниц",  str(len(pages)))
    col2.metric("Символов", f"{total_chars:,}")
    col3.metric("Слов",     f"{total_words:,}")

    # Preview first page
    st.markdown("**Превью — страница 1**")
    preview = pages[0]["text"] if pages else ""
    st.code(
        preview[:1000] + ("…" if len(preview) > 1000 else ""),
        language="",
    )

    st.markdown("**Скачать результат**")
    dl1, dl2, dl3 = st.columns(3)
    with dl1:
        st.download_button(
            label="⬇️ Скачать .txt",
            data=generate_ocr_txt(pages),
            file_name=f"{base}_ocr.txt",
            mime="text/plain",
            use_container_width=True,
        )
    with dl2:
        st.download_button(
            label="⬇️ Скачать .md",
            data=generate_ocr_md(pages),
            file_name=f"{base}_ocr.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with dl3:
        st.download_button(
            label="⬇️ Скачать .json",
            data=generate_ocr_json(pages),
            file_name=f"{base}_ocr.json",
            mime="application/json",
            use_container_width=True,
        )


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


def _is_scanned(text: str) -> bool:
    """True if markitdown returned suspiciously little text (likely a scan)."""
    from core.ocr import is_scanned_pdf
    return is_scanned_pdf(text)


def _convert_markitdown(file_path: str) -> tuple[str, str | None]:
    try:
        from markitdown import MarkItDown
        md = MarkItDown()
        result = md.convert(file_path)
        text = result.text_content
        if text is None:
            text = ""
        return text, None
    except ImportError:
        return "", (
            "Библиотека markitdown не установлена. "
            'Запустите: pip install "markitdown[pdf]"'
        )
    except Exception as e:
        return "", f"Ошибка при конвертации: {e}"


def _run_ocr(file_path: str, lang: str = "rus+eng") -> tuple[list[dict], str | None]:
    try:
        from core.ocr import ocr_pdf
        pages = ocr_pdf(file_path, lang=lang)
        if not any(p["text"] for p in pages):
            return pages, (
                "OCR не смог распознать текст. "
                "Проверьте качество скана и наличие нужного языкового пакета Tesseract."
            )
        return pages, None
    except ImportError as e:
        return [], str(e)
    except RuntimeError as e:
        return [], str(e)
    except Exception as e:
        return [], f"Ошибка OCR: {e}"


def _cleanup() -> None:
    file_path = st.session_state.get(_FILE_PATH)
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass
    for key in [_FILE_PATH, _FILE_NAME, _FILE_SIZE, _MD_RESULT, _OCR_PAGES, _IS_OCR, _STAGE]:
        st.session_state.pop(key, None)
