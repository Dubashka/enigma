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
  exclude_indices — множество индексов base, помеченных Ollama как ложноположительные
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
_TIMEOUT      = 300    # секунд — 5 минут, достаточно для холодного старта модели

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
# Ollama-бэкенды
# ---------------------------------------------------------------------------

# Простой промпт — без базового списка (использовался раньше, оставлен для GLiNER-режима)
_OLLAMA_SYSTEM_PROMPT = """\
Ты — система извлечения именованных сущностей (NER) из текста на русском языке.

Найди все конфиденциальные персональные данные и верни ТОЛЬКО JSON-массив.
Никакого вступления, никаких пояснений — ТОЛЬКО сам массив.

Каждый элемент массива — объект со следующими полями:
  "text"       — точная подстрока из исходного текста (копируй дословно)
  "label"      — одна из меток: ФИО, ОРГ, АДРЕС, ТЕЛЕФОН, EMAIL, ДАТА, ПАСПОРТ, ИНН, СНИЛС, ДОГОВОР
  "start"      — целое число: позиция первого символа в исходном тексте (0-based)
  "end"        — целое число: позиция символа ПОСЛЕ последнего (не включая)
  "confidence" — строка: "high", "medium" или "low"

Пример ответа (структура обязательна):
[
  {"text": "Иванов Иван Иванович", "label": "ФИО", "start": 10, "end": 30, "confidence": "high"},
  {"text": "ООО «Ромашка»", "label": "ОРГ", "start": 45, "end": 58, "confidence": "high"}
]

Если конфиденциальных данных не найдено — верни пустой массив: []
"""

# Расширенный промпт — получает базовый список и возвращает три секции
_OLLAMA_SYSTEM_PROMPT_WITH_BASE = """\
Ты — система проверки и расширения результатов NER (извлечения именованных сущностей) \
из текста на русском языке.

Тебе будет передан:
1. Текст документа
2. Список сущностей, уже найденных базовым сканером (Natasha + Presidio + regex) — \
каждая сущность содержит индекс (idx), значение (value) и метку (label)

Твоя задача — вернуть ТОЛЬКО JSON-объект с тремя полями:

  "confirmed"       — массив idx из базового списка, которые являются НАСТОЯЩИМИ \
персональными данными (оставить)
  "false_positives" — массив idx из базового списка, которые являются ОШИБОЧНЫМИ \
срабатываниями (удалить): OCR-мусор, обрывки слов, должности, \
неперсональные слова
  "new"             — массив НОВЫХ сущностей, которых нет в базовом списке, \
но которые являются персональными данными

Формат каждого элемента в "new":
  "text"       — точная подстрока из исходного текста
  "label"      — одна из меток: ФИО, ОРГ, АДРЕС, ТЕЛЕФОН, EMAIL, ДАТА, ПАСПОРТ, ИНН, СНИЛС, ДОГОВОР
  "start"      — целое число: позиция первого символа (0-based)
  "end"        — целое число: позиция символа ПОСЛЕ последнего
  "confidence" — строка: "high", "medium" или "low"

Правила для false_positives:
- OCR-мусор: короткие бессмысленные строки ("Зо", "БЕсТв", "Ра ;.")
- Обрывки слов из-за переноса строк
- Должности и роли ("Руководителя центра", "Директора", "Блока") — они НЕ персональные данные
- Слова, написанные ТОЛЬКО заглавными буквами, если это не аббревиатура организации \
("РАБОТ", "СТОРОН")
- Названия разделов и заголовков документа

Правила для confirmed:
- ФИО: полные имена, инициалы ("Федосов П.В.", "Скорочкин А.А.")
- ОРГ: реальные названия организаций с правовой формой \
("ПАО «МТС»", "ООО «Рексофт»")
- Телефоны, email, адреса, даты, номера документов

Пример ответа:
{
  "confirmed": [0, 1, 3, 5],
  "false_positives": [2, 4],
  "new": [
    {"text": "г. Москва, ул. Лазо, д. 3А", "label": "АДРЕС", \
"start": 820, "end": 846, "confidence": "high"}
  ]
}

Если нет ложноположительных — "false_positives": []
Если нет новых — "new": []
ТОЛЬКО JSON-объект, никакого другого текста.
"""


class OllamaUnavailableError(RuntimeError):
    """Пробрасывается в UI, если Ollama недоступна."""


class OllamaTimeoutError(OllamaUnavailableError):
    """Пробрасывается отдельно, если Ollama не ответила за _TIMEOUT секунд."""


class OllamaParseError(RuntimeError):
    """Пробрасывается в UI, если ответ не удалось разобрать."""


def _extract_json_array(content: str) -> str:
    """Вырезает JSON-массив из ответа модели."""
    content = re.sub(r"```(?:json)?|```", "", content).strip()
    start = content.find("[")
    end   = content.rfind("]")
    if start == -1 or end == -1 or end < start:
        return "[]"
    return content[start : end + 1]


def _extract_json_object(content: str) -> str:
    """Вырезает JSON-объект из ответа модели."""
    content = re.sub(r"```(?:json)?|```", "", content).strip()
    start = content.find("{")
    end   = content.rfind("}")
    if start == -1 or end == -1 or end < start:
        return "{}"
    return content[start : end + 1]


def _build_base_description(base: list[tuple]) -> str:
    """Сериализует базовый список в читаемый текст для промпта."""
    lines = []
    for idx, (start, end, label, value) in enumerate(base):
        lines.append(f"  idx={idx}  label={label}  value={value!r}  pos={start}-{end}")
    return "\n".join(lines) if lines else "  (пусто)"


def _run_ollama(text: str) -> list[dict]:
    """Простой вызов Ollama без базового списка (используется GLiNER-режимом).

    Raises:
        OllamaTimeoutError     — таймаут
        OllamaUnavailableError — сервер недоступен
        OllamaParseError       — невалидный JSON
    """
    payload = {
        "model": _OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": _OLLAMA_SYSTEM_PROMPT},
            {"role": "user",   "content": text},
        ],
        "stream": False,
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
            "Запустите сервер командой: ollama serve"
        )
    except requests.exceptions.Timeout:
        raise OllamaTimeoutError(
            f"Ollama не ответила за {_TIMEOUT} секунд.\n"
            f"Возможные причины:\n"
            f"• Модель {_OLLAMA_MODEL!r} ещё загружается — попробуйте снова через минуту.\n"
            f"• Документ слишком большой — попробуйте разбить на части.\n"
            f"• Не хватает RAM/VRAM для модели."
        )
    except requests.exceptions.HTTPError as exc:
        raise OllamaUnavailableError(f"Ollama вернула HTTP-ошибку: {exc}")

    try:
        content = resp.json()["message"]["content"]
        json_str = _extract_json_array(content)
        raw_list = json.loads(json_str)
        if not isinstance(raw_list, list):
            raise OllamaParseError(
                f"Ollama вернула не массив, а {type(raw_list).__name__}.\n\nОтвет:\n{content!r}"
            )
    except (KeyError, json.JSONDecodeError) as exc:
        raise OllamaParseError(
            f"Не удалось разобрать ответ Ollama: {exc}\n\nОтвет:\n{content!r}"
        )

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


def _run_ollama_with_base(
    text: str,
    base: list[tuple],
) -> tuple[list[dict], set[int]]:
    """Вызов Ollama с передачей базового списка.

    Модель получает текст + базовый список и возвращает JSON-объект с тремя секциями:
      confirmed       — индексы base, которые являются настоящими ПДн (оставить)
      false_positives — индексы base, которые являются мусором (удалить)
      new             — новые сущности, не вошедшие в base

    Возвращает:
      (new_entities, false_positive_indices)
      new_entities           — список dict в формате extract()
      false_positive_indices — множество int-индексов base для удаления

    Raises:
        OllamaTimeoutError     — таймаут
        OllamaUnavailableError — сервер недоступен
        OllamaParseError       — невалидный JSON в ответе
    """
    base_description = _build_base_description(base)
    user_message = (
        f"=== БАЗОВЫЙ СПИСОК СУЩНОСТЕЙ (найдено автоматически) ===\n"
        f"{base_description}\n\n"
        f"=== ТЕКСТ ДОКУМЕНТА ===\n"
        f"{text}"
    )

    payload = {
        "model": _OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": _OLLAMA_SYSTEM_PROMPT_WITH_BASE},
            {"role": "user",   "content": user_message},
        ],
        "stream": False,
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
            "Запустите сервер командой: ollama serve"
        )
    except requests.exceptions.Timeout:
        raise OllamaTimeoutError(
            f"Ollama не ответила за {_TIMEOUT} секунд.\n"
            f"Возможные причины:\n"
            f"• Модель {_OLLAMA_MODEL!r} ещё загружается — попробуйте снова через минуту.\n"
            f"• Документ слишком большой — попробуйте разбить на части.\n"
            f"• Не хватает RAM/VRAM для модели."
        )
    except requests.exceptions.HTTPError as exc:
        raise OllamaUnavailableError(f"Ollama вернула HTTP-ошибку: {exc}")

    try:
        content = resp.json()["message"]["content"]
        json_str = _extract_json_object(content)
        parsed = json.loads(json_str)
        if not isinstance(parsed, dict):
            raise OllamaParseError(
                f"Ollama вернула не объект, а {type(parsed).__name__}.\n\nОтвет:\n{content!r}"
            )
    except (KeyError, json.JSONDecodeError) as exc:
        raise OllamaParseError(
            f"Не удалось разобрать ответ Ollama: {exc}\n\nОтвет:\n{content!r}"
        )

    # Разбираем false_positives
    fp_raw = parsed.get("false_positives", [])
    false_positive_indices: set[int] = set()
    if isinstance(fp_raw, list):
        for idx in fp_raw:
            try:
                false_positive_indices.add(int(idx))
            except (TypeError, ValueError) as exc:
                logger.warning("Ollama: некорректный индекс false_positive: %s (%s)", idx, exc)

    if false_positive_indices:
        removed = [(i, base[i]) for i in sorted(false_positive_indices) if i < len(base)]
        logger.info(
            "Ollama: помечено %d ложноположительных: %s",
            len(removed),
            [(v for _, (_, _, _, v) in removed)],
        )

    # Разбираем new
    new_raw = parsed.get("new", [])
    new_entities: list[dict] = []
    if isinstance(new_raw, list):
        conf_map = {"high": 0.9, "medium": 0.6, "low": 0.3}
        for item in new_raw:
            try:
                start = int(item["start"])
                end   = int(item["end"])
                new_entities.append({
                    "text":       item.get("text") or text[start:end],
                    "label":      item.get("label", ""),
                    "start":      start,
                    "end":        end,
                    "confidence": conf_map.get(str(item.get("confidence", "low")), 0.3),
                    "source":     "ollama",
                })
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("Ollama: пропущена новая сущность из-за ошибки: %s", exc)

    return new_entities, false_positive_indices


# ---------------------------------------------------------------------------
# Объединение + дедупликация по перекрытию span
# ---------------------------------------------------------------------------

def _spans_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return not (a_end <= b_start or b_end <= a_start)


def merge_entity_lists(
    base: list[tuple],
    ai: list[dict],
    exclude_indices: set[int] | None = None,
    log_conflicts: bool = True,
) -> list[tuple]:
    """
    Объединение двух списков сущностей с дедупликацией по позиции.

    base            — кортежи (start, end, label, value) из detect_entities()
    ai              — словари {start, end, label, text, ...} из AINer.extract()
    exclude_indices — множество индексов base, помеченных Ollama как
                      ложноположительные (OCR-мусор, неверные срабатывания);
                      эти элементы удаляются перед слиянием

    Возвращает список кортежей (start, end, label, value) —
    тот же формат, что и detect_entities(), чтобы anonymize() его принял.
    """
    # Фильтруем ложноположительные из базового списка
    if exclude_indices:
        filtered_base = [
            ent for i, ent in enumerate(base)
            if i not in exclude_indices
        ]
        logger.info(
            "merge_entity_lists: удалено %d ложноположительных из base (%d → %d)",
            len(base) - len(filtered_base), len(base), len(filtered_base),
        )
    else:
        filtered_base = list(base)

    merged = list(filtered_base)

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

    Использование (с базовым списком — рекомендуется для Ollama)::

        ai_ner = AINer(mode="ollama")
        new_entities, fp_indices = ai_ner.extract(text, base_entities=base)
        merged = merge_entity_lists(base, new_entities, exclude_indices=fp_indices)

    Использование без базового списка (GLiNER или старый режим)::

        ai_ner = AINer(mode="gliner")
        entities = ai_ner.extract(text)
        merged = merge_entity_lists(base, entities)
    """

    def __init__(self, mode: str | None = None, use_cache: bool = True):
        self.mode      = (mode or _DEFAULT_MODE).lower()
        self.use_cache = use_cache

        if self.mode not in {"gliner", "ollama", "off"}:
            logger.warning(
                "Неизвестный режим AI NER: '%s'. Используется 'off'.", self.mode
            )
            self.mode = "off"

    def extract(
        self,
        text: str,
        base_entities: list[tuple] | None = None,
    ) -> tuple[list[dict], set[int]] | list[dict]:
        """
        Извлечь сущности из текста.

        Если передан base_entities и mode == "ollama" — использует расширенный
        промпт с тремя секциями (confirmed / false_positives / new).
        В этом случае возвращает кортеж (new_entities, false_positive_indices).

        Без base_entities (или для GLiNER) — возвращает просто list[dict].

        Исключения OllamaUnavailableError / OllamaTimeoutError / OllamaParseError
        пробрасываются наверх — обрабатывает вызывающий код (UI).
        """
        if self.mode == "off" or not text.strip():
            if base_entities is not None and self.mode == "ollama":
                return [], set()
            return []

        # Режим Ollama с базовым списком — расширенный промпт
        if self.mode == "ollama" and base_entities is not None:
            cache_key = _cache_key(text + str([(s, e, l) for s, e, l, _ in base_entities]), self.mode + "_with_base")
            if self.use_cache and cache_key in _cache:
                logger.debug("AINer: cache hit (mode=%s+base)", self.mode)
                cached = _cache[cache_key]
                # cached хранится как dict с двумя ключами
                return cached["new"], set(cached["fp"])

            new_entities, fp_indices = _run_ollama_with_base(text, base_entities)

            if self.use_cache:
                _cache[cache_key] = {"new": new_entities, "fp": list(fp_indices)}

            return new_entities, fp_indices

        # Обычный режим (GLiNER или Ollama без base)
        if self.use_cache:
            key = _cache_key(text, self.mode)
            if key in _cache:
                logger.debug("AINer: cache hit (mode=%s)", self.mode)
                return _cache[key]

        if self.mode == "gliner":
            result = _run_gliner(text)
        elif self.mode == "ollama":
            result = _run_ollama(text)
        else:
            result = []

        if self.use_cache:
            key = _cache_key(text, self.mode)
            _cache[key] = result

        return result

    def is_enabled(self) -> bool:
        return self.mode != "off"
