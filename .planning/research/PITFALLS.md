# Pitfalls Research

**Domain:** Data masking / pseudonymization app for industrial Excel data (Streamlit + Python)
**Researched:** 2026-03-19
**Confidence:** HIGH (domain-specific pitfalls derived from confirmed technical constraints)

---

## Critical Pitfalls

### Pitfall 1: Inconsistent Cross-Sheet Masking — Same Value Gets Different Pseudonyms

**What goes wrong:**
"ООО ЛУИС+" appears on Sheet1 as "Предприятие A" but on Sheet3 as "Предприятие B". When the user sends the masked file to an LLM, the model cannot infer that these two entities are the same, breaking any cross-sheet analysis (e.g., matching purchase orders to invoices).

**Why it happens:**
The masking dictionary is built per-sheet. Each sheet initializes a fresh counter for the prefix, so the first new value on each sheet gets index A regardless of global state. This happens when developers loop over sheets independently and initialize a `dict` inside each loop iteration.

**How to avoid:**
Build a single global masking dictionary before processing any sheet. Pass the same dictionary object (by reference) into every sheet processing function. The dictionary maps `(column_semantic_type, original_value)` → `pseudonym`. Counter state for each prefix must also be global.

```python
# WRONG — fresh dict per sheet
for sheet in workbook.sheetnames:
    masking_map = {}
    process_sheet(sheet, masking_map)

# CORRECT — single shared dict
masking_map = {}
for sheet in workbook.sheetnames:
    process_sheet(sheet, masking_map)
```

**Warning signs:**
- Unit test: same value in two sheets → different pseudonyms in output
- Mapping file has the same original value listed twice with different pseudonyms
- LLM responses reference "two different suppliers" that are actually one

**Phase to address:** Core masking engine (Phase 1 / foundation phase)

---

### Pitfall 2: Numeric Perturbation Destroys Integer Semantics and Creates Impossible Values

**What goes wrong:**
A quantity column "Количество" has integer values (e.g., 50 units). After multiplying by a float coefficient like 0.73, the result is 36.5 — a fractional unit count that is semantically impossible. Worse, contract sums stored as integers become floats with floating-point noise (e.g., 1000000 × 0.731 = 731000.0000000001), and when written back to Excel the cell displays `731000.0000000001` instead of `731000`.

**Why it happens:**
Python float multiplication introduces IEEE 754 representation errors. The project spec says "multiply by random coefficient 0.5–1.5" but doesn't differentiate between integer quantities vs. float prices vs. integer IDs (which should not be perturbed at all).

**How to avoid:**
- Detect column dtype before perturbation: integer columns → apply perturbation then `round()` back to int; float financial columns → use Python `Decimal` for multiplication or `round(result, 2)` to avoid noise.
- Never perturb columns that are numeric IDs (contract numbers, item codes) — these should be treated as text for masking, not numeric perturbation.
- Apply a single random coefficient per numeric column (not per cell) to preserve row-to-row ratios as stated in the spec.

**Warning signs:**
- Output Excel shows `.0000000001` suffixes on round numbers
- Integer quantities become decimals
- Ratio between masked values differs from ratio between original values (coefficient accidentally applied per-row with different seeds)

**Phase to address:** Core masking engine (Phase 1), with explicit dtype classification sub-task

---

### Pitfall 3: Reverse Mapping Failure Due to Whitespace and Encoding Normalization

**What goes wrong:**
During masking, "ООО \"ЛУИС+\"" is stored in the mapping as the key. During reverse decryption, the LLM output returns "ООО \"ЛУИС+\" " (trailing space) or uses a visually identical but different Unicode character (e.g., no-break space U+00A0, or a different quote style). The exact string lookup fails silently — the cell is left with the pseudonym instead of being restored, and the user doesn't notice.

**Why it happens:**
LLMs often reformat text: they trim/add spaces, normalize quotes, or produce Unicode variants (curly quotes, en-dashes). The reverse mapping uses exact string equality on the pseudonym as the lookup key. Any mismatch causes silent non-decryption.

**How to avoid:**
- Normalize all keys and lookup values before comparison: `value.strip().lower()` for case-insensitive pseudonyms, or apply `unicodedata.normalize('NFC', value)` to handle composed/decomposed Unicode equivalents.
- When building the reverse map (pseudonym → original), also build a normalized variant: `normalized_pseudonym → original`.
- During decryption, always normalize the candidate value before lookup.
- Log and surface any cells where a value looks like a pseudonym pattern but cannot be found in the map.

**Warning signs:**
- Spot-check: reverse-decrypt a just-masked file — any cells that weren't restored indicate this bug
- Log count of "unmatched pseudonym patterns" during decryption; any non-zero count is a warning
- User reports that some values weren't restored after decryption

**Phase to address:** Masking engine + decryption engine (Phase 1 and decryption phase)

---

### Pitfall 4: Russian Company Name Variants Treated as Different Entities

**What goes wrong:**
"ООО \"СТРОНГ-ФИЛЬТР\"" and "ООО СТРОНГ-ФИЛЬТР" (with and without quotes) are treated as two distinct companies and get two different pseudonyms. Similarly, "ОАО ЛУКОЙЛ" and "оао лукойл" get different pseudonyms. The LLM receives a masked file with two "Предприятие X" variants that are actually the same supplier.

**Why it happens:**
Russian industrial data is notoriously inconsistent: legal forms appear before or after the name, quotes are optional, all-caps vs. mixed case, full legal form vs. abbreviation (Общество с ограниченной ответственностью vs. ООО). A naive exact-match dictionary doesn't normalize these variants.

**How to avoid:**
- For the initial v1 (MVP), apply lightweight normalization before dictionary keying: strip outer whitespace, collapse multiple spaces, convert to uppercase, strip surrounding quotes and guillemets (« »).
- Do NOT attempt full legal form normalization in v1 — it adds complexity without proportional benefit. MVP normalization: `re.sub(r'[""«»\"]', '', value).strip().upper()`.
- Document clearly that the normalization is shallow; edge cases will remain.
- In a later phase, consider optional fuzzy matching (e.g., using `rapidfuzz`) to group near-identical names, but flag this as a UX choice requiring user confirmation before merging.

**Warning signs:**
- Mapping file has >1 entry for what looks like the same company name
- User reports: "I see two pseudonyms for the same supplier"
- High pseudonym count relative to expected number of unique suppliers

**Phase to address:** Masking engine (Phase 1), with normalization as an explicit design decision

---

### Pitfall 5: Streamlit Session State Lost on Page Interaction, Destroying In-Progress Mask Job

**What goes wrong:**
User uploads a large Excel file (10k+ rows, 4 sheets), selects columns to mask, clicks a checkbox to adjust the column selection — Streamlit reruns the entire script and the processed `masking_map` dictionary stored in a local variable is gone. User must re-upload and reprocess.

**Why it happens:**
Streamlit reruns the full script on every widget interaction. Any Python variable not stored in `st.session_state` is lost. Developers unfamiliar with Streamlit assume that variables set earlier in the script persist across reruns — they do not.

**How to avoid:**
- Store ALL computed state in `st.session_state`: the loaded workbook (or parsed DataFrames), the masking map, column detection results, processing status, and the masked output BytesIO buffer.
- Use a state machine pattern: `st.session_state['stage']` = `'uploaded' | 'columns_selected' | 'masked'`. Each stage gating the display of the next UI section.
- Never re-read from the uploaded file object after storing parsed data — the `UploadedFile` object itself survives reruns (Streamlit keeps it in widget state), but the parsed DataFrame does not unless you store it.

**Warning signs:**
- Clicking any checkbox causes the app to reset to the upload screen
- Processing indicators flash and disappear
- `st.session_state` inspection shows empty dict after interaction

**Phase to address:** Streamlit UI architecture (Phase 1 / app structure), must be designed before building any processing logic

---

### Pitfall 6: openpyxl Memory Explosion on Multi-Sheet Files with Rich Formatting

**What goes wrong:**
Loading a 15–20 MB Excel file with 4 sheets, heavy formatting (colors, borders, merged cells) causes openpyxl to consume 500 MB–1 GB of RAM in default mode. On the target VM (158.160.27.49) this may cause the server process to be OOM-killed, resulting in a 502 error from the user's perspective.

**Why it happens:**
openpyxl's default mode loads the entire workbook into memory at approximately 50x the file size. A 20 MB file = ~1 GB RAM. The project spec mentions files with "dozens of thousands of rows" — at 37 columns × 30,000 rows × 4 sheets, this is easily a 10–20 MB file.

**How to avoid:**
- Use `pandas.read_excel(..., engine='openpyxl')` for reading data (pandas handles chunking internally).
- For writing, use openpyxl's write-only mode when possible, or re-use the original workbook object and modify cells in-place rather than building a new workbook from scratch.
- Install `lxml` as the XML parser: `pip install lxml`. openpyxl uses it automatically and it is significantly faster and more memory-efficient than Python's built-in xml.
- Cap file upload size in Streamlit config: `server.maxUploadSize = 50` (MB). This prevents pathological inputs.
- Process one sheet at a time rather than loading all sheets simultaneously.

**Warning signs:**
- VM RAM usage spikes to near-capacity during file processing
- Streamlit returns "Connection error" or 502 on large file uploads
- Processing time exceeds 30 seconds for files that should take 3–5 seconds

**Phase to address:** Infrastructure / performance (Phase 1 or dedicated performance phase before production deployment)

---

### Pitfall 7: Mixed Data Type Columns — Numbers Stored as Strings, Strings Stored as Numbers

**What goes wrong:**
Column "Сумма договора" has mostly numeric values but some cells contain "Н/Д" (not available) or "договорная" (negotiable pricing). pandas infers the column as `object` dtype. The masking logic checks `if dtype == float: perturb_numerically` but the check fails — the numeric values are never perturbed. Or vice versa: a "Номер договора" column contains values like "12345" which pandas reads as `int64`, and the numeric perturbation code multiplies the contract number by 0.8 — destroying semantic meaning.

**Why it happens:**
Industrial Excel data is dirty. Mixed-type columns are common. pandas dtype inference is conservative: one non-numeric value in a numeric column makes the whole column `object`. Contract numbers look numeric but are identifiers, not quantities.

**How to avoid:**
- Auto-detection of "sensitive column type" must be semantic (based on column name keywords), not just dtype-based.
- Build a column classifier: columns whose names match keywords like "сумма", "цена", "стоимость", "расход" → numeric masking. Columns matching "номер договора", "код", "артикул", "ID" → text masking even if values are numeric.
- For mixed-type columns detected as object: attempt numeric conversion cell-by-cell; perturb cells that convert successfully, leave non-numeric cells as-is.
- Always let the user override auto-detection via the UI checkboxes.

**Warning signs:**
- Contract numbers in output are non-integer (e.g., "24691.2")
- Columns with "Н/Д" values lose their non-numeric cells entirely
- Auto-detection suggests a contract number column for "numeric" masking

**Phase to address:** Column auto-detection logic (Phase 1), verified with the real sample file

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Per-sheet masking dict instead of global | Simpler initial implementation | Cross-sheet consistency broken | Never — fix in Phase 1 |
| Exact string match for reverse mapping | Simple to implement | Silent decryption failures on LLM-edited text | MVP only; add normalization before first real-user release |
| Single random coefficient for all numeric columns | One line of code | Quantities and prices use same coefficient — misleading if user knows the multiplier | Never; use per-column coefficient |
| Loading entire workbook into memory | Simple openpyxl API | OOM on files >10 MB | Never for production; add lxml + size cap |
| dtype-based column classification only | Quick to implement | Contract numbers get perturbed numerically | Never; always combine with name-based heuristics |
| No input normalization for Cyrillic | Saves 10 lines of code | Same company gets two pseudonyms due to case/quote variants | Never; add .strip().upper() from day 1 |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| openpyxl + pandas | Using `wb = openpyxl.load_workbook(file)` then `pd.DataFrame(ws.values)` — loses column headers and dtypes | Use `pd.read_excel(file, sheet_name=None, engine='openpyxl')` to get all sheets as a dict of DataFrames |
| Streamlit `st.file_uploader` | Reading `uploaded_file.read()` multiple times — second read returns empty bytes (file cursor at end) | Call `.read()` once, store bytes in `st.session_state`, use `io.BytesIO(bytes_data)` for subsequent reads |
| openpyxl write-back | Modifying values but not preserving cell number formats — dates become serial numbers, currencies lose formatting | Copy `cell.number_format` from source cell when writing masked values |
| JSON mapping file | Using Python dict keys that are not JSON-serializable (e.g., numpy int64, pandas Timestamp) | Convert all keys to native Python types before `json.dump()` |
| Excel download in Streamlit | Using `st.download_button` with a BytesIO that has been read to end | Always call `buffer.seek(0)` before passing to `st.download_button` |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Cell-by-cell iteration with openpyxl | Processing takes 60+ seconds for 10k rows | Use pandas vectorized operations for data transformation; only use openpyxl for read/write | >5,000 rows |
| Storing full DataFrame in `st.session_state` for multiple large sheets | RAM grows with each user session; server slows for concurrent users | Store only the masking_map and file bytes; re-derive DataFrames from bytes on demand | >3 concurrent users or >20 MB files |
| Re-parsing workbook on every Streamlit rerun | 3–5 second delay on every checkbox click | Parse once, store result in `st.session_state['parsed_data']` | Immediately noticeable |
| Building reverse lookup by iterating forward map on every decryption | O(n) lookup per cell, very slow for large files | Pre-build reverse_map = {v: k for k, v in masking_map.items()} once at decryption start | >10,000 unique masked values |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Writing temp files to `/tmp` with predictable names | Another user on the same VM reads another user's data | Use `tempfile.NamedTemporaryFile()` (generates unique name) and always delete after download |
| Storing masking_map in Streamlit `st.session_state` without cleanup | Previous user's mapping survives if session is shared (e.g., behind a shared reverse proxy without session isolation) | Add "New session / clear data" button that explicitly calls `st.session_state.clear()` |
| Logging original sensitive values to console/file for debugging | Sensitive industrial data in server logs | Never log cell values; only log column names, row counts, and pseudonym counts |
| The mapping JSON file contains both original and pseudonym values | If mapping file is intercepted, full de-anonymization is possible | Document clearly that the mapping file is the "key" and must be stored securely by the user; add a warning in the UI |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No preview of what will be masked before running masking | User runs masking, sees wrong columns masked, must start over | Show a summary table of detected columns with type (text/numeric) before masking; allow checkbox override |
| Download button appears before processing is complete | User downloads empty or partial file | Use `st.spinner` during processing; only render download buttons after processing state is confirmed in session_state |
| Mapping file named "mapping.json" generically | User has 3 mapping files and can't tell which goes with which | Name output files after the input filename: `{original_name}_masked.xlsx`, `{original_name}_mapping.json` |
| No feedback on decryption completeness | User doesn't know if all values were restored | Show "X values restored, Y values not matched" after decryption |
| Column auto-detection suggests wrong columns | Industrial data has unusual column names; auto-detection based on generic PII patterns fails | Use a Russia/industrial-specific keyword list (контрагент, поставщик, ФИО, исполнитель, сумма, договор) |
| Numeric statistics show masked values instead of original count | User can't verify masking worked | Show: "Masked 847 unique company names across 3 sheets, 156 employee names, 23 contract numbers" |

---

## "Looks Done But Isn't" Checklist

- [ ] **Cross-sheet consistency:** Verify same value in Sheet1 and Sheet3 → same pseudonym. Test with a multi-sheet file.
- [ ] **Reverse mapping completeness:** Immediately decrypt a freshly-masked file → verify 100% of values restored with no residual pseudonyms.
- [ ] **Numeric coefficient per-column:** Verify that two numeric columns have different multipliers applied (different random seeds per column).
- [ ] **Integer rounding:** Verify integer quantity columns remain integer after perturbation.
- [ ] **Contract numbers untouched:** Verify "Номер договора"-type columns are text-masked, not numerically perturbed.
- [ ] **File structure preserved:** Verify output Excel has same number of sheets, same sheet names, same column count as input.
- [ ] **Cell formats preserved:** Dates are still dates, not serial numbers; currency cells still show currency format.
- [ ] **Large file performance:** Test with a 30,000-row, 4-sheet file; processing must complete in <30 seconds.
- [ ] **Session state isolation:** Open two browser tabs; verify masking in tab 1 doesn't affect tab 2.
- [ ] **Temp file cleanup:** Verify no temp files accumulate in `/tmp` after multiple processing runs.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Cross-sheet inconsistency discovered post-launch | HIGH | Requires masking engine rewrite; all existing user mapping files become incompatible |
| Reverse mapping failures discovered post-launch | MEDIUM | Add normalization layer to decryption; existing mapping files still work, only decryption logic changes |
| Memory OOM on large files | MEDIUM | Add file size cap + lxml installation; can be hot-patched without rewrite |
| Numeric perturbation of contract numbers | MEDIUM | Fix column classifier; requires re-masking affected files |
| Temp file accumulation | LOW | Add cleanup on session end; no data loss |
| Session state loss on rerun | HIGH if discovered late | Requires full UI state management refactor; much cheaper to design correctly upfront |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Cross-sheet inconsistency | Phase 1: Masking engine core | Unit test: same value in two sheets → identical pseudonym |
| Numeric perturbation precision | Phase 1: Masking engine core | Unit test: integers stay integer, floats have ≤2 decimal places |
| Reverse mapping normalization | Phase 1 (masking) + decryption phase | Integration test: mask → decrypt on same file → 100% restore rate |
| Russian name variant normalization | Phase 1: Masking engine core | Test file with ООО "X" and ООО X → single pseudonym |
| Streamlit session state | Phase 1: App architecture | Manual test: click every checkbox after upload → no state loss |
| openpyxl memory | Phase 1: Tech setup | Benchmark with 30k-row file; measure peak RAM |
| Mixed dtype columns | Phase 1: Column detection | Test with real sample file "Данные для маскирования_13.03.xlsx" |

---

## Sources

- [openpyxl Performance Documentation](https://openpyxl.readthedocs.io/en/stable/performance.html) — confirms ~50x memory multiplier, read-only/write-only modes
- [pandas/openpyxl memory issue #40569](https://github.com/pandas-dev/pandas/issues/40569) — confirmed memory blow-up with openpyxl engine
- [Streamlit file_uploader memory issue #9218](https://github.com/streamlit/streamlit/issues/9218) — confirmed server killed on large file uploads
- [Streamlit memory leak issue #12506](https://github.com/streamlit/streamlit/issues/12506) — confirmed session state not released on tab close
- [Streamlit session state docs](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state) — widget key persistence behavior
- [pandas read_excel NaN handling #20377](https://github.com/pandas-dev/pandas/issues/20377) — mixed dtype/NaN pitfalls
- [IEEE 754 floating point precision in financial calculations](https://hackerone.com/blog/precision-matters-why-using-cents-instead-floating-point-transaction-amounts-crucial) — float multiplication noise
- [Microsoft Presidio pseudonymization](https://microsoft.github.io/presidio/samples/python/pseudonymization/) — reverse mapping patterns
- [Unicode normalization Python docs](https://docs.python.org/3/howto/unicode.html) — NFC normalization for Cyrillic
- [pandas Cyrillic filename issue #17773](https://github.com/pandas-dev/pandas/issues/17773) — Cyrillic encoding edge cases
- [russiannames PyPI](https://pypi.org/project/russiannames/) — Russian name parsing tools
- Training data: Streamlit rerun model behavior, openpyxl write-back patterns, data masking industry practices

---
*Pitfalls research for: data masking Streamlit app (Энигма) — industrial Russian Excel data*
*Researched: 2026-03-19*
