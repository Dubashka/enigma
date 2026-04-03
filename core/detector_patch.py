"""
Постфильтр для Natasha PER-кандидатов и инструкция интеграции AINer.

Скопируйте natasha_postfilter и связанные импорты в существующий detector.py.
См. раздел «Интеграция AINer» в конце файла.

ВАЖНО: не заменяет существующую логику — дополняет её.
"""

from __future__ import annotations
import logging
from typing import Sequence

try:
    import pymorphy2  # type: ignore
    _morph = pymorphy2.MorphAnalyzer()
    _PYMORPHY_AVAILABLE = True
except ImportError:
    _morph = None
    _PYMORPHY_AVAILABLE = False

from core.stopwords import COMMON_WORDS, GEO_STOPWORDS

logger = logging.getLogger(__name__)

# Части речи pymorphy2, характерные для нарицательных слов
_COMMON_POS = {"NOUN", "ADJF", "ADJS", "PRTF", "PRTS"}
# Граммемы имён собственных
_PROPER_ANIMACY = {"Name", "Patr", "Surn"}


def _is_common_word(token: str) -> bool:
    """True если токен — нарицательное слово по словарю или pymorphy2."""
    t = token.lower().strip()
    if t in COMMON_WORDS or t in GEO_STOPWORDS:
        return True

    if _PYMORPHY_AVAILABLE and _morph is not None:
        parses = _morph.parse(t)
        for p in parses:
            pos = p.tag.POS
            if pos in _COMMON_POS:
                grammemes = p.tag.grammemes
                if not any(g in grammemes for g in _PROPER_ANIMACY):
                    return True
    return False


def natasha_postfilter(
    candidates: list[dict],
    label_key: str = "label",
    text_key:  str = "text",
) -> list[dict]:
    """
    Постфильтр для кандидатов типа PER из Natasha.

    Отклоняет кандидата если ВСЕ токены — нарицательные слова.
    Остальные кандидаты пропускаются без изменений.

    Параметры
    ----------
    candidates : список словарей сущностей (из Natasha)
    label_key  : ключ метки ('label' или 'type' — зависит от вашей структуры)
    text_key   : ключ текста сущности

    Возвращает отфильтрованный список.
    """
    filtered = []
    for ent in candidates:
        label = ent.get(label_key, "")
        if label not in ("PER", "person", "ФИО"):
            filtered.append(ent)
            continue

        entity_text = ent.get(text_key, "")
        tokens = entity_text.split()

        if not tokens:
            filtered.append(ent)
            continue

        if all(_is_common_word(tok) for tok in tokens):
            logger.info(
                "Postfilter: отклонён PER '%s' — все токены нарицательные",
                entity_text,
            )
        else:
            filtered.append(ent)

    return filtered


# ---------------------------------------------------------------------------
# Интеграция AINer в detector.py
# ---------------------------------------------------------------------------
# Добавьте в DetectorClass.__init__:
#
#   from core.ai_ner import AINer
#   self._ai_ner = AINer()  # читает ENIGMA_AI_NER_MODE из окружения
#
# В методе detect/analyze после сбора base_entities:
#
#   from core.ai_ner import merge_entity_lists
#   from core.detector_patch import natasha_postfilter
#   from core.patterns import find_all_russian_personal_data
#
#   base_entities = natasha_postfilter(base_entities)
#   base_entities += find_all_russian_personal_data(text)
#   ai_entities = self._ai_ner.extract(text)
#   base_entities = merge_entity_lists(base_entities, ai_entities)
#
# Обратная совместимость обеспечена — при mode="off" ai_entities = [].
