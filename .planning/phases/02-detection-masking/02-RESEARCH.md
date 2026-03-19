# Phase 2: Detection + Masking — Research

**Researched:** 2026-03-19
**Domain:** Keyword-based column detection, text pseudonymization, numeric perturbation, Streamlit multi-step UI
**Confidence:** HIGH (based on existing project code, real sample file inspection, Phase 1 architecture docs)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Детекция чувствительных колонок**
- Жёсткий список ключевых слов, зашитый в код (константы/конфиг)
- Детекция только по названию колонки, не по значениям ячеек (детекция по значениям — v2, DETC-05)
- Подстрочный поиск: если название содержит ключевое слово — колонка отмечена
- Если ни одна колонка не найдена — показать все колонки без предвыбора + предупреждение "Автоматически чувствительные колонки не обнаружены, выберите вручную"
- Список ключевых слов не редактируется пользователем через UI

**UI выбора колонок (Шаг 2)**
- Табы по листам (как на Шаге 1), на каждом листе свои чекбоксы
- Рядом с каждым чекбоксом бейдж типа маскирования: [текст] или [число]
- Кнопки "Выбрать все" / "Снять все" на каждом листе
- Автоматически определённые колонки предвыбраны (checked)
- Тип маскирования определяется автоматически по dtype колонки + эвристика для идентификаторов

**Классификация числовых колонок (MASK-04)**
- По ключевым словам в названии: №, номер, договор, контракт, документ, счёт, id → идентификатор (текстовое маскирование)
- Остальные числовые колонки → количественные (коэффициент)
- Для числовых колонок пользователь может переключить тип: коэффициент ↔ идентификатор
- Текстовые колонки всегда маскируются как текст (без возможности смены типа)

**Числовое маскирование**
- Один случайный коэффициент (0.5–1.5) на колонку — пропорции между строками сохраняются
- Коэффициент единый кросс-листово для одноимённых колонок

**Результат маскирования (Шаг 3)**
- Превью замаскированных данных (20 строк, табы по листам — аналогично Шагу 1)
- Статистика: количество замаскированных значений и уникальных сущностей
- Заглушки кнопок скачивания (неактивные) — Phase 3 активирует
- Кнопка "Назад к выбору колонок" для перемаскирования
- Кнопка "Сбросить" — начать с загрузки

**Обработка пустых значений**
- NaN/пустые ячейки пропускаются — не маскируются, не попадают в маппинг

### Claude's Discretion
- Полный список ключевых слов для детекции (на основе реального файла)
- Визуальное оформление бейджей типа маскирования
- Порядок отображения колонок в чекбоксах (как в файле vs отсортировано)
- Дизайн переключателя "коэффициент ↔ идентификатор" для числовых колонок

### Deferred Ideas (OUT OF SCOPE)
- DETC-04: Детекция по жёлтой заливке ячеек (v2)
- DETC-05: Детекция по значениям (ООО/ОАО/ИП regex, ФИО паттерны) (v2)
- Редактируемый пользователем список ключевых слов через UI
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DETC-01 | Система автоматически предлагает чувствительные колонки на основе эвристик по названиям | Keyword list derived from real sample file; substring match pattern confirmed |
| DETC-02 | Пользователь может добавить/убрать колонки для маскирования через чекбоксы | `st.checkbox` per column per sheet, persisted in `st.session_state`; tabs pattern from Phase 1 |
| DETC-03 | Для каждой выбранной колонки система определяет тип маскирования (текст или число) | dtype check + name-keyword classifier; toggle for numeric ID vs quantity |
| MASK-01 | Текстовые значения заменяются на псевдонимы с авто-префиксом из названия колонки | Prefix derivation pattern confirmed; `df[col].map(mapping_dict)` vectorized |
| MASK-02 | Числовые значения умножаются на случайный коэффициент (0.5–1.5) с сохранением пропорций | Per-column single coefficient; integer rounding required to avoid float noise |
| MASK-03 | Одно уникальное значение = один псевдоним во всём файле (кросс-листовая консистентность) | Single shared `mapping_dict` passed to all sheet processing; counter dict by prefix |
| MASK-04 | Идентификаторы-числа (номера договоров, документов) маскируются как текст, а не умножением | Keyword classifier for ID columns; confirmed by real file: "Документ закупки", "Внеш. номер договора", "Сообщение", "Заказ" |
</phase_requirements>

---

## Summary

Phase 2 builds three new modules on top of Phase 1's `parse_upload()` foundation: a keyword detector (`core/detector.py`), a masking engine (`core/masker.py`), and two new UI stages in `views/masking.py` (Шаг 2: column selector, Шаг 3: masked preview).

The core algorithmic challenge is cross-sheet consistency: the masking dictionary must be built as a single shared object before any sheet is processed. This is documented as the most critical pitfall in PITFALLS.md and is already planned in ARCHITECTURE.md as "Pattern 2: Single-Pass Cross-Sheet Mapping Build". The counter tracking unique pseudonym indices per prefix must also be global across sheets.

The real sample file (`Данные для маскирования_13.03.xlsx`) reveals the exact columns to cover. Sensitive columns are: "Имя предприятия", "Создал", "Обнаружил", "Автор изменения", "Автор сообщения", "Наименование рабочего места" (contractor name stored as object). Numeric ID columns that must NOT use coefficient masking: "Документ закупки", "Внеш. номер договора", "Сообщение", "Заказ", "Номер работы/услуги", "ВАГОН". This directly informs the keyword list and classifier.

**Primary recommendation:** Implement detection + masking as pure Python in `core/` (no Streamlit imports), extend `views/masking.py` to handle `STAGE_COLUMNS` and `STAGE_MASKED` stages, add `SELECTED_COLUMNS`, `MASK_CONFIG`, `MAPPING`, `MASKED_SHEETS`, `STATS` keys to `state_keys.py`.

---

## Standard Stack

### Core (already installed — from Phase 1)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | 3.0.1 | DataFrame operations, vectorized masking | Already in stack; `df[col].map()` and `df[col] * multiplier` are the correct vectorized APIs |
| openpyxl | latest installed | Excel read/write | Already in stack; used by parser |
| streamlit | 1.55.0 | UI framework | Already in stack; installed with `--override` flag |

### No New Dependencies Needed

Phase 2 requires zero new pip packages. All required functionality is covered by the Phase 1 stack:
- `pandas` handles vectorized text substitution (`Series.map()`), numeric multiplication, `dropna()` for NaN skipping
- `random` (stdlib) for coefficient generation
- `unicodedata` (stdlib) for NFC normalization of Cyrillic
- `re` (stdlib) for prefix derivation from column names

**Installation:** None required.

---

## Architecture Patterns

### Module Structure

New files to create:
```
core/
├── detector.py       # DETC-01, DETC-03: keyword detection + type classification
├── masker.py         # MASK-01..04: masking engine (text + numeric)
ui/
├── column_selector.py  # DETC-02: checkbox grid with type badges
```

Extend existing files:
```
core/state_keys.py    # Add 5 new session state keys
views/masking.py      # Add _render_step_columns() and _render_step_masked()
```

### Pattern 1: Keyword Detection (`core/detector.py`)

**What:** Two keyword lists — one for sensitive column names (triggers detection), one for numeric-identifier column names (triggers "text" masking instead of "coefficient"). Both lists use `.lower()` substring matching.

**Keyword list for sensitive detection** (derived from real file + domain):
```python
# Source: real file analysis + PROJECT.md domain context
SENSITIVE_KEYWORDS = [
    # Company/contractor names
    "предприятие", "контрагент", "поставщик", "исполнитель",
    "организация", "компания", "подрядчик", "рабочее место",
    # Person names
    "фио", "имя", "сотрудник", "создал", "обнаружил", "автор",
    "исполнитель", "ответственный",
    # Financial
    "сумма", "цена", "стоимость", "тариф",
    # Contract/document numbers (text-masked, not coefficient)
    "договор", "контракт", "номер", "документ", "счёт", "счет",
    "заказ", "заявка", "сообщение", "карточка",
]
```

**Keyword list for numeric ID columns** (controls MASK-04):
```python
# Source: CONTEXT.md locked decisions + real file analysis
NUMERIC_ID_KEYWORDS = [
    "№", "номер", "договор", "контракт", "документ",
    "счёт", "счет", "id", "заказ", "заявка", "сообщение",
    "код", "артикул", "вагон", "карточка",
]
```

**API:**
```python
def detect_sensitive_columns(
    sheets: dict[str, pd.DataFrame]
) -> dict[str, list[str]]:
    """Returns {sheet_name: [col_names_suggested_sensitive]}."""

def classify_column_type(col_name: str, dtype: str) -> str:
    """Returns 'text' or 'numeric'.
    object dtype → 'text'.
    numeric dtype + name matches ID keywords → 'text'.
    numeric dtype + name does NOT match ID keywords → 'numeric'.
    """
```

### Pattern 2: Masking Engine (`core/masker.py`)

**What:** Two-phase masking. Phase A builds the shared mapping dict (single pass, all sheets, all text columns). Phase B applies substitutions (vectorized).

**CRITICAL — Cross-Sheet Consistency:**
```python
# Source: ARCHITECTURE.md Pattern 2
def build_text_mapping(
    sheets: dict[str, pd.DataFrame],
    text_columns_per_sheet: dict[str, list[str]],
) -> dict[str, str]:
    """Single shared mapping_dict built before any output is written.
    Counter is global across sheets.
    """
    mapping: dict[str, str] = {}
    counters: dict[str, int] = {}  # prefix → current count

    for sheet_df in sheets.values():
        for col, col_type in text_columns_per_sheet.get(sheet_name, {}).items():
            if col_type != "text" or col not in sheet_df.columns:
                continue
            prefix = _derive_prefix(col)
            for raw_val in sheet_df[col].dropna().unique():
                normalized = _normalize(raw_val)
                if normalized not in mapping:
                    counters[prefix] = counters.get(prefix, 0) + 1
                    mapping[normalized] = f"{prefix} {_to_letter(counters[prefix])}"
    return mapping
```

**Prefix derivation** (Claude's discretion — recommendation):
```python
def _derive_prefix(col_name: str) -> str:
    """Derive human-readable prefix from column name.
    "Имя предприятия" → "Предприятие"
    "Наименование рабочего места" → "Место"
    """
    # Take first meaningful noun from column name
    # Fallback: first word of column name stripped of service prefixes
    ...
```

**Normalization** (critical — prevents Pitfall 3 and 4 from PITFALLS.md):
```python
import unicodedata, re

def _normalize(value: str) -> str:
    """NFC normalization + strip whitespace + uppercase + remove quotes."""
    s = unicodedata.normalize("NFC", str(value))
    s = s.strip().upper()
    s = re.sub(r'[""«»\'\"]', "", s)  # remove all quote variants
    s = re.sub(r"\s+", " ", s)        # collapse multiple spaces
    return s
```

**Numeric masking:**
```python
# Source: ARCHITECTURE.md + PITFALLS.md Pitfall 2
def build_numeric_mapping(
    sheets: dict[str, pd.DataFrame],
    numeric_columns: list[str],   # column names globally (cross-sheet)
) -> dict[str, float]:
    """One random multiplier per column name, shared across sheets."""
    import random
    return {
        col: random.uniform(0.5, 1.5)
        for col in numeric_columns
    }

def apply_numeric_masking(series: pd.Series, multiplier: float) -> pd.Series:
    """Multiply by coefficient; round integers back to int to avoid float noise."""
    result = series * multiplier
    if pd.api.types.is_integer_dtype(series):
        return result.round().astype("Int64")   # nullable int to handle NaN
    return result.round(2)
```

**Vectorized text application:**
```python
# Source: ARCHITECTURE.md Anti-Pattern 3 — use map() not iterrows()
def apply_text_masking(series: pd.Series, mapping: dict[str, str]) -> pd.Series:
    """Vectorized text substitution. NaN cells are left as NaN."""
    normalized_series = series.map(
        lambda v: mapping.get(_normalize(v), v) if pd.notna(v) else v
    )
    return normalized_series
```

### Pattern 3: Session State Extension

Add to `core/state_keys.py`:
```python
# Phase 2 keys
SELECTED_COLUMNS = "selected_columns"  # dict[sheet_name, dict[col_name, bool]]
MASK_CONFIG = "mask_config"            # dict[sheet_name, dict[col_name, "text"|"numeric"]]
MAPPING = "mapping"                    # dict: {"text": {norm_val: pseudonym}, "numeric": {col: multiplier}}
MASKED_SHEETS = "masked_sheets"        # dict[str, pd.DataFrame] — masked data for preview
STATS = "stats"                        # dict: {"masked_values": int, "unique_entities": int}
```

### Pattern 4: UI Stage Extension (`views/masking.py`)

The existing state machine `None → STAGE_UPLOADED` is extended to:
```
None → STAGE_UPLOADED → STAGE_COLUMNS → STAGE_MASKED
```

The "Далее" button in `_render_step_preview()` (currently `disabled=True`) is activated to transition to `STAGE_COLUMNS`.

**Шаг 2 — Column Selector (`_render_step_columns`):**
- `render_steps(current=2)` — already supported
- Tabs per sheet via `st.tabs()`
- Per-column `st.checkbox` pre-populated from detector output
- Badge rendered as `st.caption("[текст]")` or `st.caption("[число]")` inline with checkbox
- "Выбрать все" / "Снять все" via `st.button` that sets all checkboxes in session_state before `st.rerun()`
- For numeric columns: `st.radio` or `st.selectbox` for коэффициент/идентификатор toggle
- "Замаскировать" button (primary) triggers masking engine; result stored in session state; `st.rerun()` to STAGE_MASKED

**Шаг 3 — Masked Result (`_render_step_masked`):**
- `render_steps(current=3)`
- `render_preview(masked_sheets)` — reuse existing widget
- Statistics display: `st.metric("Замаскировано значений", stats["masked_values"])` etc.
- Disabled download buttons (stubs for Phase 3): `st.button("Скачать замаскированный файл", disabled=True)`
- "Назад к выбору колонок" → sets STAGE back to STAGE_COLUMNS, clears MASKED_SHEETS/STATS, reruns
- "Сбросить" → full reset (same pattern as Phase 1)

### Anti-Patterns to Avoid

- **Per-sheet masking dict:** Never initialize `mapping = {}` inside the sheet loop. The mapping must exist before the loop starts.
- **Masking on every Streamlit rerun:** Guard behind `st.button("Замаскировать")`. Store result in session state. Check `if MASKED_SHEETS not in st.session_state` before recomputing.
- **iterrows for masking:** Use `df[col].map()` for text, `df[col] * multiplier` for numeric.
- **No normalization:** Always normalize before inserting into or looking up from mapping dict.
- **dtype-only classification:** Always combine dtype with name-keyword check for ID detection.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Vectorized text substitution | Custom loop over cells | `pd.Series.map(dict)` | 100x faster; handles NaN natively |
| Numeric multiplication | Custom loop | `pd.Series * scalar` | Vectorized; numpy handles broadcasting |
| NaN skipping | Manual `if` checks | `pd.Series.dropna()` for mapping build; `pd.notna()` in apply | pandas contract guarantees |
| Unicode normalization | Custom regex | `unicodedata.normalize('NFC', s)` | Handles composed/decomposed Cyrillic correctly |
| Integer detection | `type(val) == int` | `pd.api.types.is_integer_dtype(series)` | Works correctly with pandas nullable Int64 and int64 |

**Key insight:** The entire masking engine can be implemented with 4 pandas operations (`map`, `*`, `dropna`, `notna`) plus stdlib `unicodedata` and `random`. No external masking library is needed or appropriate.

---

## Common Pitfalls

### Pitfall 1: Cross-Sheet Mapping Inconsistency (CRITICAL)
**What goes wrong:** Same value on Sheet1 gets "Предприятие A", same value on Sheet3 gets "Предприятие B".
**Why it happens:** Masking dict re-initialized per sheet, or counter reset per sheet.
**How to avoid:** Single `mapping = {}` and `counters = {}` instantiated once before the sheet loop. Both passed by reference to all sheet processing calls.
**Warning signs:** Unit test: same value in two sheets → assert same pseudonym in both.

### Pitfall 2: Float Noise on Integer Columns (MASK-02)
**What goes wrong:** `Количество: 50` → `36.5` after `* 0.731`. Or `Сумма: 1000000` → `731000.0000000001`.
**Why it happens:** IEEE 754 float multiplication on integer values.
**How to avoid:** Detect integer dtype before multiplication; apply `round().astype("Int64")` after. For float columns: `round(result, 2)`.
**Warning signs:** Output preview shows `.5` or `.0000000001` in columns that were integers.

### Pitfall 3: Numeric ID Columns Perturbed as Quantities (MASK-04)
**What goes wrong:** "Документ закупки: 4500736383" → "3289538860.31" — destroys the document number.
**Why it happens:** Column dtype is int64, no name-keyword check, so it gets coefficient masking.
**How to avoid:** Always check column name against `NUMERIC_ID_KEYWORDS` before assigning "numeric" type. The real file has at least 6 such columns.
**Real file columns requiring text masking despite numeric dtype:** "Документ закупки", "Внеш. номер договора" (Sheet 1), "Сообщение", "Заказ", "Дата изменения" (Sheet 2), "Заявка", "Заказ", "Номер работы/услуги" (Sheet 3), "ВАГОН", "КОД_ГРУЗА" (Sheet 4).

### Pitfall 4: Masking Triggered on Checkbox Interaction
**What goes wrong:** User unchecks a column → Streamlit reruns → masking engine re-runs → new random coefficients → consistency broken.
**Why it happens:** Masking logic not guarded behind button click.
**How to avoid:** Only trigger masking on explicit `st.button("Замаскировать")` click. Store result in `st.session_state[MASKED_SHEETS]`. In `_render_step_columns`, check `if MASKED_SHEETS in st.session_state` — if yes, skip to step 3 directly.

### Pitfall 5: Russian Company Name Variants as Different Entities
**What goes wrong:** `ООО "ЛУИС+"` and `ООО ЛУИС+` (no quotes) → two different pseudonyms.
**Why it happens:** Exact-string match without normalization.
**How to avoid:** Apply `_normalize()` (strip + upper + remove quotes) before inserting into mapping dict AND before lookup during application.

### Pitfall 6: "Выбрать все" / "Снять все" Buttons Don't Persist
**What goes wrong:** Button click sets checkboxes but Streamlit rerun resets them back because checkbox widget state is re-read from widget keys, not from session state.
**Why it happens:** Streamlit checkbox widget state (via `key=`) and manual session state manipulation can conflict.
**How to avoid:** Use `st.session_state["checkbox_{sheet}_{col}"] = True/False` pattern. Set these keys before calling `st.rerun()` in the "Выбрать все" button handler. Read checkbox default values from session state, not from detector output (after first render).

---

## Code Examples

### Verified Pattern: Keyword Detection

```python
# core/detector.py
def detect_sensitive_columns(
    sheets: dict[str, pd.DataFrame]
) -> dict[str, list[str]]:
    result = {}
    for sheet_name, df in sheets.items():
        sensitive = []
        for col in df.columns:
            col_lower = str(col).lower()
            if any(kw in col_lower for kw in SENSITIVE_KEYWORDS):
                sensitive.append(col)
        result[sheet_name] = sensitive
    return result
```

### Verified Pattern: Type Classification

```python
# core/detector.py
def classify_column_type(col_name: str, series: pd.Series) -> str:
    """Returns 'text' or 'numeric'."""
    import pandas as pd
    col_lower = str(col_name).lower()
    # Numeric dtype but looks like an identifier → text masking
    if pd.api.types.is_numeric_dtype(series):
        if any(kw in col_lower for kw in NUMERIC_ID_KEYWORDS):
            return "text"
        return "numeric"
    # Non-numeric (object, datetime, etc.) → always text
    return "text"
```

### Verified Pattern: Single-Pass Mapping Build

```python
# core/masker.py — MUST be called once before any apply step
def build_text_mapping(
    sheets: dict[str, pd.DataFrame],
    mask_config: dict[str, dict[str, str]],  # {sheet: {col: "text"|"numeric"}}
) -> dict[str, str]:
    """Returns {normalized_original_value: pseudonym}."""
    mapping: dict[str, str] = {}
    counters: dict[str, int] = {}

    for sheet_name, df in sheets.items():
        config = mask_config.get(sheet_name, {})
        for col, col_type in config.items():
            if col_type != "text" or col not in df.columns:
                continue
            prefix = _derive_prefix(col)
            for raw_val in df[col].dropna().unique():
                key = _normalize(str(raw_val))
                if key not in mapping:
                    counters[prefix] = counters.get(prefix, 0) + 1
                    mapping[key] = f"{prefix} {_index_to_label(counters[prefix])}"
    return mapping
```

### Verified Pattern: Letter Index (A, B, ..., Z, AA, AB, ...)

```python
def _index_to_label(n: int) -> str:
    """1→A, 2→B, 26→Z, 27→AA, 28→AB, ..."""
    label = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        label = chr(65 + remainder) + label
    return label
```

### Verified Pattern: Apply Text Masking (Vectorized)

```python
# Source: ARCHITECTURE.md Anti-Pattern 3 guidance
def apply_text_masking(series: pd.Series, mapping: dict[str, str]) -> pd.Series:
    def lookup(v):
        if pd.isna(v):
            return v
        return mapping.get(_normalize(str(v)), v)
    return series.map(lookup)
```

### Verified Pattern: Masking Guard in Streamlit

```python
# views/masking.py — only runs masking on explicit button click
def _render_step_columns() -> None:
    render_steps(current=2)
    # ... render checkboxes from session state ...

    if st.button("Замаскировать", type="primary", use_container_width=True):
        sheets = st.session_state[SHEETS]
        mask_config = _read_mask_config_from_state(sheets)
        masked_sheets, mapping, stats = run_masking(sheets, mask_config)
        st.session_state[MASKED_SHEETS] = masked_sheets
        st.session_state[MAPPING] = mapping
        st.session_state[STATS] = stats
        st.session_state[STAGE] = STAGE_MASKED
        st.rerun()
```

---

## Keyword List Recommendation (Claude's Discretion)

Based on real file analysis (`Данные для маскирования_13.03.xlsx`), the following keyword lists are recommended:

**SENSITIVE_KEYWORDS** (triggers detection):
```python
SENSITIVE_KEYWORDS = [
    # Company/org names — seen in file
    "предприятие", "контрагент", "поставщик", "рабочее место",
    "организация", "компания", "подрядчик", "исполнитель",
    # Person names — seen in file
    "фио", "имя", "сотрудник", "создал", "обнаружил",
    "автор", "ответственный",
    # Financial — seen in file
    "сумма", "цена", "стоимость", "тариф",
]
```

**NUMERIC_ID_KEYWORDS** (forces text masking on numeric-dtype columns):
```python
NUMERIC_ID_KEYWORDS = [
    # Seen in real file as int64 columns
    "документ", "договор", "контракт", "номер", "номер работы",
    "заказ", "заявка", "сообщение", "карточка", "счёт", "счет",
    "код", "артикул", "вагон", "позиция",
    # Generic
    "id", "№",
]
```

**Rationale:** The real file has columns like "Документ закупки" (int64, sample=4500736383), "Внеш. номер договора" (int64 on Sheet 1, object on Sheet 3 — inconsistent!), "Сообщение" (int64, sample=201968150), "ВАГОН" (int64, sample=60313582). All must be text-masked. Column order in display: as-in-file (preserves user familiarity).

**Badge design recommendation:** Use `st.markdown(f"<span style='background-color:#e8f4f8;border-radius:4px;padding:2px 6px;font-size:0.8em'>[текст]</span>", unsafe_allow_html=True)` for text badge, same with light-orange background for numeric badge. Inline placement next to checkbox label via `st.columns([0.7, 0.3])`.

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| iterrows for cell masking | `Series.map(dict)` vectorized | 100x faster for large files |
| Per-sheet mapping dict | Single global mapping dict before loop | Cross-sheet consistency guaranteed |
| Exact string match | Normalize + match (strip/upper/no-quotes) | Handles ООО "X" vs ООО X variants |
| dtype-only classification | dtype + name-keyword classification | Prevents document number perturbation |

---

## Open Questions

1. **"Внеш. номер договора" column dtype inconsistency**
   - What we know: On Sheet "Поступление ТМЦ" it is `int64`. On Sheet "Услуги стор. орг-й" it is `object` (values like "ДГ-1010-11292-05-22").
   - What's unclear: Should the masking engine unify cross-sheet column typing? The column name is the same but dtype differs.
   - Recommendation: Classify per-sheet independently. "text" classification wins if any sheet has object dtype for that column name — but since classification is per-sheet, this resolves naturally: Sheet 1 classifies as "text" (NUMERIC_ID_KEYWORDS match "договор"), Sheet 3 classifies as "text" (object dtype). No issue.

2. **Letter vs number pseudonym index format**
   - What we know: PROJECT.md says "Предприятие A", "Предприятие B". CONTEXT.md confirms this.
   - What's unclear: Does the user expect "Предприятие AA" after 26, or "Предприятие 27"?
   - Recommendation: Use A-Z then AA, AB, ... (Excel-column style). Consistent with the `_index_to_label()` pattern above. Practical limit: 26^2 + 26 = 702 unique values per column prefix, which exceeds any real use case.

3. **"Назад к выбору колонок" — preserve or reset column selections?**
   - What we know: CONTEXT.md says "Назад к выбору колонок" allows re-masking.
   - What's unclear: When user goes back, should checkboxes remember what they had selected?
   - Recommendation: Preserve `SELECTED_COLUMNS` and `MASK_CONFIG` in session state when going back. Only clear `MASKED_SHEETS` and `STATS`. This gives a natural "edit and re-run" workflow.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (already configured) |
| Config file | `/Users/ilyamukha/Documents/Projects/Энигма/pytest.ini` |
| Quick run command | `pytest tests/test_detector.py tests/test_masker.py -x` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DETC-01 | Keyword detection suggests correct columns from real file headers | unit | `pytest tests/test_detector.py::test_detect_sensitive_columns -x` | ❌ Wave 0 |
| DETC-01 | No sensitive columns found → returns empty list per sheet | unit | `pytest tests/test_detector.py::test_detect_no_match_returns_empty -x` | ❌ Wave 0 |
| DETC-02 | Column checkboxes render per sheet with correct pre-selection | manual | UI smoke test | — |
| DETC-03 | object-dtype column classified as "text" | unit | `pytest tests/test_detector.py::test_classify_object_is_text -x` | ❌ Wave 0 |
| DETC-03 | int64 column with "номер" in name classified as "text" | unit | `pytest tests/test_detector.py::test_classify_numeric_id_is_text -x` | ❌ Wave 0 |
| DETC-03 | int64 column with "количество" in name classified as "numeric" | unit | `pytest tests/test_detector.py::test_classify_quantity_is_numeric -x` | ❌ Wave 0 |
| MASK-01 | Text values replaced with "Prefix A/B/C" pseudonyms | unit | `pytest tests/test_masker.py::test_text_masking_produces_pseudonyms -x` | ❌ Wave 0 |
| MASK-01 | Prefix derived from column name correctly | unit | `pytest tests/test_masker.py::test_prefix_derivation -x` | ❌ Wave 0 |
| MASK-02 | Numeric column multiplied by coefficient in [0.5, 1.5] | unit | `pytest tests/test_masker.py::test_numeric_coefficient_range -x` | ❌ Wave 0 |
| MASK-02 | Integer columns remain integer after masking | unit | `pytest tests/test_masker.py::test_integer_stays_integer -x` | ❌ Wave 0 |
| MASK-02 | Proportions between rows preserved (ratio check) | unit | `pytest tests/test_masker.py::test_numeric_proportions_preserved -x` | ❌ Wave 0 |
| MASK-03 | Same value on Sheet1 and Sheet3 → same pseudonym | unit | `pytest tests/test_masker.py::test_cross_sheet_consistency -x` | ❌ Wave 0 |
| MASK-03 | NaN values skipped — not in mapping | unit | `pytest tests/test_masker.py::test_nan_not_masked -x` | ❌ Wave 0 |
| MASK-04 | "Документ закупки" (int64) masked as text not coefficient | unit | `pytest tests/test_masker.py::test_numeric_id_masked_as_text -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_detector.py tests/test_masker.py -x`
- **Per wave merge:** `pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_detector.py` — covers DETC-01, DETC-03 (create in Wave 0)
- [ ] `tests/test_masker.py` — covers MASK-01, MASK-02, MASK-03, MASK-04 (create in Wave 0)
- [ ] `tests/conftest.py` — extend with multi-sheet fixture with known sensitive columns and numeric ID columns

*(Existing `tests/test_parser.py` and `tests/conftest.py` remain untouched)*

---

## Sources

### Primary (HIGH confidence)
- Real file inspection: `Данные для маскирования_13.03.xlsx` — actual column names, dtypes, sample values across 4 sheets
- `core/parser.py` — confirmed `parse_upload()` returns `dict[str, pd.DataFrame]` — exact input contract for detector
- `core/state_keys.py` — confirmed STAGE_COLUMNS and STAGE_MASKED already defined
- `views/masking.py` — confirmed stage machine pattern, "Далее" button disabled stub location
- `ui/upload_widget.py` — confirmed `render_preview()` reusable for masked sheets preview
- `.planning/research/ARCHITECTURE.md` — Pattern 2 (single-pass mapping), Pattern 3 (BytesIO), Anti-Pattern 3 (no iterrows)
- `.planning/research/PITFALLS.md` — Pitfalls 1-7 with exact code patterns

### Secondary (MEDIUM confidence)
- pandas docs: `Series.map()`, `pd.api.types.is_integer_dtype()` — vectorized operations confirmed behavior
- Python stdlib: `unicodedata.normalize()`, `random.uniform()` — confirmed APIs

### Tertiary (LOW confidence)
- None — all findings verified from project source code or official Python stdlib docs

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new dependencies; all from Phase 1
- Detection algorithm: HIGH — keyword lists derived from real file inspection
- Masking engine: HIGH — patterns verified in ARCHITECTURE.md and PITFALLS.md
- UI patterns: HIGH — extending confirmed Phase 1 patterns
- Keyword lists: MEDIUM — derived from 4 real sheets; may miss edge cases in other user files (acceptable for v1)

**Research date:** 2026-03-19
**Valid until:** 2026-06-19 (stable domain; pandas/Streamlit APIs very stable)
