"""Конвертация поддерживаемых форматов в Markdown через Docling.

Поддерживаемые форматы:
    .md / .txt  — возвращаются без изменений
    .pdf        — docling + pypdfium2 backend (текстовый PDF и сканы через OCR)
    .docx       — docling
    .doc        — docling
    .pptx       — docling
    .odt        — docling

Почему pypdfium2 backend:
    Стандартный бэкенд docling_parse написан на C++ и не может работать
    с путями, содержащими кириллицу или пробелы (например, папка «Энигма»
    на Windows). pypdfium2 этой проблемы не имеет.

Возвращаемые значения:
    (text: str, warning: str | None)
    warning != None означает, что конвертация прошла с оговорками.
    При ошибке бросается RuntimeError с человекочитаемым сообщением.
"""
from __future__ import annotations

import os
import tempfile

# Форматы, требующие конвертации
CONVERTIBLE_TYPES = ["pdf", "docx", "doc", "pptx", "odt"]
# Форматы, принимаемые напрямую (без конвертации)
PASSTHROUGH_TYPES = ["md", "txt"]
# Все допустимые расширения для file_uploader
ACCEPTED_TYPES = PASSTHROUGH_TYPES + CONVERTIBLE_TYPES


def file_to_markdown(
    file_bytes: bytes,
    file_name: str,
    ocr_lang: str = "rus+eng",
    force_ocr: bool = False,
) -> tuple[str, str | None]:
    """Конвертировать байты загруженного файла в Markdown-текст.

    Args:
        file_bytes: содержимое файла.
        file_name:  оригинальное имя (используется для определения расширения).
        ocr_lang:   не используется (оставлен для совместимости API).
        force_ocr:  не используется (оставлен для совместимости API).
                    Docling автоматически применяет OCR для сканов.

    Returns:
        (text, warning) — warning = None если всё хорошо.

    Raises:
        RuntimeError: неустранимая ошибка конвертации.
    """
    ext = _get_ext(file_name)

    # --- Passthrough: MD и TXT ---
    if ext in PASSTHROUGH_TYPES:
        text = file_bytes.decode("utf-8", errors="replace")
        return text, None

    if ext not in CONVERTIBLE_TYPES:
        raise RuntimeError(
            f"Неподдерживаемый формат файла: .{ext}. "
            f"Допустимые форматы: {', '.join(ACCEPTED_TYPES)}"
        )

    # --- Требует временного файла с безопасным ASCII-именем ---
    tmp_path = _save_temp(file_bytes, ext)
    try:
        text = _docling_to_md(tmp_path)
        if not text.strip():
            raise RuntimeError(
                "Docling не смог извлечь текст из файла. "
                "Проверьте, что файл не повреждён и не защищён паролем."
            )
        return text, None
    finally:
        _remove_temp(tmp_path)


# ---------------------------------------------------------------------------
# Внутренние функции
# ---------------------------------------------------------------------------

def _get_ext(file_name: str) -> str:
    return file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""


def _save_temp(data: bytes, ext: str) -> str:
    """Сохранить байты во временный файл с безопасным ASCII-именем.

    Кириллица и пробелы в имени файла ломают C++-бэкенд docling_parse
    на Windows. Поэтому используем нейтральное имя upload.<ext>.
    """
    upload_dir = os.path.join(tempfile.gettempdir(), "enigma_uploads")
    os.makedirs(upload_dir, exist_ok=True)
    path = os.path.join(upload_dir, f"upload.{ext}")
    with open(path, "wb") as f:
        f.write(data)
    return path


def _remove_temp(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _docling_to_md(path: str) -> str:
    """Конвертировать файл в Markdown через Docling c pypdfium2 backend.

    pypdfium2 используется вместо стандартного docling_parse, потому что
    последний падает с RuntimeError при кириллице в пути к venv на Windows.

    Args:
        path: абсолютный путь к временному файлу.

    Returns:
        Markdown-текст документа.

    Raises:
        RuntimeError: если зависимости не установлены или произошла ошибка.
    """
    try:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend

        pipeline_options = PdfPipelineOptions(do_ocr=True)

        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pipeline_options,
                    backend=PyPdfiumDocumentBackend,
                )
            }
        )
        result = converter.convert(path)
        return result.document.export_to_markdown() or ""
    except ImportError as exc:
        raise RuntimeError(
            f"Не установлена зависимость для конвертации: {exc}. "
            "Выполните: pip install docling pypdfium2"
        ) from exc
    except Exception as exc:
        raise RuntimeError(f"Ошибка конвертации через Docling: {exc}") from exc
