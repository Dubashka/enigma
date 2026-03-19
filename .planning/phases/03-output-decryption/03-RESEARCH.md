# Phase 03: Output + Decryption - Research

**Researched:** 2026-03-20
**Domain:** Streamlit file downloads, in-memory Excel/JSON generation, reverse mapping decryption
**Confidence:** HIGH

## Summary

Phase 3 is a primarily integration phase: all the building blocks already exist in the codebase. The masking engine in `core/masker.py` already returns the mapping dict that becomes both the JSON export and the decryption key. Session state keys are already defined in `core/state_keys.py`. The Streamlit `st.download_button` API is the correct tool for stateless in-browser file delivery — no disk writes needed.

The output side (OUT-01..03) is straightforward: replace three disabled stubs in `_render_step_masked()` with real `st.download_button` calls, generating files in-memory via `io.BytesIO`. The decryption side (DECR-01..03) requires replacing the placeholder `views/decryption.py` with a full page: two file uploaders, preview, and a reverse-mapping pass using `pd.Series.map()`.

The only non-trivial design question is the decryption normalization: text masking stored normalized keys (`_normalize(value) -> pseudonym`), so decryption must build the reverse dict `{pseudonym -> original}` from the JSON's `"text"` dict, then apply it via lookup. Values introduced by LLM that have no entry in the pseudonym dict simply pass through unchanged — this is the natural behavior of `dict.get(key, original)`.

**Primary recommendation:** Use `st.download_button` for all downloads; build reverse mapping by inverting `mapping["text"]`; reuse `render_preview()` and `parse_upload()` for decryption page.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Скачивание файлов (OUT-01, OUT-02, OUT-03)
- Заменить заглушки (disabled st.button) на st.download_button с реальными данными
- Генерация файлов в памяти через BytesIO — без записи на диск (stateless)
- xlsx через pandas ExcelWriter с engine='xlsxwriter' — сохраняет все листы и структуру
- Три кнопки скачивания: замаскированный xlsx, маппинг JSON, маппинг Excel

#### Формат маппинга JSON (OUT-02)
- Использовать существующий формат из masker.py как есть: `{"text": {norm_val: pseudonym}, "numeric": {col: multiplier}}`
- Файл называется `{original_name}_mapping.json`
- UTF-8 encoding, ensure_ascii=False для кириллицы

#### Формат маппинга Excel (OUT-03)
- Два листа в файле:
  - "Текстовый маппинг": колонки Оригинал | Псевдоним
  - "Числовой маппинг": колонки Колонка | Коэффициент
- Файл называется `{original_name}_mapping.xlsx`

#### Статистика (OUT-04)
- Уже реализована в Phase 2 (Step 3: st.metric "Замаскировано значений" и "Уникальных сущностей")
- Никаких дополнительных изменений не нужно — требование выполнено

#### Дешифровка — загрузка файлов (DECR-01)
- Вкладка "Дешифровка" в сайдбаре — уже есть placeholder в views/decryption.py
- Два st.file_uploader на странице: замаскированный файл (xlsx/csv) + JSON маппинг
- После загрузки обоих файлов показать превью замаскированных данных
- Кнопка "Дешифровать" запускает обратную замену

#### Дешифровка — логика замены (DECR-02, DECR-03)
- Инвертировать text mapping: {pseudonym -> original} и применить Series.map()
- Для числовых колонок: разделить на коэффициент (обратная операция)
- Новые колонки/строки от LLM (не найденные в маппинге) — оставить без изменений
- NaN остаются NaN
- После дешифровки: превью восстановленных данных + кнопка скачивания xlsx

### Claude's Discretion
- Обработка ошибок при загрузке невалидного JSON маппинга
- Дизайн страницы дешифровки (layout, подписи)
- Именование скачиваемого восстановленного файла

### Deferred Ideas (OUT OF SCOPE)
- DECR-04: Нечёткая дешифровка (fuzzy matching) — v2
- Скачивание в формате CSV (только xlsx в v1)
- Предпросмотр различий до/после дешифровки
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| OUT-01 | Пользователь скачивает замаскированный Excel-файл со всеми листами | `st.download_button` + `pd.ExcelWriter(BytesIO, engine='xlsxwriter')` multi-sheet pattern |
| OUT-02 | Пользователь скачивает маппинг в формате JSON | `json.dumps(mapping, indent=2, ensure_ascii=False).encode('utf-8')` → `st.download_button` |
| OUT-03 | Пользователь скачивает маппинг в формате Excel | `pd.ExcelWriter` с двумя листами — "Текстовый маппинг" и "Числовой маппинг" |
| OUT-04 | Система показывает статистику: количество замаскированных значений и уникальных сущностей | Already complete in Phase 2 — `st.metric` in `_render_step_masked()` |
| DECR-01 | Пользователь загружает замаскированный файл + JSON-маппинг | Two `st.file_uploader` widgets; `parse_upload()` for xlsx/csv; `json.loads()` for mapping |
| DECR-02 | Система заменяет псевдонимы обратно на оригинальные значения | Invert `mapping["text"]` → `{pseudonym: original}`, apply via `Series.map()`; numeric: divide by coefficient |
| DECR-03 | Новые колонки/строки (добавленные LLM) остаются без изменений | Natural behavior of `dict.get(val, val)` — unmapped values pass through unchanged |
</phase_requirements>

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| streamlit | 1.55.0 | `st.download_button`, `st.file_uploader` | Already installed and used throughout |
| pandas | 3.0.1 | `ExcelWriter`, `Series.map()`, DataFrame operations | Already in use; vectorized ops |
| xlsxwriter | 3.2.9 | Excel write engine for multi-sheet output | Already installed; required for `engine='xlsxwriter'` |
| openpyxl | 3.1.5 | Excel read engine in `parse_upload()` | Already in use for parsing |
| io (stdlib) | — | `io.BytesIO` for in-memory file buffers | No disk writes — stateless constraint |
| json (stdlib) | — | `json.dumps`/`json.loads` for mapping serialization | Standard library, no additional deps |

### Installation
```bash
# All required packages already in requirements.txt — no new installations needed
```

## Architecture Patterns

### Recommended Project Structure
No structural changes needed. All new code fits into:
```
views/
└── decryption.py     # Replace placeholder with full decryption page
core/
└── decryptor.py      # New: pure decryption logic (mirrors masker.py pattern)
tests/
└── test_decryptor.py # New: unit tests for decryption engine
```

The `views/masking.py` download stubs are replaced in-place; no new files for output.

### Pattern 1: st.download_button with BytesIO
**What:** Generate file content in memory, pass bytes to `st.download_button`. The button renders immediately; Streamlit delivers the file when clicked.
**When to use:** All three download buttons (masked xlsx, JSON mapping, Excel mapping).

```python
# Source: Streamlit docs — st.download_button API
import io

buf = io.BytesIO()
with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
    for sheet_name, df in masked_sheets.items():
        df.to_excel(writer, sheet_name=sheet_name, index=False)
buf.seek(0)

st.download_button(
    label="Скачать замаскированный файл",
    data=buf,
    file_name=f"{base_name}_masked.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)
```

### Pattern 2: JSON mapping serialization
**What:** Convert the `mapping["text"]` dict (keys are normalized strings) to a human-readable JSON file.
**When to use:** OUT-02.

```python
import json

json_bytes = json.dumps(mapping, indent=2, ensure_ascii=False).encode("utf-8")

st.download_button(
    label="Скачать маппинг (JSON)",
    data=json_bytes,
    file_name=f"{base_name}_mapping.json",
    mime="application/json",
    use_container_width=True,
)
```

### Pattern 3: Excel mapping with two sheets
**What:** Two DataFrames written to separate sheets in one xlsx file via `ExcelWriter`.
**When to use:** OUT-03.

```python
buf = io.BytesIO()
with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
    text_df = pd.DataFrame(
        list(mapping["text"].items()),
        columns=["Оригинал", "Псевдоним"],
    )
    text_df.to_excel(writer, sheet_name="Текстовый маппинг", index=False)

    numeric_df = pd.DataFrame(
        list(mapping["numeric"].items()),
        columns=["Колонка", "Коэффициент"],
    )
    numeric_df.to_excel(writer, sheet_name="Числовой маппинг", index=False)
buf.seek(0)
```

### Pattern 4: Reverse mapping for decryption
**What:** Invert the `"text"` dict and apply via `Series.map()`. Uses the same `dict.get(v, v)` passthrough pattern as `apply_text_masking` — unmapped values stay unchanged.
**When to use:** DECR-02.

```python
# Source: mirrors apply_text_masking pattern in core/masker.py
def apply_text_decryption(series: pd.Series, reverse_map: dict[str, str]) -> pd.Series:
    def lookup(v):
        if pd.isna(v):
            return v
        return reverse_map.get(str(v), v)  # passthrough if not found (LLM-added values)
    return series.map(lookup)

def apply_numeric_decryption(series: pd.Series, multiplier: float) -> pd.Series:
    result = series / multiplier
    if pd.api.types.is_integer_dtype(series):
        return result.round().astype("Int64")
    return result.round(2)
```

### Pattern 5: Decryption column matching
**What:** The decryption pass only modifies columns whose names appear in the mapping. Columns added by LLM that don't appear in `mapping["numeric"]` keys are left untouched. Text columns are processed by value lookup — cells whose values aren't in the reverse map pass through by default.
**When to use:** DECR-03.

```python
# Numeric: only columns known in mapping
for col, multiplier in mapping["numeric"].items():
    if col in df.columns:
        df[col] = apply_numeric_decryption(df[col], multiplier)

# Text: apply to all columns with text values; lookup handles unknowns
reverse_text = {v: k for k, v in mapping["text"].items()}
# But mapping["text"] keys are normalized originals; we need {pseudonym -> normalized_original}
# The mapping format is {norm_original: pseudonym}, so invert to {pseudonym: norm_original}
```

**Important:** The mapping format is `{normalized_original: pseudonym}`. Inversion gives `{pseudonym: normalized_original}` — the normalized original (uppercase, no quotes). For display this is acceptable since the original masked data was already normalized for lookup purposes. However, we must check whether `norm_original` (uppercase) is "good enough" for the user or if we need to preserve case from the original file.

**Verdict:** The mapping only stores the normalized key, not the display-case original. This means decrypted text will be uppercase/normalized. The planner needs to decide how to handle this — see Open Questions.

### Anti-Patterns to Avoid
- **Disk writes:** Never use `open()` or temp files — BytesIO only (stateless constraint UI-02).
- **`iterrows()` in decryption:** Mirror masker.py and use `Series.map()` — vectorized.
- **Re-running mask on decryption page:** Decryption reads its own uploaded files independently from masking session state — no dependency.
- **Calling `_normalize()` on pseudonyms during decryption:** Pseudonyms are already clean strings (e.g., "Предприятие A") — no normalization needed for reverse lookup.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Multi-sheet Excel write | Custom openpyxl sheet builder | `pd.ExcelWriter(buf, engine='xlsxwriter')` | One context manager, handles all sheets |
| File delivery to browser | Flask endpoint or base64 link | `st.download_button(data=bytes_or_buffer)` | Native Streamlit, zero server storage |
| JSON encoding | Custom serializer | `json.dumps(..., ensure_ascii=False, indent=2)` | Handles Cyrillic, nested dicts, floats correctly |
| CSV auto-detection on decryption input | Custom sniffer | `parse_upload()` already in `core/parser.py` | Handles xlsx and csv with encoding detection |

**Key insight:** The entire output/decryption domain is a thin layer on top of already-correct data structures. Resist the temptation to re-architect.

## Common Pitfalls

### Pitfall 1: mapping["text"] key direction
**What goes wrong:** Inverting the mapping as `{v: k for k, v in mapping["text"].items()}` looks right but produces `{pseudonym: normalized_original}` not `{pseudonym: display_original}`. The normalized original is uppercased and quote-stripped — not the same as the original file value.
**Why it happens:** `masker.py` only stores the normalized form as the key. The original display string is lost after masking.
**How to avoid:** Accept that decrypted text is normalized (uppercase). This is consistent with how masking works and is documented in CONTEXT.md. If display-case recovery is ever needed, a separate pre-normalization lookup table would need to be added in a future phase.
**Warning signs:** Decrypted values appearing in UPPERCASE where original was mixed-case.

### Pitfall 2: `st.download_button` triggers full rerun
**What goes wrong:** Clicking a download button causes Streamlit to rerun the entire script. If download data is computed on every rerun (e.g., generating Excel), this is fine — but if it triggers side effects (state changes, re-masking), those side effects run again.
**Why it happens:** Streamlit's execution model reruns the whole script on every widget interaction.
**How to avoid:** Generate download bytes from session state values only — no side effects in the generation functions. Keep `_generate_masked_xlsx()`, `_generate_mapping_json()`, `_generate_mapping_xlsx()` as pure functions reading from `st.session_state`.
**Warning signs:** Masking results changing after clicking download.

### Pitfall 3: Decryption page state independence
**What goes wrong:** Decryption page reads `st.session_state[MASKED_SHEETS]` or `MAPPING` set by the masking flow, making the decryption tab dependent on the masking tab having been used in the same session.
**Why it happens:** Session state is shared across pages in Streamlit.
**How to avoid:** Decryption page manages its own local state (uploaded file bytes + uploaded JSON) entirely independently. Use distinct session state keys like `DECR_SHEETS`, `DECR_MAPPING`, `DECR_RESULT`.
**Warning signs:** Decryption page breaks when opened directly without going through masking flow.

### Pitfall 4: JSON mapping keys are strings even for numeric column names
**What goes wrong:** `json.loads()` returns all keys as strings. When the mapping was `{"numeric": {"Сумма": 1.2}}`, after `json.loads()` it's `{"Сумма": 1.2}` — still a string key, which matches DataFrame column names. No conversion needed, but developers sometimes try to convert unnecessarily.
**Why it happens:** Python dicts with string keys survive JSON round-trip without issue.
**How to avoid:** Use `mapping["numeric"]` directly for column-name lookups after loading.
**Warning signs:** KeyError on column lookup, or unnecessary `int()` conversion attempts.

### Pitfall 5: ExcelWriter context manager must close before seek(0)
**What goes wrong:** `buf.seek(0)` before the `with pd.ExcelWriter(...) as writer:` block exits leaves an incomplete/unflushed file.
**Why it happens:** `xlsxwriter` flushes and finalizes the file only on `writer.close()` which happens at `__exit__`.
**How to avoid:** Always place `buf.seek(0)` after the `with` block closes.

```python
buf = io.BytesIO()
with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
    df.to_excel(writer, sheet_name="Sheet1", index=False)
buf.seek(0)  # AFTER the with block
```

## Code Examples

### OUT-01: Generate masked xlsx in memory
```python
# Source: pandas ExcelWriter docs + xlsxwriter engine
import io
import pandas as pd

def generate_masked_xlsx(masked_sheets: dict[str, pd.DataFrame]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        for sheet_name, df in masked_sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    buf.seek(0)
    return buf.read()
```

### OUT-02: Serialize mapping to JSON bytes
```python
import json

def generate_mapping_json(mapping: dict) -> bytes:
    return json.dumps(mapping, indent=2, ensure_ascii=False).encode("utf-8")
```

### OUT-03: Generate mapping Excel with two sheets
```python
def generate_mapping_xlsx(mapping: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        text_df = pd.DataFrame(
            list(mapping["text"].items()),
            columns=["Оригинал", "Псевдоним"],
        )
        text_df.to_excel(writer, sheet_name="Текстовый маппинг", index=False)
        numeric_df = pd.DataFrame(
            list(mapping["numeric"].items()),
            columns=["Колонка", "Коэффициент"],
        )
        numeric_df.to_excel(writer, sheet_name="Числовой маппинг", index=False)
    buf.seek(0)
    return buf.read()
```

### DECR-01: Load mapping JSON from uploaded file
```python
import json

def load_mapping_from_upload(uploaded_json_file) -> dict | None:
    try:
        content = uploaded_json_file.read()
        return json.loads(content.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, KeyError):
        return None  # caller handles error display
```

### DECR-02: Apply reverse text and numeric decryption
```python
def decrypt_sheets(
    sheets: dict[str, pd.DataFrame],
    mapping: dict,
) -> dict[str, pd.DataFrame]:
    reverse_text = {v: k for k, v in mapping["text"].items()}
    numeric_map = mapping["numeric"]

    result = {}
    for sheet_name, df in sheets.items():
        decrypted_df = df.copy()
        for col in decrypted_df.columns:
            # Numeric decryption by column name match
            if col in numeric_map:
                coeff = numeric_map[col]
                decrypted_df[col] = decrypted_df[col].apply(
                    lambda v: round(v / coeff, 2) if pd.notna(v) else v
                )
            else:
                # Text decryption by value lookup — unknown values pass through
                decrypted_df[col] = decrypted_df[col].map(
                    lambda v: reverse_text.get(str(v), v) if pd.notna(v) else v
                )
        result[sheet_name] = decrypted_df
    return result
```

**Note on text decryption column scope:** The above applies text lookup to all non-numeric columns. If LLM added new text columns, their values won't be in the reverse map and will pass through unchanged (DECR-03 satisfied). If a column has both pseudonymized and LLM-added text, individual cells pass through independently.

### Decryption page structure (views/decryption.py)
```python
import streamlit as st
import json
from core.parser import parse_upload
from core.decryptor import decrypt_sheets
from ui.upload_widget import render_preview

DECR_SHEETS = "decr_sheets"
DECR_MAPPING = "decr_mapping"
DECR_RESULT = "decr_result"

def render() -> None:
    st.header("Дешифровка данных")

    uploaded_masked = st.file_uploader(
        "Замаскированный файл (xlsx или csv)",
        type=["xlsx", "csv"],
        key="decr_file",
    )
    uploaded_json = st.file_uploader(
        "Файл маппинга (JSON)",
        type=["json"],
        key="decr_json",
    )

    if uploaded_masked and uploaded_json:
        sheets = parse_upload(uploaded_masked)
        mapping = _load_mapping(uploaded_json)
        if mapping is None:
            st.error("Невалидный файл маппинга")
            return

        st.subheader("Замаскированные данные")
        render_preview(sheets)

        if st.button("Дешифровать", type="primary"):
            result = decrypt_sheets(sheets, mapping)
            st.session_state[DECR_RESULT] = result

    if DECR_RESULT in st.session_state:
        st.subheader("Восстановленные данные")
        render_preview(st.session_state[DECR_RESULT])
        # download button here
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `st.button` + base64 href for downloads | `st.download_button` | Streamlit ~1.2.0 | Native support, no JS needed |
| `openpyxl` for write | `xlsxwriter` via `pd.ExcelWriter` | Standard practice | Better performance, already in requirements.txt |

## Open Questions

1. **Decrypted text case: normalized uppercase or original case?**
   - What we know: `mapping["text"]` keys are normalized (uppercase, no quotes). Inversion gives `{pseudonym: UPPERCASE_NORMALIZED}`. Original display case (e.g., "ООО Альфа") is not stored in the mapping — only its normalized form "ООО АЛЬФА" is the key.
   - What's unclear: Is "ООО АЛЬФА" acceptable in the decrypted output, or does the user expect "ООО Альфа"?
   - Recommendation: Accept normalized uppercase for v1 — the data is semantically correct and users can reformat. Document this behavior. If case recovery is required, the masker must be extended to store `{norm_key: (pseudonym, original_display)}`, which is a v2 change.

2. **Decryption page: stateful (session_state) or stateless (recompute on every rerun)?**
   - What we know: Masking page uses a stage machine with `st.rerun()`. Decryption is simpler.
   - What's unclear: Should decryption result persist in session state across reruns, or recompute each time the button is clicked?
   - Recommendation: Store result in `st.session_state[DECR_RESULT]` keyed to uploaded files — simple pattern matching masking page without full stage machine overhead.

3. **File name for decrypted download**
   - What we know: CONTEXT.md marks naming as Claude's Discretion.
   - Recommendation: Use `{masked_filename_without_ext}_decrypted.xlsx`. If the user uploaded `data_masked.xlsx`, output is `data_masked_decrypted.xlsx`.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.3.5 |
| Config file | `pytest.ini` (testpaths = tests) |
| Quick run command | `python -m pytest tests/test_decryptor.py -q` |
| Full suite command | `python -m pytest tests/ -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| OUT-01 | `generate_masked_xlsx()` returns valid xlsx bytes with all sheets | unit | `pytest tests/test_output.py::test_masked_xlsx_has_all_sheets -x` | ❌ Wave 0 |
| OUT-02 | `generate_mapping_json()` returns valid JSON with text+numeric keys | unit | `pytest tests/test_output.py::test_mapping_json_format -x` | ❌ Wave 0 |
| OUT-03 | `generate_mapping_xlsx()` returns xlsx with two sheets | unit | `pytest tests/test_output.py::test_mapping_xlsx_two_sheets -x` | ❌ Wave 0 |
| OUT-04 | Statistics already verified in test_masker.py::test_stats_counts | unit | `pytest tests/test_masker.py::test_stats_counts -x` | ✅ |
| DECR-01 | `load_mapping_from_upload()` parses valid JSON; returns None on invalid | unit | `pytest tests/test_decryptor.py::test_load_mapping_valid -x` | ❌ Wave 0 |
| DECR-02 | `decrypt_sheets()` restores masked text values to normalized originals | unit | `pytest tests/test_decryptor.py::test_decrypt_text_values -x` | ❌ Wave 0 |
| DECR-02 | `decrypt_sheets()` restores masked numeric values via inverse coefficient | unit | `pytest tests/test_decryptor.py::test_decrypt_numeric_values -x` | ❌ Wave 0 |
| DECR-02 | NaN cells remain NaN after decryption | unit | `pytest tests/test_decryptor.py::test_decrypt_nan_passthrough -x` | ❌ Wave 0 |
| DECR-03 | Unknown text values (LLM-added) pass through unchanged | unit | `pytest tests/test_decryptor.py::test_decrypt_unknown_values_passthrough -x` | ❌ Wave 0 |
| DECR-03 | Unknown columns (LLM-added) pass through unchanged | unit | `pytest tests/test_decryptor.py::test_decrypt_unknown_columns_passthrough -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_decryptor.py tests/test_output.py -q`
- **Per wave merge:** `python -m pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_decryptor.py` — covers DECR-01, DECR-02, DECR-03
- [ ] `tests/test_output.py` — covers OUT-01, OUT-02, OUT-03
- [ ] `core/decryptor.py` — decryption engine (mirrors masker.py structure)

---

## Sources

### Primary (HIGH confidence)
- Codebase inspection: `core/masker.py`, `core/state_keys.py`, `core/parser.py`, `views/masking.py`, `views/decryption.py`, `ui/upload_widget.py`, `requirements.txt`, `pytest.ini` — all read directly
- `.planning/phases/03-output-decryption/03-CONTEXT.md` — locked decisions
- `.planning/REQUIREMENTS.md` — requirement definitions

### Secondary (MEDIUM confidence)
- Streamlit `st.download_button` API — well-established since Streamlit 1.2, behavior verified through project's use of Streamlit 1.55.0
- `pd.ExcelWriter` with `engine='xlsxwriter'` — standard pandas pattern, xlsxwriter 3.2.9 in requirements.txt

### Tertiary (LOW confidence)
- None — all critical claims verified from codebase or locked decisions

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages already installed, versions pinned in requirements.txt
- Architecture: HIGH — integration points explicitly defined in CONTEXT.md and verified in codebase
- Pitfalls: HIGH — pitfalls 2-5 verified from Streamlit/pandas docs and codebase patterns; pitfall 1 (case loss) confirmed by reading masker.py normalization logic

**Research date:** 2026-03-20
**Valid until:** 2026-04-20 (stable stack, no fast-moving dependencies)
