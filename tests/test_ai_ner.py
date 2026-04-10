"""
Unit-тесты для core/ai_ner.py.
Использует mock-объекты — не требует реальных моделей.
Запуск: pytest tests/test_ai_ner.py -v
"""

from unittest.mock import MagicMock, patch
import pytest
from core.ai_ner import AINer, merge_entity_lists


SAMPLE_TEXT = "Директор Иван Петров, тел. +7(999)123-45-67, ИНН 770653816842"

FAKE_GLINER_OUTPUT = [
    {"label": "person", "score": 0.92, "start": 9,  "end": 20},
    {"label": "phone",  "score": 0.88, "start": 27, "end": 43},
    {"label": "inn",    "score": 0.75, "start": 50, "end": 62},
]

FAKE_OLLAMA_RESPONSE = [
    {
        "text": "Иван Петров",
        "label": "ФИО",
        "start": 9,
        "end": 20,
        "confidence": "high",
    },
]


class TestOffMode:
    def test_off_mode_returns_empty(self):
        ner = AINer(mode="off")
        assert ner.extract(SAMPLE_TEXT) == []

    def test_off_mode_is_disabled(self):
        ner = AINer(mode="off")
        assert not ner.is_enabled()

    def test_empty_text_returns_empty(self):
        ner = AINer(mode="gliner")
        assert ner.extract("") == []
        assert ner.extract("   ") == []


class TestGlinerMode:
    @patch("core.ai_ner._load_gliner")
    def test_gliner_extracts_entities(self, mock_load):
        mock_model = MagicMock()
        mock_model.predict_entities.return_value = FAKE_GLINER_OUTPUT
        mock_load.return_value = mock_model
        import core.ai_ner as ai_ner_mod
        ai_ner_mod._gliner_model_cache = None
        ner = AINer(mode="gliner", use_cache=False)
        results = ner.extract(SAMPLE_TEXT)
        assert len(results) == 3
        assert all(r["source"] == "gliner" for r in results)

    @patch("core.ai_ner._load_gliner")
    def test_gliner_filters_low_confidence_person(self, mock_load):
        low_conf = [{"label": "person", "score": 0.35, "start": 0, "end": 5}]
        mock_model = MagicMock()
        mock_model.predict_entities.return_value = low_conf
        mock_load.return_value = mock_model
        import core.ai_ner as ai_ner_mod
        ai_ner_mod._gliner_model_cache = None
        ner = AINer(mode="gliner", use_cache=False)
        results = ner.extract("Тест текст")
        assert len(results) == 0

    @patch("core.ai_ner._load_gliner")
    def test_gliner_cache(self, mock_load):
        mock_model = MagicMock()
        mock_model.predict_entities.return_value = FAKE_GLINER_OUTPUT
        mock_load.return_value = mock_model
        import core.ai_ner as ai_ner_mod
        ai_ner_mod._gliner_model_cache = None
        ai_ner_mod._cache.clear()
        ner = AINer(mode="gliner", use_cache=True)
        ner.extract(SAMPLE_TEXT)
        ner.extract(SAMPLE_TEXT)
        assert mock_model.predict_entities.call_count == 1


class TestOllamaMode:
    @patch("core.ai_ner.requests.post")
    def test_ollama_extracts_entities(self, mock_post):
        import json
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "message": {"content": json.dumps(FAKE_OLLAMA_RESPONSE)}
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp
        ner = AINer(mode="ollama", use_cache=False)
        results = ner.extract(SAMPLE_TEXT)
        assert len(results) == 1
        assert results[0]["source"] == "ollama"
        assert results[0]["confidence"] == 0.9

    @patch("core.ai_ner.requests.post", side_effect=__import__("requests").exceptions.ConnectionError)
    def test_ollama_fallback_on_connection_error(self, _):
        ner = AINer(mode="ollama", use_cache=False)
        results = ner.extract(SAMPLE_TEXT)
        assert results == []

    @patch("core.ai_ner.requests.post")
    def test_ollama_handles_broken_json(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "message": {"content": "Извините, я не могу этого сделать."}
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp
        ner = AINer(mode="ollama", use_cache=False)
        results = ner.extract(SAMPLE_TEXT)
        assert results == []


class TestMergeEntityLists:
    def _make_ent(self, text, label, start, end, source="base"):
        return {"text": text, "label": label, "start": start, "end": end, "source": source}

    def test_no_overlap_merges_all(self):
        base = [self._make_ent("Иван", "PER", 0, 4)]
        ai   = [self._make_ent("Петров", "PER", 5, 11, source="gliner")]
        merged = merge_entity_lists(base, ai, log_conflicts=False)
        assert len(merged) == 2

    def test_overlap_same_label_deduplicates(self):
        base = [self._make_ent("Иван Петров", "PER", 0, 11)]
        ai   = [self._make_ent("Иван Петров", "PER", 0, 11, source="gliner")]
        merged = merge_entity_lists(base, ai, log_conflicts=False)
        assert len(merged) == 1

    def test_overlap_different_label_keeps_both(self):
        base = [self._make_ent("7707083893", "ОРГ", 10, 20)]
        ai   = [self._make_ent("7707083893", "ИНН", 10, 20, source="gliner")]
        merged = merge_entity_lists(base, ai, log_conflicts=False)
        assert len(merged) == 2

    def test_empty_ai_returns_base(self):
        base = [self._make_ent("Иван", "PER", 0, 4)]
        merged = merge_entity_lists(base, [], log_conflicts=False)
        assert merged == base
