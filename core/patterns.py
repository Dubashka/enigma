"""
Дополнительные regex-паттерны для российских персональных данных.
Интегрируется в detector.py.

Паттерны возвращают именованные группы для удобства извлечения.
"""

import re
from typing import Iterator

# ---------------------------------------------------------------------------
# Скомпилированные паттерны
# ---------------------------------------------------------------------------

# Паспорт РФ:
#   «4510 123456», «45 10 123456», «серия 4510 № 123456»
#   «45 10 № 123456», «серия 45 10 номер 123456»
_PASSPORT_RE = re.compile(
    r"(?:"
    r"(?:серия\s+)?"       # необязательный префикс «серия»
    r"(?P<series>\d{4}|\d{2}\s\d{2})"  # серия: «4510» или «45 10»
    r"\s*"
    r"(?:№|N|номер|no\.?)?\s*"  # необязательный разделитель
    r"(?P<number>\d{6})"   # номер: 6 цифр
    r")",
    re.IGNORECASE,
)

# СНИЛС: «123-456-789 01» или «12345678901» (11 цифр)
_SNILS_RE = re.compile(
    r"(?:"
    r"\d{3}-\d{3}-\d{3}\s\d{2}"  # формат с дефисами и пробелом
    r"|"
    r"(?<!\d)\d{11}(?!\d)"       # 11 цифр без дефисов (не часть большего числа)
    r")"
)

# ИНН физлица: 12 цифр, ИНН юрлица: 10 цифр
# С опциональным словом «ИНН» перед числом
_INN_RE = re.compile(
    r"(?:ИНН\s*[:\-]?\s*)?"  # необязательный префикс
    r"(?P<inn>"
    r"(?<!\d)\d{12}(?!\d)"   # физлицо — 12 цифр
    r"|"
    r"(?<!\d)\d{10}(?!\d)"   # юрлицо  — 10 цифр
    r")",
    re.IGNORECASE,
)

# КПП: 9 цифр, обычно рядом с ИНН
_KPP_RE = re.compile(
    r"(?:КПП\s*[:\-]?\s*)"
    r"(?P<kpp>(?<!\d)\d{9}(?!\d))",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Функции-итераторы
# ---------------------------------------------------------------------------

def find_passports(text: str) -> Iterator[dict]:
    """Возвращает совпадения паспортных данных."""
    for m in _PASSPORT_RE.finditer(text):
        yield {
            "text":  m.group(0).strip(),
            "label": "ПАСПОРТ",
            "start": m.start(),
            "end":   m.end(),
        }


def find_snils(text: str) -> Iterator[dict]:
    """Возвращает совпадения СНИЛС."""
    for m in _SNILS_RE.finditer(text):
        yield {
            "text":  m.group(0).strip(),
            "label": "СНИЛС",
            "start": m.start(),
            "end":   m.end(),
        }


def find_inn(text: str) -> Iterator[dict]:
    """Возвращает совпадения ИНН (10 или 12 цифр)."""
    for m in _INN_RE.finditer(text):
        inn_val = m.group("inn")
        if inn_val and len(inn_val) in (10, 12):
            yield {
                "text":  m.group(0).strip(),
                "label": "ИНН",
                "start": m.start(),
                "end":   m.end(),
            }


def find_kpp(text: str) -> Iterator[dict]:
    """Возвращает совпадения КПП (9 цифр, только с явным префиксом КПП)."""
    for m in _KPP_RE.finditer(text):
        yield {
            "text":  m.group(0).strip(),
            "label": "КПП",
            "start": m.start(),
            "end":   m.end(),
        }


def find_all_russian_personal_data(text: str) -> list[dict]:
    """
    Запустить все паттерны и вернуть единый список сущностей,
    отсортированный по позиции в тексте.
    """
    results: list[dict] = []
    for finder in (find_passports, find_snils, find_inn, find_kpp):
        results.extend(finder(text))
    return sorted(results, key=lambda x: x["start"])
