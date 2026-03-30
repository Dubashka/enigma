"""OCR conversion via Docling for scanned PDFs and images.

Docling (IBM) performs layout-aware OCR locally — no external API calls.
Supports: PDF (scanned), PNG, JPG, JPEG, TIFF, BMP, WEBP.

Design decisions:
- Lazy import of docling to avoid startup penalty when OCR is not used
- Returns (markdown_text, error_message) tuple — no Streamlit dependency
- EasyOCR pipeline is selected by default for better Russian-language support
"""
from __future__ import annotations

SUPPORTED_OCR_TYPES = ["pdf", "png", "jpg", "jpeg", "tiff", "bmp", "webp"]


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
    except ImportError:
        return "", (
            "Библиотека Docling не установлена. "
            "Запустите: pip install docling"
        )

    try:
        pipeline_options = PdfPipelineOptions(do_ocr=True, do_table_structure=True)

        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )

        result = converter.convert(file_path)
        md_text = result.document.export_to_markdown()

        if not md_text or not md_text.strip():
            return "", "Docling не смог извлечь текст из файла. Проверьте качество скана."

        return md_text, None

    except Exception as e:
        return "", f"Ошибка Docling при конвертации: {e}"
