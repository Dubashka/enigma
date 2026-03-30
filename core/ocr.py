"""OCR conversion via Docling for scanned PDFs and images.

Docling (IBM) performs layout-aware OCR locally — no external API calls.
Supports: PDF (scanned), PNG, JPG, JPEG, TIFF, BMP, WEBP.

Design decisions:
- Lazy import of docling to avoid startup penalty when OCR is not used
- Returns (markdown_text, error_message) tuple — no Streamlit dependency
- File is copied to a safe ASCII-only temp path before conversion
  (docling-parse C++ backend chokes on Cyrillic/spaces in file paths)
- ConversionError is caught separately to give the user actionable hints
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile

SUPPORTED_OCR_TYPES = ["pdf", "png", "jpg", "jpeg", "tiff", "bmp", "webp"]

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
    "Файл не прошёл валидацию Docling. Возможные причины:\n"
    "• Файл повреждён или неполностью загрузился\n"
    "• PDF защищён паролем или запрещает копирование содержимого\n"
    "• Файл создан нестандартным ПО (старый сканер, конвертер онлайн)\n"
    "• Файл не является настоящим PDF (например, переименованный JPG)\n\n"
    "Попробуйте пересохранить PDF через Adobe Acrobat или LibreOffice и загрузить ещё раз."
)


def _safe_filename(name: str) -> str:
    """Transliterate Cyrillic, replace spaces and unsafe chars with underscores."""
    result = "".join(_TRANSLIT.get(ch, ch) for ch in name)
    result = re.sub(r"[^A-Za-z0-9._-]", "_", result)
    result = re.sub(r"_+", "_", result).strip("_")
    return result or "document"


def _copy_to_safe_path(file_path: str) -> tuple[str, str]:
    """Copy file to a temp dir under a safe ASCII filename. Returns (new_path, tmp_dir)."""
    original_name = os.path.basename(file_path)
    ext  = original_name.rsplit(".", 1)[-1] if "." in original_name else ""
    stem = original_name.rsplit(".", 1)[0]  if "." in original_name else original_name

    safe_name = f"{_safe_filename(stem)}.{ext}" if ext else _safe_filename(stem)
    tmp_dir   = tempfile.mkdtemp(prefix="enigma_ocr_")
    safe_path = os.path.join(tmp_dir, safe_name)
    shutil.copy2(file_path, safe_path)
    return safe_path, tmp_dir


def convert_with_docling(file_path: str) -> tuple[str, str | None]:
    """Convert a scanned file to Markdown using Docling OCR.

    Args:
        file_path: Absolute path to the file on disk.

    Returns:
        (markdown_text, None) on success.
        ("", error_message) on failure.
    """
    try:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.datamodel.base_models import InputFormat
        from docling.exceptions import ConversionError
    except ImportError:
        return "", (
            "Библиотека Docling не установлена. "
            "Запустите: pip install docling"
        )

    tmp_dir = None
    try:
        safe_path, tmp_dir = _copy_to_safe_path(file_path)

        pipeline_options = PdfPipelineOptions(do_ocr=True, do_table_structure=True)
        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )

        result  = converter.convert(safe_path)
        md_text = result.document.export_to_markdown()

        if not md_text or not md_text.strip():
            return "", "Текст не обнаружен. Проверьте качество скана или читаемость PDF."

        return md_text, None

    except ConversionError:
        return "", _CONVERSION_ERROR_HINT

    except Exception as e:
        return "", f"Неожиданная ошибка: {e}"

    finally:
        if tmp_dir and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)
