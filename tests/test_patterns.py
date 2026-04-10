"""
Unit-тесты для новых regex-паттернов (паспорт, СНИЛС, ИНН, КПП).
Запуск: pytest tests/test_patterns.py -v
"""

import pytest
from core.patterns import find_passports, find_snils, find_inn, find_kpp


class TestPassport:
    def test_basic_format(self):
        results = list(find_passports("Паспорт: 4510 123456"))
        assert len(results) == 1
        assert results[0]["label"] == "ПАСПОРТ"
        assert "4510" in results[0]["text"]
        assert "123456" in results[0]["text"]

    def test_format_with_spaces_in_series(self):
        results = list(find_passports("серия 45 10 № 123456"))
        assert len(results) == 1

    def test_format_with_prefix_no(self):
        results = list(find_passports("серия 4510 № 123456"))
        assert len(results) == 1

    def test_multiple_passports(self):
        text = "Иванов: 4510 123456, Петров: 4612 654321"
        results = list(find_passports(text))
        assert len(results) == 2

    def test_no_false_positive_short_number(self):
        results = list(find_passports("счёт 123456"))
        assert len(results) == 0

    def test_no_false_positive_phone(self):
        results = list(find_passports("+7 (999) 123-45-67"))
        assert len(results) == 0


class TestSnils:
    def test_canonical_format(self):
        results = list(find_snils("СНИЛС: 123-456-789 01"))
        assert len(results) == 1
        assert results[0]["label"] == "СНИЛС"

    def test_digits_only(self):
        results = list(find_snils("12345678901"))
        assert len(results) == 1

    def test_no_false_positive_phone(self):
        results = list(find_snils("+79991234567"))
        assert len(results) == 0

    def test_no_false_positive_inn_12(self):
        results = list(find_snils("123456789012"))
        assert len(results) == 0

    def test_empty_text(self):
        assert list(find_snils("")) == []


class TestInn:
    def test_inn_10_digits_legal_entity(self):
        results = list(find_inn("ИНН 7707083893"))
        assert len(results) == 1
        assert results[0]["label"] == "ИНН"

    def test_inn_12_digits_individual(self):
        results = list(find_inn("ИНН: 772053816842"))
        assert len(results) == 1
        inn_digits = "".join(c for c in results[0]["text"] if c.isdigit())
        assert len(inn_digits) == 12

    def test_inn_without_prefix(self):
        results = list(find_inn("7707083893"))
        assert len(results) == 1

    def test_no_false_positive_9_digits(self):
        results = list(find_inn("123456789"))
        assert len(results) == 0

    def test_no_false_positive_8_digits(self):
        results = list(find_inn("12345678"))
        assert len(results) == 0


class TestKpp:
    def test_with_prefix(self):
        results = list(find_kpp("КПП 770701001"))
        assert len(results) == 1
        assert results[0]["label"] == "КПП"

    def test_without_prefix_not_detected(self):
        results = list(find_kpp("770701001"))
        assert len(results) == 0

    def test_with_colon(self):
        results = list(find_kpp("КПП: 770701001"))
        assert len(results) == 1

    def test_full_company_block(self):
        text = "ООО «Ромашка», ИНН 7707083893, КПП 770701001"
        results = list(find_kpp(text))
        assert len(results) == 1


class TestCombined:
    def test_full_document(self):
        from core.patterns import find_all_russian_personal_data
        text = (
            "Иванов Иван, паспорт 4510 123456, "
            "СНИЛС 123-456-789 01, ИНН 772053816842, "
            "ООО «Тест», ИНН 7707083893, КПП 770701001."
        )
        results = find_all_russian_personal_data(text)
        labels = [r["label"] for r in results]
        assert "ПАСПОРТ" in labels
        assert "СНИЛС" in labels
        assert "ИНН" in labels
        assert "КПП" in labels
        positions = [r["start"] for r in results]
        assert positions == sorted(positions)
