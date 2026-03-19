import io
import pandas as pd


def parse_upload(uploaded_file) -> dict[str, pd.DataFrame]:
    """Parse uploaded file bytes into dict[sheet_name, DataFrame].

    Supports .xlsx (multi-sheet) and .csv (single sheet, auto-encoding).
    Raises ValueError with Russian message on any error.
    """
    file_bytes = uploaded_file.read()
    name = uploaded_file.name.lower()

    if name.endswith(".xlsx"):
        return _parse_excel(file_bytes)
    elif name.endswith(".csv"):
        return _parse_csv(file_bytes)
    else:
        raise ValueError("Поддерживаются только файлы xlsx и csv")


def _parse_excel(file_bytes: bytes) -> dict[str, pd.DataFrame]:
    try:
        sheets = pd.read_excel(
            io.BytesIO(file_bytes),
            sheet_name=None,
            engine="openpyxl",
        )
    except Exception:
        raise ValueError("Не удалось прочитать файл")
    result = {name: df for name, df in sheets.items() if not df.empty}
    if not result:
        raise ValueError("Файл не содержит данных")
    return result


def _parse_csv(file_bytes: bytes) -> dict[str, pd.DataFrame]:
    for encoding in ("utf-8", "cp1251", "utf-8-sig"):
        try:
            df = pd.read_csv(
                io.BytesIO(file_bytes),
                encoding=encoding,
                sep=None,
                engine="python",
            )
            if df.empty:
                raise ValueError("Файл не содержит данных")
            return {"Лист1": df}
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
        except ValueError:
            raise
    raise ValueError("Не удалось прочитать файл")
