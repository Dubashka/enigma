"""Ollama integration for AI-based column sensitivity analysis."""
from __future__ import annotations

import json
import logging
import os
import re

import pandas as pd
import requests

logger = logging.getLogger(__name__)

OLLAMA_URL   = os.environ.get("ENIGMA_OLLAMA_URL",   "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("ENIGMA_OLLAMA_MODEL", "qwen2.5:7b")
_MAX_RETRIES = 3
_TIMEOUT     = 60  # секунд


class OllamaUnavailableError(RuntimeError):
    """Пробрасывается в UI, если Ollama недоступна или не отвечает."""


def _build_column_samples(sheets: dict[str, pd.DataFrame], max_rows: int = 3) -> str:
    """Build compact column-name + sample-values list (no full CSV, less tokens)."""
    parts = []
    for sheet_name, df in sheets.items():
        lines = [f"Лист: {sheet_name}"]
        for col in df.columns:
            samples = df[col].dropna().astype(str).unique()[:max_rows]
            sample_str = ", ".join(samples) if len(samples) else "—"
            lines.append(f"  - {col}: {sample_str}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def _extract_json(text: str) -> str:
    """Extract JSON object from text regardless of where the model put it."""
    # Try markdown code block first
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        return match.group(1).strip()

    # Find outermost {...} in the full text
    start = text.find("{")
    if start != -1:
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]

    return ""


def _call_ollama(messages: list[dict], max_tokens: int = 800) -> str:
    """Send a chat request to Ollama and return the response content string.

    Raises:
        OllamaUnavailableError — connection error or timeout
        requests.HTTPError    — non-2xx HTTP response
    """
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": max_tokens,
        },
    }
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json=payload,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.exceptions.ConnectionError:
        raise OllamaUnavailableError(
            f"Ollama недоступна по адресу {OLLAMA_URL}.\n"
            "Запустите: ollama serve"
        )
    except requests.exceptions.Timeout:
        raise OllamaUnavailableError(
            f"Ollama не ответила за {_TIMEOUT} секунд "
            f"(модель {OLLAMA_MODEL} может ещё загружаться).\n"
            "Подождите и попробуйте снова."
        )

    return resp.json()["message"]["content"]


def check_columns_with_ai(
    sheets: dict[str, pd.DataFrame],
    presidio_required: dict[str, list[str]] | None = None,
) -> dict[str, dict[str, str]]:
    """Call Ollama to classify columns for privacy sensitivity.

    Returns:
        {sheet_name: {col_name: "required" | "recommended" | "safe"}}

    Raises:
        OllamaUnavailableError — if Ollama is not running
        RuntimeError           — if the model fails to return valid JSON
    """
    columns_info = {name: list(df.columns) for name, df in sheets.items()}
    all_current_cols = {c for cols in columns_info.values() for c in cols}

    # Check library for cached classifications — skip known columns
    try:
        from core.library import AttributeLibrary
        lib = AttributeLibrary()
        cached = lib.get_all_classifications()
        known_columns = lib.get_known_columns()
        relevant_known = [c for c in known_columns if c in all_current_cols]
        logger.info("[AI] Библиотека: %d классификаций. Колонки в файле: %s",
                    len(cached), list(all_current_cols))
        logger.info("[AI] Найдено в кэше: %s",
                    [c for c in all_current_cols if c in cached])
        logger.info("[AI] Не найдено в кэше: %s",
                    [c for c in all_current_cols if c not in cached])
    except Exception as e:
        logger.warning("[AI] Ошибка чтения библиотеки: %s", e)
        cached = {}
        relevant_known = []

    # Pre-fill result with cached verdicts
    prefilled: dict[str, dict[str, str]] = {}
    unknown_cols: dict[str, list[str]] = {}
    for sheet_name, df in sheets.items():
        prefilled[sheet_name] = {}
        unknown_cols[sheet_name] = []
        for col in df.columns:
            if col in cached:
                prefilled[sheet_name][col] = cached[col]
            else:
                unknown_cols[sheet_name].append(col)

    # If all columns are known — return immediately without calling Ollama
    total_unknown = sum(len(v) for v in unknown_cols.values())
    if total_unknown == 0:
        logger.info("[AI] Все колонки найдены в библиотеке — Ollama не вызывается")
        return prefilled

    # Build samples only for unknown columns
    unknown_sheets = {
        name: df[unknown_cols[name]] for name, df in sheets.items() if unknown_cols[name]
    }
    samples_text = _build_column_samples(unknown_sheets, max_rows=3)
    unknown_info = {name: unknown_cols[name] for name in unknown_cols if unknown_cols[name]}

    known_hint = (
        f"\nPreviously masked columns (treat as at least 'recommended'): {relevant_known}\n"
        if relevant_known else ""
    )

    # Presidio hint — columns confirmed to contain email/phone/IP
    presidio_flat = []
    if presidio_required:
        for cols in presidio_required.values():
            presidio_flat.extend(cols)
    presidio_hint = (
        f"\nColumns confirmed by pattern scanner to contain personal data (classify as 'required'): {presidio_flat}\n"
        if presidio_flat else ""
    )

    prompt = (
        "Classify each table column for personal data sensitivity. "
        "Return ONLY valid JSON, no explanation.\n\n"
        f"Columns and sample values:\n{samples_text}\n"
        f"{known_hint}{presidio_hint}\n"
        "Categories:\n"
        '- "required": must mask (full name, passport, tax ID, phone, email, address, DOB, medical)\n'
        '- "recommended": should mask (job title, company, city, IP)\n'
        '- "safe": no masking needed (technical IDs, statuses, amounts, event dates)\n\n'
        f"JSON format: {json.dumps({k: {c: 'required|recommended|safe' for c in v} for k, v in unknown_info.items()}, ensure_ascii=False)}"
    )

    messages = [
        {
            "role": "system",
            "content": "You are a JSON-only API. Reply with valid JSON only. No explanation, no markdown.",
        },
        {"role": "user", "content": prompt},
    ]

    last_error: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        logger.info("[AI] Попытка %d/%d…", attempt, _MAX_RETRIES)
        # OllamaUnavailableError propagates immediately — no retry on connection errors
        full_text = _call_ollama(messages, max_tokens=800)
        logger.info("[AI] Попытка %d, ответ: %s", attempt, full_text[:200])

        candidate = _extract_json(full_text)
        if candidate:
            try:
                raw: dict = json.loads(candidate)
                # Merge: prefilled (from library) + new from Ollama
                result: dict[str, dict[str, str]] = {}
                for sheet_name, df in sheets.items():
                    sheet_raw = raw.get(sheet_name, {})
                    result[sheet_name] = {}
                    for col in df.columns:
                        if col in prefilled.get(sheet_name, {}):
                            result[sheet_name][col] = prefilled[sheet_name][col]
                        else:
                            verdict = sheet_raw.get(col, "safe")
                            result[sheet_name][col] = verdict
                logger.info("[AI] Успешно на попытке %d", attempt)
                return result
            except json.JSONDecodeError as exc:
                last_error = exc
                logger.warning("[AI] Попытка %d: JSON невалидный — %s", attempt, exc)
        else:
            last_error = ValueError("JSON не найден в ответе модели")
            logger.warning("[AI] Попытка %d: пустой ответ", attempt)

    raise RuntimeError(
        f"Модель не вернула валидный JSON после {_MAX_RETRIES} попыток. "
        f"Последняя ошибка: {last_error}"
    )


def get_fake_prefix_from_ai(col_name: str, samples: list[str]) -> str | None:
    """Ask Ollama for a single neutral Russian noun to use as a fake value prefix.

    Example: col_name="Отдел", samples=["Бухгалтерия", "ИТ-поддержка"] → "Подразделение"
    Returns None if Ollama is unavailable or response is unusable.
    """
    samples_str = ", ".join(f'"{s}"' for s in samples[:3])
    prompt = (
        f'Название колонки: "{col_name}". Примеры значений: {samples_str}. '
        "Напиши ОДНО короткое нейтральное русское существительное в именительном падеже, "
        "которое подойдёт как анонимный заменитель для значений этого типа. "
        "Только слово, без объяснений."
    )
    messages = [
        {
            "role": "system",
            "content": "Ты помощник по анонимизации данных. Отвечай одним словом.",
        },
        {"role": "user", "content": prompt},
    ]
    try:
        text = _call_ollama(messages, max_tokens=10).strip()
        # Take only the first word, strip punctuation
        word = re.split(r"[\s\n.,!?;:\-–—]", text)[0].strip()
        if word and len(word) >= 2:
            return word.capitalize()
    except Exception:
        pass
    return None
