"""
Постфильтр для PER-кандидатов Natasha.

natasha_postfilter() работает с потоком кортежей:
    (start: int, end: int, label: str, value: str)

Это нативный формат detect_entities() / _regex_entities() / _natasha_entities().
Не требует адаптера — подключается напрямую в md_anonymizer.detect_entities().
"""

from __future__ import annotations
import logging

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
        for p in _morph.parse(t):
            pos = p.tag.POS
            if pos in _COMMON_POS:
                grammemes = p.tag.grammemes
                # Если pymorphy2 не пометил слово граммемой имени собственного
                if not any(g in grammemes for g in _PROPER_ANIMACY):
                    return True
    return False


# Метки, которые фильтруем
_PERSON_LABELS = {"ФИО", "PER", "person"}


def natasha_postfilter(
    candidates: list[tuple],
) -> list[tuple]:
    """
    Постфильтр для потока кортежей (start, end, label, value).

    Отклоняет PER/ФИО-кандидата, если:
      - ВСЕ токены присутствуют в COMMON_WORDS или GEO_STOPWORDS, ИЛИ
      - pymorphy2 определяет все токены как нарицательные
        (без граммем Name/Patr/Surn).

    Все остальные метки (ORG, EMAIL и т.д.) пропускаются без изменений.
    """
    filtered = []
    for ent in candidates:
        # Кортеж имеет формат (start, end, label, value)
        label = ent[2]
        if label not in _PERSON_LABELS:
            filtered.append(ent)
            continue

        value = ent[3]
        tokens = value.split()

        if not tokens:
            filtered.append(ent)
            continue

        if all(_is_common_word(tok) for tok in tokens):
            logger.info(
                "Postfilter: отклонён PER '%s' — все токены нарицательные",
                value,
            )
        else:
            filtered.append(ent)

    return filtered
