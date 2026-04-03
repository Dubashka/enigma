"""AI-powered NER stage for Enigma: GLiNER (Variant A) and Ollama (Variant B).

Mode is controlled by env var ENIGMA_AI_NER_MODE:
  gliner  — use urchade/gliner_multi-v2.1 locally
  ollama  — use Ollama REST API
  off     — skip AI stage entirely (default)

This module is called from md_anonymizer.detect_entities() AFTER the existing
Natasha + Presidio + regex stage. The two span lists are merged with dedup by
overlap so that neither precision nor recall degrades.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODE_ENV = "ENIGMA_AI_NER_MODE"          # "gliner" | "ollama" | "off"
OLLAMA_URL_ENV = "ENIGMA_OLLAMA_URL"     # default http://localhost:11434
OLLAMA_MODEL_ENV = "ENIGMA_OLLAMA_MODEL" # default qwen2.5:7b

_DEFAULT_OLLAMA_URL = "http://localhost:11434"
_DEFAULT_OLLAMA_MODEL = "qwen2.5:7b"

# GLiNER entity labels → internal Enigma labels
_GLINER_LABEL_MAP: dict[str, str] = {
    "person": "ФИО",
    "organization": "ОРГ",
    "address": "АДРЕС",
    "phone": "ТЕЛЕФОН",
    "email": "EMAIL",
    "date": "ДАТА",
    "passport": "ПАСПОРТ",
    "inn": "ИНН",
    "snils": "СНИЛС",
    "contract number": "ДОГОВОР",
}

_GLINER_LABELS: list[str] = list(_GLINER_LABEL_MAP.keys())

# Confidence threshold below which "person" entities are auto-rejected
_PERSON_CONFIDENCE_REJECT = 0.4
# Confidence below which an entity is logged as suspicious (but kept)
_CONFIDENCE_LOG_THRESHOLD = 0.5

# ---------------------------------------------------------------------------
# Span type alias: (start, end, label, value, confidence)
# The first four fields match md_anonymizer convention; confidence is extra.
# ---------------------------------------------------------------------------

AISpan = tuple[int, int, str, str, float]

# ---------------------------------------------------------------------------
# Simple text-hash cache (avoids re-running expensive model on same text)
# ---------------------------------------------------------------------------

_CACHE_ENABLED = True  # can be disabled via disable_cache()
_span_cache: dict[str, list[AISpan]] = {}


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def disable_cache() -> None:  # noqa: D401
    """Disable the in-process result cache (useful in tests)."""
    global _CACHE_ENABLED
    _CACHE_ENABLED = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_mode() -> str:
    return os.environ.get(MODE_ENV, "off").lower().strip()


def _spans_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def _to_enigma_label(raw: str) -> str:
    """Map raw model label string to internal Enigma label."""
    key = raw.lower().strip()
    return _GLINER_LABEL_MAP.get(key, raw.upper())


# ---------------------------------------------------------------------------
# Variant A — GLiNER
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _load_gliner_model():
    """Load GLiNER model once and cache the instance."""
    from gliner import GLiNER  # type: ignore[import]
    model_name = os.environ.get("ENIGMA_GLINER_MODEL", "urchade/gliner_multi-v2.1")
    logger.info("[ai_ner] Loading GLiNER model: %s", model_name)
    return GLiNER.from_pretrained(model_name)


def _gliner_entities(text: str) -> list[AISpan]:
    """Run GLiNER on *text* and return spans with confidence."""
    try:
        model = _load_gliner_model()
        entities = model.predict_entities(text, _GLINER_LABELS, threshold=0.0)
    except Exception as exc:
        logger.warning("[ai_ner/gliner] Model error: %s", exc)
        return []

    result: list[AISpan] = []
    for ent in entities:
        raw_label: str = ent.get("label", "")
        score: float = float(ent.get("score", 0.0))
        start: int = ent.get("start", 0)
        end: int = ent.get("end", 0)
        value: str = text[start:end]
        label = _to_enigma_label(raw_label)

        # Hard reject low-confidence persons
        if raw_label.lower() == "person" and score < _PERSON_CONFIDENCE_REJECT:
            logger.debug(
                "[ai_ner/gliner] REJECTED low-confidence person (%.2f): %r",
                score, value,
            )
            continue

        if score < _CONFIDENCE_LOG_THRESHOLD:
            logger.debug(
                "[ai_ner/gliner] Low confidence (%.2f) for %s %r — kept, flagged",
                score, label, value,
            )

        result.append((start, end, label, value, score))

    return result


# ---------------------------------------------------------------------------
# Variant B — Ollama
# ---------------------------------------------------------------------------

_OLLAMA_PROMPT_TEMPLATE = """Ты — система распознавания именованных сущностей (NER).
Проанализируй текст на русском языке и найди ВСЕ конфиденциальные сущности.

Возможные метки:
- ФИО — полное имя человека
- ОРГ — название организации / компании
- АДРЕС — почтовый или физический адрес
- ТЕЛЕФОН — номер телефона
- EMAIL — адрес электронной почты
- ДАТА — дата или период
- ПАСПОРТ — серия и номер паспорта
- ИНН — ИНН физлица (12 цифр) или юрлица (10 цифр)
- СНИЛС — СНИЛС
- ДОГОВОР — номер договора / контракта

Отвечай ТОЛЬКО валидным JSON-массивом, без объяснений:
[
  {{"text": "...", "label": "ФИО", "start": 0, "end": 10, "confidence": "high"}},
  ...
]

Если сущностей нет — верни пустой массив [].

Текст:
{text}
"""

_CONFIDENCE_MAP = {"high": 0.9, "medium": 0.6, "low": 0.3}


def _ollama_entities(text: str) -> list[AISpan]:
    """Call Ollama REST API and parse response into AISpan list."""
    import requests  # already in requirements

    base_url = os.environ.get(OLLAMA_URL_ENV, _DEFAULT_OLLAMA_URL).rstrip("/")
    model = os.environ.get(OLLAMA_MODEL_ENV, _DEFAULT_OLLAMA_MODEL)
    url = f"{base_url}/api/chat"

    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [
            {
                "role": "system",
                "content": "Ты — JSON-only NER API. Отвечай только валидным JSON-массивом.",
            },
            {
                "role": "user",
                "content": _OLLAMA_PROMPT_TEMPLATE.format(text=text),
            },
        ],
        "options": {"temperature": 0, "seed": 42},
    }

    try:
        import requests as _req
        resp = _req.post(url, json=payload, timeout=120)
        resp.raise_for_status()
        raw_content: str = resp.json()["message"]["content"]
    except Exception as exc:
        logger.warning("[ai_ner/ollama] Unavailable — falling back: %s", exc)
        return []

    # Extract JSON array from response
    array_text = _extract_json_array(raw_content)
    if not array_text:
        logger.warning("[ai_ner/ollama] No JSON array found in response")
        return []

    try:
        entities: list[dict[str, Any]] = json.loads(array_text)
    except json.JSONDecodeError as exc:
        logger.warning("[ai_ner/ollama] JSON parse error: %s", exc)
        return []

    result: list[AISpan] = []
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        ent_text: str = str(ent.get("text", ""))
        label: str = str(ent.get("label", "")).upper()
        conf_raw: str = str(ent.get("confidence", "medium")).lower()
        confidence: float = _CONFIDENCE_MAP.get(conf_raw, 0.6)

        start: int | None = ent.get("start")
        end: int | None = ent.get("end")

        # If model gave positions — validate them; otherwise locate by search
        if isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(text):
            if text[start:end] != ent_text:
                # Positions are wrong — relocate
                found_pos = text.find(ent_text)
                if found_pos == -1:
                    continue
                start, end = found_pos, found_pos + len(ent_text)
        else:
            found_pos = text.find(ent_text)
            if found_pos == -1:
                continue
            start, end = found_pos, found_pos + len(ent_text)

        result.append((start, end, label, ent_text, confidence))

    return result


def _extract_json_array(text: str) -> str:
    """Extract first JSON array [...] from arbitrary text."""
    # Try markdown code block first
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        candidate = m.group(1).strip()
        if candidate.startswith("["):
            return candidate
    # Find outermost [...]
    start = text.find("[")
    if start == -1:
        return ""
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return ""


# ---------------------------------------------------------------------------
# Conflict logging
# ---------------------------------------------------------------------------

def _log_conflicts(
    classic: list[tuple[int, int, str, str]],
    ai_spans: list[AISpan],
) -> None:
    """Log label mismatches between classic NER and AI NER for the same span."""
    for a_start, a_end, a_label, a_value in classic:
        for b_start, b_end, b_label, b_value, _conf in ai_spans:
            if _spans_overlap(a_start, a_end, b_start, b_end) and a_label != b_label:
                logger.info(
                    "[ai_ner] CONFLICT span=[%d:%d] classic=%s(%r) ai=%s(%r)",
                    a_start, a_end, a_label, a_value, b_label, b_value,
                )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_entities_ai(
    text: str,
    classic_spans: list[tuple[int, int, str, str]] | None = None,
) -> list[tuple[int, int, str, str]]:
    """Run AI NER stage and return *only* the AI-found spans (without confidence).

    Call merge_with_classic() to combine with classic pipeline.
    Returns empty list if mode is 'off' or model is unavailable.

    Args:
        text: Input text.
        classic_spans: Spans already found by classic pipeline (used for conflict logging).

    Returns:
        List of (start, end, label, value) tuples.
    """
    mode = _get_mode()
    if mode == "off":
        return []

    if _CACHE_ENABLED:
        key = _text_hash(text)
        if key in _span_cache:
            logger.debug("[ai_ner] Cache hit")
            ai_spans = _span_cache[key]
        else:
            ai_spans = _run_model(mode, text)
            _span_cache[key] = ai_spans
    else:
        ai_spans = _run_model(mode, text)

    if classic_spans:
        _log_conflicts(classic_spans, ai_spans)

    # Strip confidence before returning
    return [(s, e, l, v) for s, e, l, v, _c in ai_spans]


def _run_model(mode: str, text: str) -> list[AISpan]:
    """Dispatch to the configured backend."""
    if mode == "gliner":
        return _gliner_entities(text)
    if mode == "ollama":
        return _ollama_entities(text)
    logger.warning("[ai_ner] Unknown mode %r — returning empty", mode)
    return []


def merge_with_classic(
    classic: list[tuple[int, int, str, str]],
    ai: list[tuple[int, int, str, str]],
) -> list[tuple[int, int, str, str]]:
    """Union of classic + AI spans, deduplicated by position overlap.

    Classic spans take precedence on overlap (they keep their label).
    AI-only spans that don't overlap with any classic span are appended.
    """
    result = list(classic)
    for a_start, a_end, a_label, a_value in ai:
        overlaps = any(
            _spans_overlap(a_start, a_end, c_start, c_end)
            for c_start, c_end, _, _ in classic
        )
        if not overlaps:
            result.append((a_start, a_end, a_label, a_value))
    return result
