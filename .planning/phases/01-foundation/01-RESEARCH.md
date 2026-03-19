# Phase 1: Foundation - Research

**Researched:** 2026-03-19
**Domain:** Streamlit file upload, Excel/CSV parsing, session state architecture, Russian-language UI
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **App structure:** Sidebar with navigation — Маскирование / Дешифровка (two modes)
- **Sidebar:** Navigation only, no additional information
- **Masking flow:** Step-by-step: Step 1 (Upload) → Step 2 (Column selection) → Step 3 (Results + download)
- **Step navigation:** Back/Next buttons between steps
- **Preview:** `st.tabs` with sheet names for multi-sheet Excel files
- **Preview rows:** 20 rows per sheet
- **No file metadata:** No sheet/row count display — show tabs with tables directly
- **Empty sheets:** Skip silently (do not show in tabs)
- **Unsupported formats:** Readable Russian message — "Поддерживаются только файлы xlsx и csv"
- **Corrupt files:** Error message — "Не удалось прочитать файл"
- **Theme:** Light (светлая тема)
- **Page title:** "Enigma — Шифрование данных для LLM"
- **Layout:** `wide` layout for tables with 30+ columns
- **Tech stack:** Streamlit + Python, openpyxl, pandas — fixed

### Claude's Discretion

- File size limit (determine based on VM RAM)
- Handling files with a single sheet (don't show tabs if there is only one sheet)
- Design of Back/Next buttons and step indicator

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| LOAD-01 | User can upload Excel file (xlsx) with multiple sheets | `pd.read_excel(..., sheet_name=None, engine='openpyxl')` returns `dict[str, DataFrame]`; covered by STACK.md patterns |
| LOAD-02 | User can upload CSV file | `pd.read_csv(io.BytesIO(bytes_data))` — single DataFrame, wrap in dict for uniform interface |
| LOAD-03 | System preserves file structure (all sheets, columns, row order) | Store `dict[sheet_name, DataFrame]` in `st.session_state["sheets"]`; preserve sheet order via `pd.read_excel` which uses openpyxl sheet order |
| UI-01 | Interface fully in Russian language | All `st.title`, `st.header`, `st.button`, `st.file_uploader`, `st.error`, `st.tabs` labels are Russian strings — no library needed |
| UI-02 | Stateless — server stores nothing, data only in Streamlit session | `st.session_state` is per-WebSocket-connection; `io.BytesIO` for all in-memory output; never write to disk |
</phase_requirements>

---

## Summary

Phase 1 builds the complete application skeleton: file upload with Excel/CSV parsing, multi-sheet preview with tabs, a three-step navigation flow, and the session state architecture that all subsequent phases will use. The research corpus (STACK.md, ARCHITECTURE.md, PITFALLS.md) is comprehensive and directly applicable — no additional external research was needed.

The core challenge is establishing the correct Streamlit session state pattern from day one. Because Streamlit reruns the full script on every widget interaction, any state not stored in `st.session_state` is lost. The architecture decision to use a `stage` enum in session state (`uploaded → columns_selected → masked`) gates UI sections and prevents spurious reruns from resetting user progress.

The secondary challenge is the file parsing contract. Phase 2 (masking) and Phase 3 (decryption) both depend on `st.session_state["sheets"]` holding a `dict[sheet_name, DataFrame]` with original column order and dtypes intact. Phase 1 must establish this contract and document the exact keys used in session state.

**Primary recommendation:** Build `core/parser.py` first, establish the session state key contract as constants in a `core/state_keys.py` module, then build the Streamlit UI around it. This keeps business logic testable in isolation.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.11+ | Runtime | pandas 3.0.1 hard requirement; 3.12 is the sweet spot |
| Streamlit | 1.55.0 | UI framework | Only mature option for Python data web apps; stateless-by-default; `st.tabs`, `st.file_uploader`, `st.session_state` all available |
| pandas | 3.0.1 | DataFrame operations, Excel/CSV reading | `read_excel(sheet_name=None)` returns all sheets as dict; Copy-on-Write default in 3.0 prevents silent mutations |
| openpyxl | 3.1.5 | Excel engine used by pandas | Required by pandas; handles multi-sheet xlsx; preserves sheet order |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| numpy | 2.x (pandas dep) | Numeric operations | Automatically available; no separate install needed |
| io (stdlib) | — | BytesIO for in-memory file handling | Always — never write to disk |
| re (stdlib) | — | Cyrillic text normalization | For normalizing company names before dict keying |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| openpyxl | python-calamine | calamine is ~3x faster for read but write-only not supported; not worth it for Phase 1 |
| pandas read_excel | openpyxl directly | pandas gives cleaner DataFrame interface with dtype inference; openpyxl needed only for write-back in later phases |

**Installation:**
```bash
uv venv .venv
source .venv/bin/activate
uv pip install streamlit==1.55.0 pandas==3.0.1 openpyxl==3.1.5 xlsxwriter==3.2.9
```

**requirements.txt:**
```
streamlit==1.55.0
pandas==3.0.1
openpyxl==3.1.5
xlsxwriter==3.2.9
```

---

## Architecture Patterns

### Recommended Project Structure

```
enigma/
├── app.py                  # Streamlit entry point: page config, sidebar navigation
├── pages/
│   ├── 01_mask.py          # Masking flow: Step 1 (upload) → Step 2 (columns) → Step 3 (download)
│   └── 02_decrypt.py       # Decryption flow (Phase 3)
├── core/
│   ├── state_keys.py       # Constants for all session_state keys — prevents typos
│   ├── parser.py           # Parse uploaded bytes → dict[sheet_name, DataFrame]
│   ├── heuristics.py       # Column sensitivity scoring (Phase 2)
│   ├── masker.py           # Masking engine (Phase 2)
│   ├── mapping.py          # Mapping dict helpers (Phase 2)
│   └── assembler.py        # BytesIO output assembly (Phase 3)
├── ui/
│   ├── upload_widget.py    # Reusable upload + preview component
│   └── step_indicator.py   # Step 1/2/3 progress indicator
└── requirements.txt
```

### Pattern 1: Session State Stage Machine

**What:** A `stage` key in `st.session_state` drives which UI sections are rendered. Transitions happen only on explicit user actions (button clicks), not on reruns.

**When to use:** Always — prevents state loss on Streamlit reruns triggered by widget interactions.

**Example:**
```python
# core/state_keys.py — Source: ARCHITECTURE.md pattern
SHEETS = "sheets"
RAW_BYTES = "raw_bytes"
STAGE = "stage"
FILE_NAME = "file_name"

STAGE_UPLOADED = "uploaded"
STAGE_COLUMNS = "columns_selected"
STAGE_MASKED = "masked"
```

```python
# pages/01_mask.py
import streamlit as st
from core.state_keys import STAGE, STAGE_UPLOADED, SHEETS
from core.parser import parse_upload

uploaded_file = st.file_uploader(
    "Загрузите файл Excel или CSV",
    type=["xlsx", "csv"],
    label_visibility="collapsed",
)

if uploaded_file and STAGE not in st.session_state:
    try:
        sheets = parse_upload(uploaded_file)
        st.session_state[SHEETS] = sheets
        st.session_state[STAGE] = STAGE_UPLOADED
        st.rerun()
    except ValueError as e:
        st.error(str(e))
```

### Pattern 2: parse_upload Contract

**What:** `parse_upload(uploaded_file)` reads bytes once, returns `dict[str, pd.DataFrame]`. Empty sheets are filtered. CSV is wrapped in a single-key dict. All errors raise `ValueError` with Russian messages.

**When to use:** This is the single entry point for all file parsing; called once, result stored in session state.

**Example:**
```python
# core/parser.py
import io
import pandas as pd

def parse_upload(uploaded_file) -> dict[str, pd.DataFrame]:
    """
    Returns dict[sheet_name, DataFrame].
    Raises ValueError with Russian message on format or parse errors.
    """
    file_bytes = uploaded_file.read()
    name = uploaded_file.name.lower()

    if name.endswith(".xlsx"):
        return _parse_excel(file_bytes)
    elif name.endswith(".csv"):
        return _parse_csv(file_bytes)
    else:
        raise ValueError("Поддерживаются только файлы xlsx и csv")

def _parse_excel(file_bytes: bytes) -> dict[str, pd.DataFrame]:
    try:
        sheets = pd.read_excel(
            io.BytesIO(file_bytes),
            sheet_name=None,
            engine="openpyxl",
        )
    except Exception:
        raise ValueError("Не удалось прочитать файл")
    # Filter empty sheets silently
    return {name: df for name, df in sheets.items() if not df.empty}

def _parse_csv(file_bytes: bytes) -> dict[str, pd.DataFrame]:
    try:
        df = pd.read_csv(io.BytesIO(file_bytes))
    except Exception:
        raise ValueError("Не удалось прочитать файл")
    return {"Лист1": df}
```

### Pattern 3: Multi-Sheet Preview with st.tabs

**What:** If more than one non-empty sheet, render `st.tabs` with sheet names. If exactly one sheet, render `st.dataframe` directly (no tabs). Show first 20 rows.

**When to use:** Step 1 preview after successful file parse.

**Example:**
```python
# ui/upload_widget.py
import streamlit as st

def render_preview(sheets: dict):
    sheet_names = list(sheets.keys())
    if len(sheet_names) == 1:
        st.dataframe(sheets[sheet_names[0]].head(20), use_container_width=True)
    else:
        tabs = st.tabs(sheet_names)
        for tab, name in zip(tabs, sheet_names):
            with tab:
                st.dataframe(sheets[name].head(20), use_container_width=True)
```

### Pattern 4: BytesIO for In-Memory File Handling

**What:** Never write to disk. Use `io.BytesIO` for all file reads and writes. Call `.seek(0)` before passing to `st.download_button`.

**When to use:** All file output operations.

**Example:**
```python
# Source: ARCHITECTURE.md Pattern 3
import io
import openpyxl

def workbook_to_bytes(wb: openpyxl.Workbook) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()
```

### Pattern 5: Page Config (app.py)

**What:** Set page title, layout, and theme in `app.py` using `st.set_page_config`. This must be the first Streamlit call.

**Example:**
```python
# app.py
import streamlit as st

st.set_page_config(
    page_title="Enigma — Шифрование данных для LLM",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Sidebar navigation
st.sidebar.title("Enigma")
page = st.sidebar.radio(
    "Режим",
    ["Маскирование", "Дешифровка"],
    label_visibility="collapsed",
)
```

**Note on light theme:** Streamlit theme is set in `.streamlit/config.toml`, not in Python code:
```toml
# .streamlit/config.toml
[theme]
base = "light"
```

### Anti-Patterns to Avoid

- **Global variables for state:** `MAPPING = {}` at module level leaks data between users. Always use `st.session_state`.
- **Writing temp files:** `wb.save("/tmp/output.xlsx")` creates race conditions. Always use `io.BytesIO`.
- **Reading uploaded_file.read() twice:** Second call returns empty bytes (cursor at end). Read once, store bytes in session state.
- **Triggering parsing on every rerun:** Guard with `if SHEETS not in st.session_state` before calling `parse_upload`.
- **Not calling buf.seek(0):** BytesIO at end of write position; `st.download_button` gets empty data.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Reading multi-sheet Excel | Manual openpyxl sheet iteration + DataFrame construction | `pd.read_excel(sheet_name=None)` | pandas handles column header detection, dtype inference, NaN handling automatically |
| CSV encoding detection | Custom encoding sniffer | `pd.read_csv` with default UTF-8; add `encoding='cp1251'` fallback for Russian Windows files | pandas handles the common cases; custom sniffers miss edge cases |
| In-memory file buffer | Temp file on disk | `io.BytesIO` | Zero-disk approach; no cleanup needed; no race conditions |
| Multi-page navigation | Custom URL routing | Streamlit native multi-page (`pages/` directory) | Streamlit handles routing, page titles, and sidebar links automatically |
| Step indicator | Custom HTML/CSS | Simple `st.progress` or `st.markdown` with step labels | Sufficient for MVP; avoids unsupported HTML injection risks |

**Key insight:** pandas + openpyxl together handle the full Excel round-trip including multi-sheet, dtype inference, and encoding. Building custom parsing adds risk without benefit.

---

## Common Pitfalls

### Pitfall 1: Streamlit Rerun Destroys Unpersisted State

**What goes wrong:** User uploads file, Streamlit parses it into a local variable, user clicks a tab — Streamlit reruns the script, local variable is gone, app resets to upload screen.

**Why it happens:** Streamlit reruns the full Python script on every widget interaction. Local variables do not persist between reruns.

**How to avoid:** Store ALL computed state in `st.session_state` immediately after computation. Check `if SHEETS not in st.session_state` before re-parsing. Use the stage machine pattern.

**Warning signs:** Clicking any UI element causes reset to upload screen.

### Pitfall 2: Reading uploaded_file Twice

**What goes wrong:** `parse_upload(uploaded_file)` calls `.read()` internally. If the caller also calls `.read()` or the function is called twice, the second call returns `b""`.

**Why it happens:** `st.UploadedFile` is a file-like object; `.read()` advances the cursor to the end.

**How to avoid:** In `parse_upload`, call `.read()` exactly once and pass `io.BytesIO(file_bytes)` to pandas. Store `file_bytes` in `st.session_state[RAW_BYTES]` for any subsequent needs.

**Warning signs:** `pd.read_excel` raises `BadZipFile` or returns empty DataFrame on the second parse attempt.

### Pitfall 3: CSV with Windows Cyrillic Encoding (cp1251)

**What goes wrong:** CSV exported from Russian Windows Excel uses cp1251 encoding. `pd.read_csv` defaults to UTF-8 and raises `UnicodeDecodeError`, or worse, silently produces garbled column names.

**Why it happens:** Russian corporate tools often default to cp1251 (Windows-1251) for CSV exports.

**How to avoid:** Wrap `pd.read_csv` in a try/except:
```python
def _parse_csv(file_bytes: bytes) -> dict[str, pd.DataFrame]:
    for encoding in ("utf-8", "cp1251", "utf-8-sig"):
        try:
            df = pd.read_csv(io.BytesIO(file_bytes), encoding=encoding)
            return {"Лист1": df}
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
    raise ValueError("Не удалось прочитать файл")
```

**Warning signs:** Column names appear as `?????` or encoding errors on CSV upload.

### Pitfall 4: openpyxl Memory on Large Files

**What goes wrong:** A 20 MB xlsx file with formatting causes openpyxl to consume ~1 GB RAM (50x multiplier), potentially OOM-killing the Streamlit process.

**Why it happens:** openpyxl default mode loads the full workbook object tree into memory.

**How to avoid:** Use `pd.read_excel` (not raw openpyxl) for data reading — pandas manages memory more carefully. Set `server.maxUploadSize = 50` in `.streamlit/config.toml` to cap input size. Install `lxml` for faster XML parsing.

**Warning signs:** Server returns 502, process killed for files >10 MB.

### Pitfall 5: Empty Sheet Handling

**What goes wrong:** `pd.read_excel(sheet_name=None)` returns empty DataFrames for blank sheets. If not filtered, `st.tabs` shows a tab for a blank sheet, and `st.dataframe` renders an empty table with a confusing empty state.

**Why it happens:** openpyxl preserves all sheets defined in the workbook including blank placeholder sheets.

**How to avoid:** Filter after parsing: `{name: df for name, df in sheets.items() if not df.empty}`. If ALL sheets are empty after filtering, raise `ValueError("Файл не содержит данных")`.

**Warning signs:** Tab with empty table appears for sheets that are blank in the original file.

### Pitfall 6: BytesIO seek(0) Missing

**What goes wrong:** `st.download_button(data=buf)` serves an empty file because the BytesIO cursor is at the end after writing.

**Why it happens:** After `wb.save(buf)` or `buf.write(...)`, the cursor is at the end of the buffer. Reading from the end returns empty bytes.

**How to avoid:** Always call `buf.seek(0)` before passing to `st.download_button` or returning `buf.read()`.

**Warning signs:** Downloaded file is 0 bytes or opens as corrupted.

---

## Code Examples

Verified patterns from STACK.md and ARCHITECTURE.md:

### Multi-Sheet Excel Read

```python
# Source: STACK.md "For multi-sheet Excel read"
import pandas as pd
import io

sheets = pd.read_excel(
    io.BytesIO(file_bytes),
    sheet_name=None,
    engine="openpyxl",
)
# Returns dict[str, DataFrame]; empty sheets filtered separately
```

### Session State Stage Gate

```python
# Source: ARCHITECTURE.md Pattern 1
if "sheets" not in st.session_state:
    # Show upload widget
    uploaded_file = st.file_uploader("Загрузите файл Excel или CSV", type=["xlsx", "csv"])
    if uploaded_file:
        ...
else:
    # Show preview and next steps
    render_preview(st.session_state["sheets"])
```

### CSV Encoding Fallback

```python
# Source: PITFALLS.md Pitfall 7 + cp1251 pattern
for encoding in ("utf-8", "cp1251", "utf-8-sig"):
    try:
        df = pd.read_csv(io.BytesIO(file_bytes), encoding=encoding)
        return {"Лист1": df}
    except (UnicodeDecodeError, pd.errors.ParserError):
        continue
raise ValueError("Не удалось прочитать файл")
```

### Page Config + Light Theme

```python
# app.py — must be first Streamlit call
st.set_page_config(
    page_title="Enigma — Шифрование данных для LLM",
    layout="wide",
    initial_sidebar_state="expanded",
)
```

```toml
# .streamlit/config.toml
[theme]
base = "light"

[server]
maxUploadSize = 50
headless = true
```

### st.tabs for Multi-Sheet Preview

```python
# Source: Streamlit docs / ARCHITECTURE.md
sheet_names = list(sheets.keys())
if len(sheet_names) == 1:
    st.dataframe(sheets[sheet_names[0]].head(20), use_container_width=True)
else:
    tabs = st.tabs(sheet_names)
    for tab, name in zip(tabs, sheet_names):
        with tab:
            st.dataframe(sheets[name].head(20), use_container_width=True)
```

### Error Handling Pattern

```python
# Russian error messages as specified
try:
    sheets = parse_upload(uploaded_file)
except ValueError as e:
    st.error(str(e))
    st.stop()
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `xlrd` for xlsx reading | `openpyxl` as pandas engine | xlrd 2.0 (2020) dropped xlsx support | xlrd raises `XLRDError` on any modern .xlsx — do not use |
| pandas 2.x with copy-on-write opt-in | pandas 3.0 with CoW as default | Feb 2026 (pandas 3.0.1) | Code written against 3.0 won't silently mutate DataFrames |
| `st.experimental_rerun()` | `st.rerun()` | Streamlit 1.27+ | Old name deprecated; use `st.rerun()` |
| `st.experimental_memo` | `st.cache_data` | Streamlit 1.18+ | `experimental_memo` removed in recent versions |

**Deprecated/outdated:**
- `xlrd`: Do not use — only reads legacy .xls format, raises `XLRDError` on .xlsx
- `st.experimental_rerun`: Renamed to `st.rerun()` in current Streamlit
- `st.experimental_memo`: Replaced by `st.cache_data`

---

## Open Questions

1. **File size limit for this VM**
   - What we know: VM is at 158.160.27.49; openpyxl has ~50x memory multiplier; typical files are 15–20 MB
   - What's unclear: Available RAM on the VM is not confirmed
   - Recommendation: Set `maxUploadSize = 50` MB as a safe default; validate during Phase 1 implementation by loading the real test file and monitoring RAM

2. **CSV separator auto-detection**
   - What we know: `pd.read_csv` defaults to comma; Russian Excel exports may use semicolon as separator
   - What's unclear: What separators appear in the target corporate files
   - Recommendation: Use `sep=None, engine='python'` in `pd.read_csv` to auto-detect separator, then fall back to explicit comma if that fails

3. **Back button behavior clearing state**
   - What we know: User can click "Back" to go from Step 2 to Step 1
   - What's unclear: Should "Back" clear only the current step's data or all downstream data?
   - Recommendation: "Back" to Step 1 should clear `st.session_state` entirely (reset to blank upload state) to avoid stale column selections referencing the previous file

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (not yet installed — see Wave 0) |
| Config file | none — Wave 0 creates `pytest.ini` |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| LOAD-01 | parse_upload returns dict[str, DataFrame] for xlsx with multiple sheets | unit | `pytest tests/test_parser.py::test_parse_excel_multisheet -x` | Wave 0 |
| LOAD-01 | Empty sheets are silently filtered from result | unit | `pytest tests/test_parser.py::test_empty_sheets_filtered -x` | Wave 0 |
| LOAD-02 | parse_upload returns single-key dict for CSV | unit | `pytest tests/test_parser.py::test_parse_csv -x` | Wave 0 |
| LOAD-02 | CSV with cp1251 encoding parses correctly | unit | `pytest tests/test_parser.py::test_parse_csv_cp1251 -x` | Wave 0 |
| LOAD-03 | Parsed sheets dict preserves column order from source file | unit | `pytest tests/test_parser.py::test_column_order_preserved -x` | Wave 0 |
| LOAD-03 | Parsed sheets dict preserves row order from source file | unit | `pytest tests/test_parser.py::test_row_order_preserved -x` | Wave 0 |
| UI-01 | All visible string literals are in Russian | manual | Visual inspection during development | N/A |
| UI-02 | Refresh clears session state — no data persists | manual | Open app, upload file, refresh, verify empty state | N/A |

### Sampling Rate

- **Per task commit:** `pytest tests/test_parser.py -x -q`
- **Per wave merge:** `pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/__init__.py` — empty init for test discovery
- [ ] `tests/test_parser.py` — covers LOAD-01, LOAD-02, LOAD-03
- [ ] `tests/conftest.py` — shared fixtures (sample xlsx bytes, sample csv bytes)
- [ ] `pytest.ini` — minimal config
- [ ] Framework install: `uv pip install pytest` — pytest not in requirements.txt yet

---

## Sources

### Primary (HIGH confidence)

- `.planning/research/STACK.md` — verified library versions, installation patterns, multi-sheet read/write code
- `.planning/research/ARCHITECTURE.md` — session state patterns, project structure, BytesIO pattern, anti-patterns
- `.planning/research/PITFALLS.md` — openpyxl memory, session state loss, file cursor pitfalls, Cyrillic encoding
- `.planning/phases/01-foundation/01-CONTEXT.md` — locked UI decisions, preview specs, error messages

### Secondary (MEDIUM confidence)

- `.planning/PROJECT.md` — product constraints, target data types, VM deployment details
- `.planning/REQUIREMENTS.md` — requirement definitions LOAD-01..03, UI-01..02

### Tertiary (LOW confidence)

- None — all findings backed by PRIMARY sources from prior research sessions

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified from PyPI in STACK.md (2026-03-19)
- Architecture: HIGH — patterns from ARCHITECTURE.md with Streamlit official doc citations
- Pitfalls: HIGH — sourced from openpyxl/pandas/Streamlit issue trackers and official docs

**Research date:** 2026-03-19
**Valid until:** 2026-04-18 (30 days — stable libraries)
