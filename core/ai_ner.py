"""
AI-модуль NER для проекта Enigma.

Поддерживает два бэкенда:
  - gliner  : локальная модель GLiNER (urchade/gliner_multi-v2.1)
  - ollama  : локальный REST API Ollama (qwen2.5:7b / mistral:7b)
  - off     : только Natasha + Presidio + regex (без AI)

Режим задаётся через переменную окружения ENIGMA_AI_NER_MODE
или аргументом конструктора.

Результат extract() — список словарей:
  {
    "text"      : str,
    "label"     : str,
    "start"     : int,
    "end"       : int,
    "confidence": float,     # 0.0–1.0
    "source"    : "gliner" | "ollama",
  }

merge_entity_lists() принимает:
  base — список кортежей (start, end, label, value)   ← формат detect_entities()
  ai   — список словарей (формат extract() выше)
и возвращает объединённый список кортежей.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

_DEFAULT_MODE = os.environ.get("ENIGMA_AI_NER_MODE", "off").lower()
_GLINER_MODEL = os.environ.get("ENIGMA_GLINER_MODEL", "urchade/gliner_multi-v2.1")
_OLLAMA_URL   = os.environ.get("ENIGMA_OLLAMA_URL",   "http://localhost:11434")
_OLLAMA_MODEL = os.environ.get("ENIGMA_OLLAMA_MODEL", "qwen2.5:7b")
_KEEP_ALIVE   = "15m"  # держать модель в памяти между запросами
_TIMEOUT      = 180    # секунд — даём время на холодный старт модели

GLINER_LABELS = [
    "person", "organization", "address", "phone", "email",
    "date", "passport", "inn", "snils", "contract number",
]

# Пороги GLiNER
_GLINER_PERSON_THRESHOLD = 0.4
_GLINER_LOW_CONFIDENCE   = 0.5

# ---------------------------------------------------------------------------
# Кэш (хэш текста → список сущностей)
# ---------------------------------------------------------------------------

_cache: dict[str, list[dict]] = {}


def _cache_key(text: str, mode: str) -> str:
    return hashlib.sha256(f"{mode}:{text}".encode()).hexdigest()


# ---------------------------------------------------------------------------
# GLiNER-бэкенд
# ---------------------------------------------------------------------------

def _load_gliner():
    """Ленивая загрузка GLiNER — только при первом использовании."""
    try:
        from gliner import GLiNER  # type: ignore
        model = GLiNER.from_pretrained(_GLINER_MODEL)
        logger.info("GLiNER model '%s' loaded.", _GLINER_MODEL)
        return model
    except ImportError:
        logger.error("gliner не установлен. pip install gliner")
        raise
    except Exception as exc:
        logger.error("Не удалось загрузить GLiNER: %s", exc)
        raise


_gliner_model_cache: Any = None  # синглтон модели


def _run_gliner(text: str) -> list[dict]:
    global _gliner_model_cache
    if _gliner_model_cache is None:
        _gliner_model_cache = _load_gliner()

    raw = _gliner_model_cache.predict_entities(text, GLINER_LABELS)
    results: list[dict] = []

    for ent in raw:
        label       = ent.get("label", "")
        score       = float(ent.get("score", 0.0))
        start       = ent.get("start", 0)
        end         = ent.get("end", 0)
        entity_text = text[start:end]

        if label == "person" and score < _GLINER_PERSON_THRESHOLD:
            logger.debug(
                "GLiNER: отклонён PER-кандидат '%s' (score=%.2f < %.2f)",
                entity_text, score, _GLINER_PERSON_THRESHOLD,
            )
            continue

        if score < _GLINER_LOW_CONFIDENCE:
            logger.info(
                "GLiNER: низкая уверенность %.2f для '%s' [%s]",
                score, entity_text, label,
            )

        results.append({
            "text":       entity_text,
            "label":      label,
            "start":      start,
            "end":        end,
            "confidence": score,
            "source":     "gliner",
        })

    return results


# ---------------------------------------------------------------------------
# Ollama-бэкенд
# ---------------------------------------------------------------------------

_OLLAMA_SYSTEM_PROMPT = """Ты — система извлечения именованных сущностей из текста.
Найди все конфиденциальные данные в тексте и верни ТОЛЬКО JSON-массив объектов.
Каждый объект должен иметь поля:
  "text"       — точная подстрока из исходного текста
  "label"      — одна из меток: ФИО, ОРГ, АДРЕС, ТЕЛЕФОН, EMAIL, ДАТА,
                 ПАСПОРТ, ИНН, СНИЛС, ДОГОВОР
  "start"      — позиция начала (0-based, символы)
  "end"        — позиция конца (не включая)
  "confidence" — "high", "medium" или "low"

Если ничего не найдено — верни пустой массив [].
Не добавляй никаких пояснений — только JSON."""


class OllamaUnavailableError(RuntimeError):
    """Пробрасывается в UI, если Ollama недоступна."""


class OllamaParseError(RuntimeError):
    """Пробрасывается в UI, если ответ не удалось разобрать."""


def _run_ollama(text: str) -> list[dict]:
    """Вызов Ollama REST API.

    Raises:
        OllamaUnavailableError — если сервер недоступен или таймаут
        OllamaParseError       — если ответ не является валидным JSON
    """
    payload = {
        "model": _OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": _OLLAMA_SYSTEM_PROMPT},
            {"role": "user",   "content": text},
        ],
        "stream": False,
        "format": "json",
        "keep_alive": _KEEP_ALIVE,
    }
    try:
        resp = requests.post(
            f"{_OLLAMA_URL}/api/chat",
            json=payload,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.exceptions.ConnectionError:
        raise OllamaUnavailableError(
            f"Ollama недоступна по адресу {_OLLAMA_URL}.\n"
            "Запустите: ollama serve"
        )
    except requests.exceptions.Timeout:
        raise OllamaUnavailableError(
            f"Ollama не ответила за {_TIMEOUT} секунд (модель {_OLLAMA_MODEL} может ещё загружаться).\n"
            "Подождите и попробуйте снова."
        )
    except requests.exceptions.HTTPError as exc:
        raise OllamaUnavailableError(f"Ollama вернула HTTP-ошибку: {exc}")

    try:
        content = resp.json()["message"]["content"]
        # Модель может обернуть JSON в markdown-блок
        json_str = re.sub(r"```(?:json)?|```", "", content).strip()
        raw_list = json.loads(json_str)
    except (KeyError, json.JSONDecodeError) as exc:
        raise OllamaParseError(f"Не удалось разобрать ответ Ollama: {exc}\n\nОтвет:\n{content!r}")

    results: list[dict] = []
    for item in raw_list:
        try:
            conf_map = {"high": 0.9, "medium": 0.6, "low": 0.3}
            confidence = conf_map.get(str(item.get("confidence", "low")), 0.3)
            start = int(item["start"])
            end   = int(item["end"])
            results.append({
                "text":       item.get("text") or text[start:end],
                "label":      item.get("label", ""),
                "start":      start,
                "end":        end,
                "confidence": confidence,
                "source":     "ollama",
            })
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Ollama: пропущена сущность из-за ошибки: %s", exc)

    return results


# ---------------------------------------------------------------------------
# Объединение + дедупликация по перекрытию span
# ---------------------------------------------------------------------------

def _spans_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return not (a_end <= b_start or b_end <= a_start)


def merge_entity_lists(
    base: list[tuple],
    ai: list[dict],
    log_conflicts: bool = True,
) -> list[tuple]:
    """
    Объединение двух списков сущностей с дедупликацией по позиции.

    base — кортежи (start, end, label, value) из detect_entities()
    ai   — словари {start, end, label, text, ...} из AINer.extract()

    Возвращает список кортежей (start, end, label, value) —
    тот же формат, что и detect_entities(), чтобы anonymize() его принял.

    При конфликте меток (одна позиция, разные метки) — логируем, оставляем оба варианта.
    """
    merged = list(base)  # кортежи (start, end, label, value)

    for ai_ent in ai:
        ai_start = ai_ent["start"]
        ai_end   = ai_ent["end"]
        ai_label = ai_ent.get("label", "")
        ai_text  = ai_ent.get("text", "")

        overlaps = [
            b for b in merged
            if _spans_overlap(ai_start, ai_end, b[0], b[1])
        ]

        if not overlaps:
            # Новая сущность — добавляем как кортеж
            merged.append((ai_start, ai_end, ai_label, ai_text))
        else:
            if log_conflicts:
                for b in overlaps:
                    if b[2] != ai_label:
                        logger.info(
                            "NER-конфликт: '%s' → base=%s, ai=%s",
                            ai_text, b[2], ai_label,
                        )

    return merged


# ---------------------------------------------------------------------------
# Публичный класс
# ---------------------------------------------------------------------------

class AINer:
    """
    Оболочка для AI-этапа NER.

    Использование::

        ai_ner = AINer(mode="ollama")
        entities = ai_ner.extract(text)  # список dict
        # или сразу мёрджим с базовым списком кортежей:
        merged = merge_entity_lists(base_entities, entities)
    """

    def __init__(self, mode: str | None = None, use_cache: bool = True):
        self.mode      = (mode or _DEFAULT_MODE).lower()
        self.use_cache = use_cache

        if self.mode not in {"gliner", "ollama", "off"}:
            logger.warning(
                "Неизвестный режим AI NER: '%s'. Используется 'off'.", self.mode
            )
            self.mode = "off"

    def extract(self, text: str) -> list[dict]:
        """
        Извлечь сущности из текста.

        Возвращает список словарей text/label/start/end/confidence/source.
        Исключения OllamaUnavailableError / OllamaParseError / Exception
        пробрасываются наверх — обрабатывает вызывающий код (UI).
        """
        if self.mode == "off" or not text.strip():
            return []

        if self.use_cache:
            key = _cache_key(text, self.mode)
            if key in _cache:
                logger.debug("AINer: cache hit (mode=%s)", self.mode)
                return _cache[key]

        if self.mode == "gliner":
            result = _run_gliner(text)
        elif self.mode == "ollama":
            result = _run_ollama(text)   # может бросить OllamaUnavailableError
        else:
            result = []

        if self.use_cache:
            key = _cache_key(text, self.mode)
            _cache[key] = result

        return result

    def is_enabled(self) -> bool:
        return self.mode != "off"
