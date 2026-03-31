"""LM Studio integration for AI-based column sensitivity analysis."""
from __future__ import annotations

import json
import re

import pandas as pd
import requests

LM_STUDIO_URL = "http://127.0.0.1:1234/v1/chat/completions"
_MAX_RETRIES = 3


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

    # Find outermost {...} in the full text (works even inside <think> blocks)
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


def check_columns_with_ai(
    sheets: dict[str, pd.DataFrame],
    presidio_required: dict[str, list[str]] | None = None,
) -> dict[str, dict[str, str]]:
    """Call LM Studio to classify columns for privacy sensitivity.

    Returns:
        {sheet_name: {col_name: "required" | "recommended" | "safe"}}
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
        print(f"[AI] Библиотека: {len(cached)} классификаций. Колонки в файле: {list(all_current_cols)}")
        print(f"[AI] Найдено в кэше: {[c for c in all_current_cols if c in cached]}")
        print(f"[AI] Не найдено в кэше: {[c for c in all_current_cols if c not in cached]}")
    except Exception as e:
        print(f"[AI] Ошибка чтения библиотеки: {e}")
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

    # If all columns are known — return immediately without calling LM Studio
    total_unknown = sum(len(v) for v in unknown_cols.values())
    if total_unknown == 0:
        print("[AI] Все колонки найдены в библиотеке — LM Studio не вызывается")
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

    payload = {
        "model": "local-model",
        "messages": [
            {
                "role": "system",
                "content": "You are a JSON-only API. Reply with valid JSON only. No thinking tags, no explanation, no markdown.",
            },
            {"role": "user", "content": "/no_think\n\n" + prompt},
            # Prefill assistant response with "{" — forces model to continue as JSON
            {"role": "assistant", "content": "{"},
        ],
        "temperature": 0,
        "seed": 42,
        "max_tokens": 800,
        "chat_template_kwargs": {"enable_thinking": False},
    }

    last_error: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        print(f"[AI] Попытка {attempt}/{_MAX_RETRIES}…")
        response = requests.post(LM_STUDIO_URL, json=payload, timeout=None)
        response.raise_for_status()

        message = response.json()["choices"][0]["message"]
        # Collect all text the model produced (content + reasoning_content for qwen3)
        full_text = " ".join(
            (message.get(field) or "")
            for field in ("content", "reasoning_content")
        ).strip()
        # Restore prefill "{" — model continues from it without repeating
        if full_text and not full_text.lstrip().startswith("{"):
            full_text = "{" + full_text
        print(f"[AI] Попытка {attempt}, ответ: {full_text[:200]}")

        candidate = _extract_json(full_text)
        if candidate:
            try:
                raw: dict = json.loads(candidate)
                # Merge: prefilled (from library) + new from LM Studio
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
                print(f"[AI] Успешно на попытке {attempt}")
                return result
            except json.JSONDecodeError as exc:
                last_error = exc
                print(f"[AI] Попытка {attempt}: JSON невалидный — {exc}")
        else:
            last_error = ValueError("JSON не найден в ответе модели")
            print(f"[AI] Попытка {attempt}: пустой ответ")

    raise RuntimeError(
        f"Модель не вернула валидный JSON после {_MAX_RETRIES} попыток. "
        f"Последняя ошибка: {last_error}"
    )


def get_fake_prefix_from_ai(col_name: str, samples: list[str]) -> str | None:
    """Ask LM Studio for a single neutral Russian noun to use as a fake value prefix.

    Example: col_name="Отдел", samples=["Бухгалтерия", "ИТ-поддержка"] → "Подразделение"
    Returns None if LM Studio is unavailable or response is unusable.
    """
    samples_str = ", ".join(f'"{s}"' for s in samples[:3])
    prompt = (
        f'Название колонки: "{col_name}". Примеры значений: {samples_str}. '
        "Напиши ОДНО короткое нейтральное русское существительное в именительном падеже, "
        "которое подойдёт как анонимный заменитель для значений этого типа. "
        "Только слово, без объяснений."
    )
    payload = {
        "model": "local-model",
        "messages": [
            {
                "role": "system",
                "content": "Ты помощник по анонимизации данных. Отвечай одним словом.",
            },
            {"role": "user", "content": "/no_think\n\n" + prompt},
        ],
        "temperature": 0,
        "seed": 42,
        "max_tokens": 10,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    try:
        response = requests.post(LM_STUDIO_URL, json=payload, timeout=10)
        response.raise_for_status()
        text = response.json()["choices"][0]["message"].get("content", "").strip()
        # Take only the first word, strip punctuation
        word = re.split(r"[\s\n.,!?;:\-–—]", text)[0].strip()
        if word and len(word) >= 2:
            return word.capitalize()
    except Exception:
        pass
    return None
