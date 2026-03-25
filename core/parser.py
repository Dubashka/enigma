import io
import os
import tempfile
import pandas as pd


# Directory for temporary uploaded files
UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "enigma_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def save_upload(uploaded_file) -> str:
    """Save uploaded file to disk and return the path."""
    path = os.path.join(UPLOAD_DIR, uploaded_file.name)
    with open(path, "wb") as f:
        f.write(uploaded_file.read())
    return path


def cleanup_upload(path: str) -> None:
    """Remove uploaded file from disk."""
    try:
        os.remove(path)
    except OSError:
        pass


def parse_preview(path: str, nrows: int = 20) -> dict[str, pd.DataFrame]:
    """Parse only first N rows for preview — fast, low memory."""
    name = path.lower()
    if name.endswith(".xlsx"):
        return _parse_excel_preview(path, nrows)
    elif name.endswith(".csv"):
        return _parse_csv_preview(path, nrows)
    else:
        raise ValueError("Поддерживаются только файлы xlsx и csv")


def parse_full(path: str) -> dict[str, pd.DataFrame]:
    """Parse entire file for masking."""
    name = path.lower()
    if name.endswith(".xlsx"):
        return _parse_excel_full(path)
    elif name.endswith(".csv"):
        return _parse_csv_full(path)
    else:
        raise ValueError("Поддерживаются только файлы xlsx и csv")


# Keep backward compat for decryption page
def parse_upload(uploaded_file) -> dict[str, pd.DataFrame]:
    """Parse uploaded file bytes into dict[sheet_name, DataFrame]."""
    file_bytes = uploaded_file.read()
    name = uploaded_file.name.lower()
    if name.endswith(".xlsx"):
        return _parse_excel_bytes(file_bytes)
    elif name.endswith(".csv"):
        return _parse_csv_bytes(file_bytes)
    else:
        raise ValueError("Поддерживаются только файлы xlsx и csv")


# --- Excel ---

def _get_excel_engine() -> str:
    """Return best available Excel engine: calamine (fast, Rust) or openpyxl (fallback)."""
    try:
        import python_calamine  # noqa: F401
        return "calamine"
    except ImportError:
        return "openpyxl"


def _parse_excel_preview(path: str, nrows: int) -> dict[str, pd.DataFrame]:
    engine = _get_excel_engine()
    try:
        sheets = pd.read_excel(path, sheet_name=None, engine=engine, nrows=nrows)
    except Exception:
        raise ValueError("Не удалось прочитать файл")
    result = {name: df for name, df in sheets.items() if not df.empty}
    if not result:
        raise ValueError("Файл не содержит данных")
    return result


def _parse_excel_full(path: str) -> dict[str, pd.DataFrame]:
    engine = _get_excel_engine()
    try:
        sheets = pd.read_excel(path, sheet_name=None, engine=engine)
    except Exception:
        raise ValueError("Не удалось прочитать файл")
    result = {name: df for name, df in sheets.items() if not df.empty}
    if not result:
        raise ValueError("Файл не содержит данных")
    return result


def _parse_excel_bytes(file_bytes: bytes) -> dict[str, pd.DataFrame]:
    engine = _get_excel_engine()
    try:
        sheets = pd.read_excel(
            io.BytesIO(file_bytes), sheet_name=None, engine=engine,
        )
    except Exception:
        raise ValueError("Не удалось прочитать файл")
    result = {name: df for name, df in sheets.items() if not df.empty}
    if not result:
        raise ValueError("Файл не содержит данных")
    return result


# --- CSV ---

def _try_read_csv(source, encoding: str, nrows: int | None = None) -> pd.DataFrame:
    """Try reading CSV with fast C engine first, fall back to Python engine for sep detection."""
    kwargs = {"encoding": encoding}
    if nrows is not None:
        kwargs["nrows"] = nrows
    try:
        # Fast path: C engine with common separators
        for sep in (",", ";", "\t"):
            try:
                df = pd.read_csv(source, sep=sep, engine="c", **kwargs)
                if len(df.columns) > 1:
                    return df
                # Reset source position for BytesIO
                if hasattr(source, "seek"):
                    source.seek(0)
            except Exception:
                if hasattr(source, "seek"):
                    source.seek(0)
                continue
        # Fallback: Python engine with auto-detect separator
        if hasattr(source, "seek"):
            source.seek(0)
        return pd.read_csv(source, sep=None, engine="python", **kwargs)
    except Exception:
        raise


def _parse_csv_preview(path: str, nrows: int) -> dict[str, pd.DataFrame]:
    for encoding in ("utf-8", "cp1251", "utf-8-sig"):
        try:
            df = _try_read_csv(path, encoding, nrows=nrows)
            if df.empty:
                raise ValueError("Файл не содержит данных")
            return {"Лист1": df}
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
        except ValueError:
            raise
    raise ValueError("Не удалось прочитать файл")


def _parse_csv_full(path: str) -> dict[str, pd.DataFrame]:
    for encoding in ("utf-8", "cp1251", "utf-8-sig"):
        try:
            df = _try_read_csv(path, encoding)
            if df.empty:
                raise ValueError("Файл не содержит данных")
            return {"Лист1": df}
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
        except ValueError:
            raise
    raise ValueError("Не удалось прочитать файл")


def _parse_csv_bytes(file_bytes: bytes) -> dict[str, pd.DataFrame]:
    for encoding in ("utf-8", "cp1251", "utf-8-sig"):
        try:
            df = _try_read_csv(io.BytesIO(file_bytes), encoding)
            if df.empty:
                raise ValueError("Файл не содержит данных")
            return {"Лист1": df}
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
        except ValueError:
            raise
    raise ValueError("Не удалось прочитать файл")
