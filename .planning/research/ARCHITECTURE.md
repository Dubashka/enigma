# Architecture Research

**Domain:** Data masking / pseudonymization Streamlit app
**Researched:** 2026-03-19
**Confidence:** HIGH

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        UI Layer (Streamlit)                      │
├──────────────┬──────────────┬──────────────┬────────────────────┤
│  Upload &    │  Column      │  Masking     │  Decrypt           │
│  Preview     │  Selector    │  Results &   │  Tab               │
│  Widget      │  Checkboxes  │  Download    │                    │
└──────┬───────┴──────┬───────┴──────┬───────┴──────┬─────────────┘
       │              │              │              │
       ▼              ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Session State (st.session_state)               │
│  raw_workbook | column_meta | mask_config | masked_bytes |       │
│  mapping_dict | stats                                            │
└───────┬──────────────────────────────────────────┬──────────────┘
        │                                          │
        ▼                                          ▼
┌───────────────────────┐              ┌──────────────────────────┐
│   File Parsing Layer  │              │   Reverse Decrypt Layer  │
│  (openpyxl + pandas)  │              │  (mapping JSON + xlsx)   │
└───────────┬───────────┘              └──────────────────────────┘
            │
            ▼
┌───────────────────────────────────────────────────────────────┐
│                      Masking Engine                            │
│  ┌─────────────────────┐    ┌──────────────────────────────┐  │
│  │  Text Pseudonymizer │    │  Numeric Perturbation Engine │  │
│  │  (prefix + counter) │    │  (per-column multiplier)     │  │
│  └──────────┬──────────┘    └──────────────┬───────────────┘  │
│             │                              │                   │
│             └──────────────┬───────────────┘                   │
│                            ▼                                   │
│                  ┌──────────────────┐                          │
│                  │   Mapping Store  │                          │
│                  │  (in-memory dict)│                          │
│                  └──────────────────┘                          │
└───────────────────────────────────────────────────────────────┘
            │
            ▼
┌───────────────────────────────────────────────────────────────┐
│                    Output Assembly Layer                        │
│   masked Excel (BytesIO) | mapping JSON (str) | mapping Excel  │
└───────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| File Parsing Layer | Read uploaded bytes into workbook + per-sheet DataFrames; detect column types; infer sensitive columns | `openpyxl.load_workbook(BytesIO(...))` + `pd.read_excel` per sheet |
| Column Selector UI | Present checkboxes pre-populated from heuristic; let user override sensitive/not columns and masking type (text vs numeric) | `st.checkbox` grid or `st.multiselect`, persisted in `st.session_state` |
| Masking Engine - Text Pseudonymizer | Build and maintain a `{original_value: pseudonym}` dict; assign new pseudonym using column-derived prefix + incrementing counter; consistent cross-sheet | Pure Python dict, single pass over all sheets before writing output |
| Masking Engine - Numeric Perturbation | Choose a per-column random multiplier in [0.5, 1.5]; apply it uniformly to every cell in that column | numpy or plain Python, multiplier stored in mapping for reversibility |
| Mapping Store (in-memory) | Single source of truth for the session; holds text lookup table + numeric multipliers; lives in `st.session_state` | `dict`: `{"text": {"ООО Ромашка": "Контрагент A", ...}, "numeric": {"col_name": 1.23, ...}}` |
| Output Assembly Layer | Serialize masked workbook to `BytesIO` (preserving sheet structure); serialize mapping to JSON string and to Excel file | `openpyxl` write to `BytesIO`, `json.dumps`, `pd.ExcelWriter` to `BytesIO` |
| Reverse Decrypt Layer | Accept masked file + mapping JSON; reconstruct original values by reversing the lookup table (text) and dividing by multiplier (numeric); leave new columns/rows untouched | Invert mapping dict; walk cells in masked workbook |
| Session State Bus | Central store isolating each user's data from other concurrent users; clears on page refresh | `st.session_state` — Streamlit isolates this per browser tab/WebSocket connection |

## Recommended Project Structure

```
enigma/
├── app.py                  # Streamlit entry point, page routing
├── pages/
│   ├── 01_mask.py          # Masking flow (upload → configure → download)
│   └── 02_decrypt.py       # Decryption flow (upload masked + mapping → download)
├── core/
│   ├── parser.py           # File Parsing Layer: read Excel/CSV into sheets dict
│   ├── heuristics.py       # Column sensitivity heuristics (name patterns, dtype)
│   ├── masker.py           # Masking Engine: text pseudonymizer + numeric perturber
│   ├── mapping.py          # Mapping Store helpers: build, serialize, deserialize
│   └── assembler.py        # Output Assembly: masked workbook → BytesIO, mapping export
├── ui/
│   ├── upload_widget.py    # Reusable upload + preview component
│   ├── column_selector.py  # Column checkbox grid component
│   └── stats_display.py    # Post-masking statistics component
└── requirements.txt
```

### Structure Rationale

- **core/**: All business logic is pure Python with no Streamlit imports. This makes each module unit-testable in isolation and callable from either the mask or decrypt page without duplication.
- **pages/**: Streamlit's native multi-page routing. Each page imports from `core/` and manages its own UI flow. Session state passes data between pages without requiring re-upload.
- **ui/**: Reusable widget helpers that encapsulate `st.*` calls. Keeps pages thin and declarative.

## Architectural Patterns

### Pattern 1: Session State as the In-Memory Database

**What:** All transient data (uploaded workbook bytes, parsed DataFrames, masking config, mapping dict, output bytes) lives exclusively in `st.session_state`. Nothing is written to disk except Python's own temp files during `st.file_uploader` handling.

**When to use:** Always in this app — it is the stateless guarantee. Session state is isolated per WebSocket connection, so two concurrent users never share data.

**Trade-offs:** Data is lost on page refresh (intentional — stateless by design). Large files (tens of thousands of rows) consume server RAM proportional to concurrent active sessions. One session = one user's full file in RAM.

**Example:**
```python
# parser.py output is immediately stored in session state
if uploaded_file is not None:
    wb_bytes = uploaded_file.read()
    st.session_state["raw_bytes"] = wb_bytes
    st.session_state["sheets"] = parse_workbook(wb_bytes)
    st.session_state["column_meta"] = infer_column_types(st.session_state["sheets"])
```

### Pattern 2: Single-Pass Cross-Sheet Mapping Build

**What:** Before writing any output, the masking engine makes one full pass over ALL sheets and ALL selected text columns to populate the mapping dict. Only then does it write masked output. This guarantees that the same value (e.g., "ООО Ромашка") appearing on sheet 1 and sheet 4 gets the same pseudonym.

**When to use:** Required whenever cross-sheet consistency is a hard requirement.

**Trade-offs:** Requires holding all sheets in memory simultaneously. For files with 4 sheets × 37 columns × 50k rows this is still manageable (pandas DataFrames at ~100MB max for this scale).

**Example:**
```python
def build_mapping(sheets: dict[str, pd.DataFrame], text_columns: list[str]) -> dict:
    mapping = {}
    counters = {}  # per-column prefix counter
    for sheet_df in sheets.values():
        for col in text_columns:
            if col not in sheet_df.columns:
                continue
            prefix = derive_prefix(col)
            for val in sheet_df[col].dropna().unique():
                if val not in mapping:
                    counters[prefix] = counters.get(prefix, 0) + 1
                    mapping[val] = f"{prefix} {num_to_letter(counters[prefix])}"
    return mapping
```

### Pattern 3: BytesIO Round-Trip for Zero-Disk Output

**What:** All file outputs (masked Excel, mapping Excel) are assembled into `io.BytesIO` objects in memory and passed directly to `st.download_button(data=...)`. No temp files are written to the server filesystem.

**When to use:** Mandatory for a stateless no-server-storage architecture.

**Trade-offs:** Output files must fit in RAM. For this domain (Excel files up to ~50k rows) this is not a concern. Avoids file cleanup logic and race conditions from temp files.

**Example:**
```python
def workbook_to_bytes(wb: openpyxl.Workbook) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()

st.download_button("Скачать замаскированный файл", data=workbook_to_bytes(masked_wb), ...)
```

## Data Flow

### Masking Flow

```
User uploads file (st.file_uploader)
    |
    v
File Parsing Layer
  openpyxl.load_workbook(BytesIO) → sheets dict + column metadata
    |
    v
Session State: store raw_bytes, sheets, column_meta
    |
    v
Heuristics Engine
  Scores columns by name patterns + dtype → suggested sensitive set
    |
    v
Column Selector UI (user confirms/adjusts checkboxes)
    |
    v
Session State: store mask_config {col: "text"|"numeric"|"skip"}
    |
    v
Masking Engine
  Pass 1: walk all sheets, all text columns → build mapping dict
  Pass 2: walk all sheets, apply substitutions + numeric multipliers
    |
    v
Session State: store mapping_dict, stats
    |
    v
Output Assembly Layer
  masked workbook → BytesIO
  mapping dict   → JSON string + Excel BytesIO
    |
    v
UI: show stats, st.download_button x3
```

### Decryption Flow

```
User uploads masked file + mapping JSON (st.file_uploader x2)
    |
    v
File Parsing Layer: parse masked workbook into sheets dict
Mapping Layer:      json.loads(mapping_json) → inverted lookup dict
    |
    v
Reverse Decrypt Layer
  For each sheet, for each cell:
    if cell value in inverted_text_map → replace with original
    if column in numeric_map → divide by stored multiplier
    else → leave untouched (new columns/rows from LLM pass through)
    |
    v
Output Assembly Layer: restored workbook → BytesIO
    |
    v
UI: st.download_button for restored file
```

### State Management

```
st.session_state  (per-user, per-tab, cleared on refresh)
    |
    ├── raw_bytes:      bytes          # original uploaded file
    ├── sheets:         dict[str, df]  # parsed DataFrames per sheet
    ├── column_meta:    dict           # dtype + heuristic score per column
    ├── mask_config:    dict           # col → "text"|"numeric"|"skip"
    ├── mapping_dict:   dict           # {"text": {...}, "numeric": {...}}
    ├── masked_bytes:   bytes          # output workbook bytes
    ├── mapping_json:   str            # serialized mapping
    └── stats:          dict           # counts for display
```

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1-10 concurrent users | Current design works. Single VM, no changes needed. |
| 10-50 concurrent users | Monitor RAM. Each session holds one full Excel in memory. 50 sessions × ~50MB = ~2.5GB. VM should have 4-8GB RAM. |
| 50+ concurrent users | Add `st.cache_data` for parsing (not masking — masking is stateful). Consider session cleanup via `st.session_state` size limits. Or move to async processing with a job queue. |

### Scaling Priorities

1. **First bottleneck:** RAM from concurrent sessions each holding file bytes + DataFrames. Mitigation: store only DataFrames in session state, not raw bytes after parsing.
2. **Second bottleneck:** CPU from large file masking (50k rows × 37 columns). Mitigation: use pandas vectorized operations instead of cell-by-cell loops; avoid iterrows.

## Anti-Patterns

### Anti-Pattern 1: Global Variables or Module-Level State

**What people do:** Store the mapping dict or parsed DataFrames as module-level Python variables (e.g., `MAPPING = {}` at the top of masker.py).

**Why it's wrong:** Module-level state is shared across ALL concurrent Streamlit sessions. User A's data leaks into User B's masking run. This is a critical privacy violation given the app handles sensitive corporate data.

**Do this instead:** Always store mutable state in `st.session_state`. Pass state explicitly as function arguments through core/ modules.

### Anti-Pattern 2: Writing Temp Files to Disk

**What people do:** `wb.save("/tmp/masked_output.xlsx")` then `open("/tmp/masked_output.xlsx", "rb").read()`.

**Why it's wrong:** Creates race conditions between concurrent users writing to the same path. Requires cleanup logic. Violates the "server stores nothing" contract.

**Do this instead:** Always use `io.BytesIO()` — write to BytesIO, seek(0), pass directly to `st.download_button`.

### Anti-Pattern 3: iterrows for Masking Large Files

**What people do:** Loop through every row and column with `df.iterrows()` or nested for-loops to apply masking.

**Why it's wrong:** For 50k rows × 15 text columns, this produces 750k Python loop iterations. Pandas vectorized operations are 10-100x faster.

**Do this instead:** Use `df[col].map(mapping_dict)` for text substitution (vectorized). Use `df[col] * multiplier` for numeric perturbation (vectorized). Fall back to `df[col].apply(...)` only when map() is insufficient.

### Anti-Pattern 4: Rebuilding Mapping on Each Rerun

**What people do:** Run the masking engine every time Streamlit reruns the script (e.g., on every checkbox interaction).

**Why it's wrong:** Streamlit reruns the full script on every widget interaction. If masking is triggered unconditionally, a 50k-row file gets re-masked dozens of times during column selection. Worse, a new random multiplier gets chosen each rerun, breaking consistency.

**Do this instead:** Guard masking behind an explicit button click. Store the result in `st.session_state` and check `if "masked_bytes" not in st.session_state` before recomputing. Use `st.button("Замаскировать")` as the sole trigger.

## Integration Points

### External Services

None. This app is intentionally self-contained with no external API calls.

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| UI pages ↔ core/ | Direct function calls, data passed as arguments | core/ modules must have zero Streamlit imports |
| pages/ ↔ session state | Read/write `st.session_state` keys | Use constants for key names to avoid typos |
| masker.py ↔ mapping.py | masker.py calls mapping.py to build/read the dict | mapping.py owns serialization (JSON/Excel) |
| assembler.py ↔ masker.py | assembler receives masked DataFrames + original workbook structure; reassembles | Sheet order, merged cells, column widths from original must be preserved via openpyxl |

## Sources

- [Streamlit Architecture and Execution Concepts](https://docs.streamlit.io/develop/concepts/architecture) — HIGH confidence
- [Streamlit Session State Reference](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state) — HIGH confidence
- [Streamlit Client-Server Architecture](https://docs.streamlit.io/develop/concepts/architecture/architecture) — HIGH confidence
- [Microsoft Presidio Pseudonymization Patterns](https://microsoft.github.io/presidio/samples/python/pseudonymization/) — MEDIUM confidence
- [Consistent Cross-Table Pseudonymization (IRI)](https://www.iri.com/blog/data-protection/consistent-cross-table-data-pseudonymization/) — MEDIUM confidence
- [Streamlit Community: Session State Isolation for Concurrent Users](https://discuss.streamlit.io/t/streamlit-session-states-in-users-simultaneous-activity/35996) — MEDIUM confidence
- [Data Masking Pipeline Architecture (Pipeline Mastery)](https://pipelinemastery.io/data-masking-and-anonymization/) — MEDIUM confidence

---
*Architecture research for: Энигма — Streamlit data masking app*
*Researched: 2026-03-19*
