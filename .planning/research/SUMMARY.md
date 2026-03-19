# Project Research Summary

**Project:** Энигма — Data Masking / Anonymization App
**Domain:** Streamlit-based tabular data pseudonymization for LLM data preparation (Excel/CSV, Russian industrial data)
**Researched:** 2026-03-19
**Confidence:** HIGH

## Executive Summary

Энигма is a focused internal tool that solves a specific workflow problem: prepare sensitive Russian industrial Excel data for analysis by cloud LLMs by pseudonymizing it in a reversible way. Research confirms this is a well-understood domain with clear prior art (Microsoft Presidio, ARX, anonLLM), but no existing tool covers the target niche — multi-sheet Russian-language Excel files with industrial entity naming conventions. The right approach is a small, stateless Streamlit web app with a deterministic pseudonymization engine, deployed on the company's existing VM behind nginx, with no server-side storage of any kind. The architecture is simple and the entire core can be built with Python + pandas + openpyxl without exotic dependencies.

The recommended stack (Python 3.12, Streamlit 1.55, pandas 3.0.1, openpyxl 3.1.5) is fully confirmed against current package releases. The most critical design decision is building a single shared mapping dictionary across all sheets before processing any output — without this, multi-sheet cross-entity consistency is broken and the tool's primary value proposition collapses. A secondary but equally important decision is that pseudonyms use column-name-derived prefixes ("Предприятие A", "Контрагент B") rather than generic tokens — this makes LLM output readable and actionable.

The primary risks are implementation-level, not architectural: inconsistent cross-sheet masking, silent reverse-mapping failures after LLM reformatting, and Streamlit session state mismanagement. All three are avoidable with upfront design discipline and early-phase testing. Memory pressure from large openpyxl workloads is a real concern on the target VM and requires a file size cap and the lxml XML parser to be installed from day one. No phase requires complex external integrations — the scope is intentionally narrow and self-contained, which makes the build tractable for a small team.

## Key Findings

### Recommended Stack

The stack is minimal and well-validated. Python 3.12 + Streamlit 1.55 + pandas 3.0.1 + openpyxl 3.1.5 cover the full feature set. pandas 3.0's Copy-on-Write default makes masking logic safer (no silent DataFrame mutation). Faker is explicitly not needed — column-prefix + counter generates better pseudonyms for this use case with zero extra dependency. numpy is available as a pandas transitive dependency for numeric perturbation. Production deployment uses systemd + nginx on the existing VM; Docker adds overhead without benefit for a single-VM internal tool.

**Core technologies:**
- Python 3.12: Runtime — required by pandas 3.0.1 (hard minimum 3.11); 3.12 is the current sweet spot
- Streamlit 1.55.0: UI framework — the only mature Python-native data app framework; stateless-by-default fits zero-server-storage requirement
- pandas 3.0.1: DataFrame operations and Excel/CSV I/O — industry standard; handles multi-sheet Excel natively via `sheet_name=None`
- openpyxl 3.1.5: Excel read/write engine — required under pandas and directly for preserving sheet structure on write-back
- numpy (transitive): Numeric perturbation via `np.random.uniform(0.5, 1.5)` per column — no separate install needed
- systemd + nginx: Process management and reverse proxy on VM — simpler than Docker for a single-host internal tool; nginx required for WebSocket header forwarding

**Critical version notes:**
- pandas 3.0.1 requires Python 3.11+ (hard requirement, not advisory)
- Do not use xlrd — it dropped .xlsx support; openpyxl is the only correct engine
- Do not use pandas 2.x — Copy-on-Write is not default; code written for 3.0 may silently mutate DataFrames on 2.x

### Expected Features

All P1 features can be completed in v1. The feature set is cohesive and the dependency graph is well-defined: file upload gates everything; column detection gates masking; masking gates all downloads; de-anonymization is a separate flow gated on mapping file upload.

**Must have (table stakes):**
- File upload (Excel multi-sheet + CSV) — entry point; nothing works without it
- Data preview (first 50 rows) — users must verify what they uploaded before committing to mask
- Auto-detection of sensitive columns via name heuristics — manual selection is too slow for 30+ column industrial files
- Checkbox override for detected columns — users always need to add or remove columns from the detected set
- Text pseudonymization with column-name prefix — core masking output; readable aliases are the key differentiator
- Consistent cross-sheet mapping — without this, multi-sheet files are unusable for LLM analysis
- Numeric masking with ratio-preserving multiplier — financial/quantity columns are the second most common sensitive type
- Download masked Excel (structure-preserving) — primary output
- Download mapping as JSON + Excel — enables de-anonymization; without it the tool is destructive, not reversible
- De-anonymization (upload masked file + JSON mapping → restored download) — completes the LLM workflow loop
- Masking statistics — validates coverage; builds user trust
- Russian-language UI — non-negotiable for target audience adoption

**Should have (competitive, add in v1.x):**
- Russian entity recognition via Cyrillic regex (ООО, ОАО, ИП, ФИО patterns) — triggers when users report missed detections on Russian company names
- Color-based detection hint (read yellow cell fill via openpyxl) — relevant for the target sample file which uses yellow highlighting
- Per-column masking statistics breakdown — when aggregate stats aren't granular enough
- Fuzzy de-anonymization — when users report that LLM-reformatted aliases fail reverse lookup

**Defer (v2+):**
- Word/PPT/PDF file support — each format is a separate engineering effort; validate Excel demand first
- Authentication / user accounts — stateless model limits exposure; add only if multi-tenant deployment is requested
- LLM API integration — scope creep; keeps the tool focused on masking, not AI interfacing
- Configurable anonymization strategies per column — current pseudonym + multiplier covers 95% of cases

### Architecture Approach

The architecture is a single-page-state Streamlit application with a clean separation between a stateless `core/` layer (pure Python, no Streamlit imports, unit-testable) and Streamlit UI pages that orchestrate user flows and read/write `st.session_state`. All transient data lives exclusively in session state — no disk writes, no database, no external services. The masking engine performs two passes: a first pass over all sheets to build the global mapping dictionary, then a second pass to apply substitutions and generate output as `io.BytesIO` objects passed directly to `st.download_button`.

**Major components:**
1. File Parsing Layer (`core/parser.py`) — reads uploaded bytes into a `dict[sheet_name → DataFrame]` using `pd.read_excel(..., sheet_name=None, engine='openpyxl')`; infers column types and metadata
2. Heuristics Engine (`core/heuristics.py`) — scores columns by Russian keyword patterns and dtype to suggest sensitive set; must be semantic (name-based), not dtype-only, to avoid misclassifying contract numbers as numeric targets
3. Masking Engine (`core/masker.py`) — Text Pseudonymizer: single global dict with column-derived prefix + incrementing counter, one pass over all sheets; Numeric Perturber: per-column random multiplier in [0.5, 1.5], applied uniformly
4. Mapping Store (`core/mapping.py`) — owns serialization to JSON and Excel; the JSON format drives de-anonymization (machine-readable), the Excel is for human review only
5. Output Assembly Layer (`core/assembler.py`) — serializes masked workbook and mapping files to `BytesIO`; preserves sheet structure, cell number formats, and column headers via openpyxl
6. Reverse Decrypt Layer (`pages/02_decrypt.py` + `core/`) — loads masked file + mapping JSON, inverts text lookup, divides numeric columns by stored multiplier, leaves LLM-added columns untouched
7. Session State Bus — `st.session_state` isolates all user data per browser tab/WebSocket connection; acts as the in-memory database; cleared intentionally on page refresh

### Critical Pitfalls

1. **Inconsistent cross-sheet masking** — build ONE global mapping dict before iterating over any sheet; passing a fresh dict into each sheet loop is the most common mistake and breaks the entire cross-entity analysis value proposition. Recovery post-launch requires a full masking engine rewrite.

2. **Streamlit session state loss on rerun** — every widget interaction triggers a full script rerun; any state not in `st.session_state` is lost. Design a state machine (`stage: 'uploaded' | 'columns_selected' | 'masked'`) upfront and store all computed results in session state. Refactoring this after the fact is expensive.

3. **Silent reverse-mapping failure after LLM reformatting** — LLMs add trailing spaces, change quote styles, or use Unicode variants of characters. Exact string match on pseudonyms will silently fail to restore some cells. Apply `unicodedata.normalize('NFC', value).strip()` normalization on both the map key and the lookup value at decryption time.

4. **Numeric perturbation of semantic identifiers and integer precision** — "Номер договора" columns contain numeric-looking values that are IDs, not quantities; multiplying them destroys meaning. Integer quantity columns become fractional after float multiplication (IEEE 754 noise). Column classification must combine name heuristics with dtype; always round perturbed integers back to int; never perturb ID-pattern columns numerically.

5. **openpyxl memory explosion on formatted multi-sheet files** — openpyxl default mode loads ~50x the file size in RAM; a 20 MB formatted workbook can consume 1 GB. Install `lxml` from day one, cap upload size at 50 MB in Streamlit config, and use `pd.read_excel` (not raw openpyxl) for data reading.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Foundation — App Skeleton and State Architecture

**Rationale:** Streamlit's session state rerun model is the most dangerous pitfall if not designed upfront. The state machine and `core/` vs `pages/` separation must exist before any feature logic is added. This phase de-risks the single highest-cost refactor (session state mismanagement has HIGH recovery cost per pitfalls research).

**Delivers:** Working Streamlit app with file upload, data preview, and session state architecture in place; no masking yet.

**Addresses:** File upload (Excel multi-sheet + CSV), data preview (50 rows), Russian-language UI skeleton.

**Avoids:** Pitfall 5 (session state loss), Anti-Pattern 1 (global variables), Anti-Pattern 2 (temp files to disk).

**Research flag:** Standard patterns — skip research phase. Streamlit architecture is well-documented.

### Phase 2: Column Detection Engine

**Rationale:** Detection must be built and validated before the masking engine — it provides the `mask_config` dict that masking consumes. Building detection with the real sample file early catches the mixed-dtype (Pitfall 7) and Russian naming issues before they infect masking logic.

**Delivers:** Heuristics engine that scores columns by Russian industrial keyword patterns; checkbox override UI pre-populated with detected columns and masking type (text vs numeric vs skip).

**Addresses:** Auto-detection of sensitive columns, checkbox override, Russian-specific keywords (контрагент, поставщик, ФИО, сумма, договор).

**Avoids:** Pitfall 7 (mixed dtype columns misclassified), and the "contract numbers perturbed numerically" failure mode.

**Research flag:** May need light research during planning on Russian industrial column naming patterns if the sample file reveals gaps in the keyword list.

### Phase 3: Core Masking Engine

**Rationale:** This is the most logic-dense phase and must be built with the critical cross-sheet constraint as an explicit design requirement, not retrofitted. Both text pseudonymization and numeric perturbation belong here because they share the two-pass loop and mapping store structure. Building them together prevents divergent state management.

**Delivers:** Text pseudonymizer (global dict, column-prefix + counter, single pre-pass over all sheets), numeric perturber (per-column random multiplier, round-to-int for integer columns), masking statistics, full mapping store.

**Addresses:** Text pseudonymization with column prefix, consistent cross-sheet mapping, numeric masking with ratio-preserving multiplier, masking statistics.

**Avoids:** Pitfall 1 (inconsistent cross-sheet masking), Pitfall 2 (numeric precision and ID misclassification), Pitfall 4 (Russian company name variant normalization — apply `.strip().upper()` + Cyrillic quote stripping from day one), Anti-Pattern 3 (iterrows), Anti-Pattern 4 (rebuild mapping on every rerun).

**Research flag:** Standard patterns — skip research phase. Pseudonymization patterns are well-documented.

### Phase 4: Output Assembly and Downloads

**Rationale:** With masking engine complete, output delivery is the next dependency in the feature graph. All three downloads (masked Excel, mapping JSON, mapping Excel) are generated here. BytesIO round-trip pattern is mandatory for the stateless architecture.

**Delivers:** Masked Excel download (structure-preserving, sheet order intact, cell number formats preserved), mapping JSON download (machine-readable, used by decryption), mapping Excel download (human-readable lookup table), output files named after input filename.

**Addresses:** Download masked file, download mapping (JSON + Excel).

**Avoids:** Anti-Pattern 2 (disk writes), integration gotcha (BytesIO.seek(0) before passing to download_button), JSON serialization of numpy/pandas types.

**Research flag:** Standard patterns — skip research phase.

### Phase 5: De-anonymization Flow

**Rationale:** Completes the core LLM workflow loop (mask → LLM → restore). Depends on the mapping JSON format being finalized in Phase 4. Should be built as a separate Streamlit page (`pages/02_decrypt.py`) that reuses `core/` modules without duplication.

**Delivers:** Decryption page accepting masked file + mapping JSON, restoring original values by inverting text lookup and dividing numeric columns by stored multiplier, leaving LLM-added columns untouched, showing restored file download and completeness statistics.

**Addresses:** De-anonymization feature, "X values restored, Y not matched" feedback.

**Avoids:** Pitfall 3 (reverse mapping failure — apply Unicode normalization at lookup time), UX pitfall (no feedback on decryption completeness).

**Research flag:** Standard patterns — skip research phase.

### Phase 6: Deployment and Performance Hardening

**Rationale:** The app must be production-ready on the target VM before user handoff. This phase covers the systemd service, nginx reverse proxy, file size cap, lxml installation, and performance validation against a large real file. Memory and CPU bottlenecks are known risks that can only be verified with real data at scale.

**Delivers:** systemd service definition, nginx config with WebSocket headers, Streamlit config with `server.maxUploadSize = 50`, lxml installation, performance benchmark (30k-row, 4-sheet file in <30 seconds), session isolation verification across two concurrent browser tabs.

**Addresses:** VM deployment (systemd + nginx), openpyxl memory safety.

**Avoids:** Pitfall 6 (openpyxl memory explosion), security mistake (temp file accumulation), the "Looks Done But Isn't" checklist items for performance and concurrency.

**Research flag:** MEDIUM — nginx WebSocket configuration for Streamlit has community-level documentation only; verify the proxy_set_header pattern during implementation.

### Phase Ordering Rationale

- Phase 1 must come first because Streamlit's rerun model affects every subsequent phase; the state machine skeleton costs nothing to add early and is extremely expensive to refactor later.
- Phase 2 (detection) before Phase 3 (masking) because masking consumes the detection output (`mask_config`); testing detection with real data early catches column-type misclassification bugs before they propagate into masking.
- Phase 3 (masking) before Phase 4 (output) because output assembly needs the masked DataFrames and mapping dict that masking produces.
- Phase 4 (output) before Phase 5 (decryption) because decryption depends on the finalized mapping JSON schema.
- Phase 6 last because it validates the complete system under production conditions; putting it earlier would benchmark an incomplete product.
- v1.x features (Russian Cyrillic regex detection, color-based hints, fuzzy de-anonymization) are intentionally deferred to after Phase 6 — they enhance detection and decryption quality but do not block the core workflow.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 6:** nginx WebSocket configuration for Streamlit is documented primarily in community forums; verify `proxy_set_header Upgrade` and `proxy_read_timeout` values against the actual VM OS version before implementation.
- **Phase 2 (if gaps emerge):** Russian industrial column naming patterns beyond the initial keyword list; validate against the real sample file "Данные для маскирования_13.03.xlsx" early and expand heuristics if detection misses common column types.

Phases with standard patterns (skip research phase):
- **Phase 1:** Streamlit multi-page app structure and session state architecture is thoroughly documented in official Streamlit docs.
- **Phase 3:** Pseudonymization with global mapping dict is a well-established pattern with multiple open-source references (Presidio, anonLLM).
- **Phase 4:** BytesIO round-trip and ExcelWriter multi-sheet output are standard pandas/openpyxl patterns.
- **Phase 5:** Reverse mapping via dict inversion is straightforward Python; the only nuance (Unicode normalization) is already specified.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All package versions verified against current PyPI releases; version compatibility matrix confirmed |
| Features | HIGH | Feature set derived from competitor analysis (Presidio, ARX, anonLLM, Amnesia) plus explicit project requirements; clear MVP vs v1.x vs v2+ split |
| Architecture | HIGH | Official Streamlit architecture docs; session state isolation confirmed; BytesIO pattern confirmed; project structure rationale is sound |
| Pitfalls | HIGH | Pitfalls derived from confirmed technical constraints (GitHub issues, official docs, IEEE 754 behavior) not speculation; recovery costs explicitly quantified |

**Overall confidence:** HIGH

### Gaps to Address

- **Sample file validation (Phase 2):** The real file "Данные для маскирования_13.03.xlsx" has not been analyzed. The column name heuristics keyword list needs to be validated against actual column names in that file before Phase 2 is considered complete. If columns use non-obvious naming ("Контрагент 1", "Субъект"), the heuristic will miss them and the user fallback (checkbox override) will carry more weight.
- **Concurrent user load on target VM:** The VM's RAM capacity is not specified in research. Architecture research estimates 50 concurrent sessions at ~2.5 GB RAM assuming 50 MB files; the actual VM spec needs to be confirmed before recommending a concurrent-user ceiling to users.
- **LLM alias reformatting patterns:** Pitfall 3 (reverse mapping failure) is known but the normalization strategy (NFC + strip) is a reasonable first approach, not a proven complete fix. Fuzzy de-anonymization (v1.x) with `rapidfuzz` should be planned as a follow-on if users report persistent restoration failures.
- **Cyrillic legal form normalization depth:** The MVP normalization (strip quotes, `.upper()`) handles the most common variants but will not catch "ООО" vs "Общество с ограниченной ответственностью" or abbreviation differences. This gap is documented and intentionally deferred to v1.x Russian entity recognition work.

## Sources

### Primary (HIGH confidence)
- [streamlit · PyPI](https://pypi.org/project/streamlit/) — confirmed version 1.55.0
- [pandas · PyPI](https://pypi.org/project/pandas/) — confirmed version 3.0.1, Python 3.11+ requirement
- [openpyxl · PyPI](https://pypi.org/project/openpyxl/) — confirmed version 3.1.5
- [xlsxwriter · PyPI](https://pypi.org/project/xlsxwriter/) — confirmed version 3.2.9
- [Streamlit Architecture Concepts](https://docs.streamlit.io/develop/concepts/architecture) — session state isolation, rerun model
- [Streamlit Session State Reference](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state) — widget key persistence
- [openpyxl Performance Documentation](https://openpyxl.readthedocs.io/en/stable/performance.html) — ~50x memory multiplier, lxml recommendation
- [Microsoft Presidio GitHub](https://github.com/microsoft/presidio) — feature baseline, pseudonymization patterns
- [ARX Data Anonymization Tool](https://arx.deidentifier.org/overview/) — privacy model comparison
- [anonLLM GitHub](https://github.com/fsndzomga/anonLLM) — reversible replacement for LLM APIs

### Secondary (MEDIUM confidence)
- [Streamlit deployment with nginx community thread](https://discuss.streamlit.io/t/streamlit-deployment-with-nginx/111676) — WebSocket header configuration
- [Consistent Cross-Table Pseudonymization (IRI)](https://www.iri.com/blog/data-protection/consistent-cross-table-data-pseudonymization/) — cross-table referential integrity
- [Secure LLM Usage With Reversible Data Anonymization (DZone)](https://dzone.com/articles/llm-pii-anonymization-guide) — reversible anonymization workflow
- [pandas/openpyxl memory issue #40569](https://github.com/pandas-dev/pandas/issues/40569) — confirmed memory blow-up
- [Streamlit file_uploader memory issue #9218](https://github.com/streamlit/streamlit/issues/9218) — OOM on large uploads

### Tertiary (context, needs validation against real file)
- Russian industrial column naming conventions — needs validation against "Данные для маскирования_13.03.xlsx"
- Target VM RAM capacity — not confirmed; needed for concurrent-user ceiling recommendation

---
*Research completed: 2026-03-19*
*Ready for roadmap: yes*
