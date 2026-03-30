"""OCR engine for scanned PDF files.

Pipeline:
    PDF  →  per-page images (pdf2image / poppler)
         →  Tesseract OCR  (pytesseract)
         →  list[{page, text}]

Design decisions:
- dpi=300 is the sweet spot: good quality without excessive memory usage.
- lang defaults to "rus+eng" — covers the most common mixed-language documents.
- Returns structured list so callers can choose output format freely
  (plain text, Markdown, JSON — see core/output.py).
- Raises ImportError with a clear message when optional deps are missing,
  so the UI layer (views/pdf_to_md.py) can show a helpful hint.
"""
from __future__ import annotations


def _check_deps() -> None:
    """Raise ImportError with install hint if optional OCR deps are missing."""
    missing = []
    try:
        import pdf2image  # noqa: F401
    except ImportError:
        missing.append("pdf2image")
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        missing.append("pytesseract")
    if missing:
        raise ImportError(
            f"Для OCR необходимо установить: {', '.join(missing)}. "
            "Выполните: pip install " + " ".join(missing)
        )


def ocr_pdf(
    file_path: str,
    lang: str = "rus+eng",
    dpi: int = 300,
) -> list[dict]:
    """Run Tesseract OCR on every page of a scanned PDF.

    Args:
        file_path: absolute path to the PDF file.
        lang:      Tesseract language string, e.g. "rus", "eng", "rus+eng".
        dpi:       rendering resolution; 300 recommended for most scans.

    Returns:
        List of dicts: [{"page": 1, "text": "..."}, {"page": 2, ...}, ...]

    Raises:
        ImportError: if pdf2image or pytesseract is not installed.
        RuntimeError: if Tesseract binary is not found in PATH.
        Exception:   propagates pdf2image / Tesseract errors as-is.
    """
    _check_deps()

    from pdf2image import convert_from_path
    import pytesseract

    # Verify Tesseract is accessible before starting the (potentially long) conversion
    try:
        pytesseract.get_tesseract_version()
    except pytesseract.TesseractNotFoundError:
        raise RuntimeError(
            "Tesseract не найден. Убедитесь, что он установлен и доступен в PATH. "
            "Linux: sudo apt install tesseract-ocr tesseract-ocr-rus  "
            "macOS: brew install tesseract tesseract-lang"
        )

    images = convert_from_path(file_path, dpi=dpi)

    pages: list[dict] = []
    for i, img in enumerate(images, start=1):
        text = pytesseract.image_to_string(img, lang=lang)
        pages.append({"page": i, "text": text.strip()})

    return pages


def is_scanned_pdf(text_from_markitdown: str) -> bool:
    """Heuristic: PDF is likely a scan if markitdown extracted very little text.

    A threshold of 50 non-whitespace characters is generous enough to avoid
    false positives on cover pages while catching genuinely empty scans.
    """
    return len(text_from_markitdown.strip()) < 50
