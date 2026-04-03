"""
Unit-тесты для постфильтра Natasha.
Запуск: pytest tests/test_postfilter.py -v
"""

import pytest
from core.detector_patch import natasha_postfilter


def make_ent(text, label="PER"):
    return {"text": text, "label": label, "start": 0, "end": len(text)}


class TestNatashaPostfilter:
    def test_rejects_common_words(self):
        ents = [make_ent("приоритетным продуктовым направлениям")]
        result = natasha_postfilter(ents)
        assert len(result) == 0

    def test_accepts_real_name(self):
        ents = [make_ent("Иван Петров")]
        result = natasha_postfilter(ents)
        assert len(result) == 1

    def test_non_per_label_passes_through(self):
        ents = [make_ent("ООО Ромашка", label="ORG")]
        result = natasha_postfilter(ents)
        assert len(result) == 1

    def test_mixed_list(self):
        ents = [
            make_ent("Иван Петров"),
            make_ent("общий договор"),
            make_ent("ООО Тест", label="ORG"),
        ]
        result = natasha_postfilter(ents)
        assert len(result) == 2
        labels = [e["label"] for e in result]
        assert "ORG" in labels
        assert "PER" in labels

    def test_empty_input(self):
        assert natasha_postfilter([]) == []
