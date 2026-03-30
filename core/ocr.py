"""OCR conversion via Docling for scanned PDFs and images.

Docling (IBM) performs layout-aware OCR locally — no external API calls.
Supports: PDF (scanned), PNG, JPG, JPEG, TIFF, BMP, WEBP.

Design decisions:
- Lazy import of docling to avoid startup penalty when OCR is not used
- Returns (markdown_text, error_message) tuple — no Streamlit dependency
- File is copied to a safe ASCII-only temp path before conversion
  (docling-parse C++ backend chokes on Cyrillic/spaces in file paths)
- ConversionError triggers a pikepdf repair pass, then retries Docling once
- If repair also fails, a user-friendly hint is shown
- OCR language(s) are passed via OcrOptions to improve recognition quality
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile

SUPPORTED_OCR_TYPES = ["pdf", "png", "jpg", "jpeg", "tiff", "bmp", "webp"]

# Human-readable language labels → Docling/EasyOCR language codes
OCR_LANGUAGES: dict[str, str] = {
    "Русский":     "ru",
    "Английский":  "en",
    "Немецкий":   "de",
    "Французский": "fr",
    "Испанский":  "es",
    "Итальянский": "it",
    "Китайский (упр.)": "ch_sim",
    "Японский":  "ja",
}

DEFAULT_LANGUAGES = ["Русский", "Английский"]

# Cyrillic → Latin transliteration table
_TRANSLIT = {
    "а": "a",  "б": "b",  "в": "v",  "г": "g",  "д": "d",
    "е": "e",  "ё": "yo", "ж": "zh", "з": "z",  "и": "i",
    "й": "j",  "к": "k",  "л": "l",  "м": "m",  "н": "n",
    "о": "o",  "п": "p",  "р": "r",  "с": "s",  "т": "t",
    "у": "u",  "ф": "f",  "х": "kh", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "sch","ъ": "",   "ы": "y",  "ь": "",
    "э": "e",  "ю": "yu", "я": "ya",
    "А": "A",  "Б": "B",  "В": "V",  "Г": "G",  "Д": "D",
    "Е": "E",  "Ё": "Yo", "Ж": "Zh", "З": "Z",  "И": "I",
    "Й": "J",  "К": "K",  "Л": "L",  "М": "M",  "Н": "N",
    "О": "O",  "П": "P",  "Р": "R",  "С": "S",  "Т": "T",
    "У": "U",  "Ф": "F",  "Х": "Kh", "Ц": "Ts", "Ч": "Ch",
    "Ш": "Sh", "Щ": "Sch","Ъ": "",   "Ы": "Y",  "Ь": "",
    "Э": "E",  "Ю": "Yu", "Я": "Ya",
}

_CONVERSION_ERROR_HINT = (
    "Файл не прошёл валидацию даже после попытки автоматического восстановления. Возможные причины:\n"
    "• PDF защищён паролем или запрещает копирование содержимого\n"
    "• Файл слишком сильно повреждён и не поддаётся восстановлению\n"
    "• Файл не является настоящим PDF (например, переименованный JPG)\n\n"
    "Попробуйте пересохранить PDF через Adobe Acrobat или LibreOffice и загрузить ещё раз."
)


def _safe_filename(name: str) -> str:
    result = "".join(_TRANSLIT.get(ch, ch) for ch in name)
    result = re.sub(r"[^A-Za-z0-9._-]", "_", result)
    result = re.sub(r"_+", "_", result).strip("_")
    return result or "document"


def _copy_to_safe_path(file_path: str) -> tuple[str, str]:
    original_name = os.path.basename(file_path)
    ext  = original_name.rsplit(".", 1)[-1] if "." in original_name else ""
    stem = original_name.rsplit(".", 1)[0]  if "." in original_name else original_name
    safe_name = f"{_safe_filename(stem)}.{ext}" if ext else _safe_filename(stem)
    tmp_dir   = tempfile.mkdtemp(prefix="enigma_ocr_")
    safe_path = os.path.join(tmp_dir, safe_name)
    shutil.copy2(file_path, safe_path)
    return safe_path, tmp_dir


def _repair_pdf(src_path: str, tmp_dir: str) -> str | None:
    try:
        import pikepdf
        repaired_path = os.path.join(tmp_dir, "repaired.pdf")
        with pikepdf.open(src_path, suppress_warnings=True) as pdf:
            pdf.save(repaired_path)
        return repaired_path
    except Exception:
        return None


def _run_docling(safe_path: str, lang_codes: list[str]) -> str:
    """Run Docling converter with given language codes. Raises on any error."""
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.pipeline_options import PdfPipelineOptions, EasyOcrOptions
    from docling.datamodel.base_models import InputFormat

    ocr_options = EasyOcrOptions(lang=lang_codes)
    pipeline_options = PdfPipelineOptions(
        do_ocr=True,
        do_table_structure=True,
        ocr_options=ocr_options,
    )
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )
    result = converter.convert(safe_path)
    return result.document.export_to_markdown()


def convert_with_docling(
    file_path: str,
    languages: list[str] | None = None,
) -> tuple[str, str | None]:
    """Convert a scanned file to Markdown using Docling OCR.

    Args:
        file_path: Absolute path to the file on disk.
        languages: List of human-readable language names from OCR_LANGUAGES.
                   Defaults to DEFAULT_LANGUAGES (['Русский', 'Английский']).

    Returns:
        (markdown_text, None) on success.
        ("", error_message) on failure.
    """
    try:
        from docling.exceptions import ConversionError
    except ImportError:
        return "", (
            "Библиотека Docling не установлена. "
            "Запустите: pip install docling"
        )

    selected = languages or DEFAULT_LANGUAGES
    lang_codes = [OCR_LANGUAGES[lang] for lang in selected if lang in OCR_LANGUAGES]
    if not lang_codes:
        lang_codes = ["ru", "en"]

    tmp_dir = None
    try:
        safe_path, tmp_dir = _copy_to_safe_path(file_path)

        try:
            md_text = _run_docling(safe_path, lang_codes)
        except ConversionError:
            repaired_path = _repair_pdf(safe_path, tmp_dir)
            if repaired_path is None:
                return "", _CONVERSION_ERROR_HINT
            try:
                md_text = _run_docling(repaired_path, lang_codes)
            except ConversionError:
                return "", _CONVERSION_ERROR_HINT

        if not md_text or not md_text.strip():
            return "", (
                "Текст не обнаружен. Проверьте качество скана или читаемость PDF. "
                "Также убедитесь, что выбраны правильные языки документа."
            )

        return md_text, None

    except Exception as e:
        return "", f"Неожиданная ошибка: {e}"

    finally:
        if tmp_dir and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)
