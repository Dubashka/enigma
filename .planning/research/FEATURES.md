# Feature Research

**Domain:** Data masking / anonymization tool for LLM data preparation (tabular: Excel/CSV)
**Researched:** 2026-03-19
**Confidence:** HIGH

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| File upload (Excel + CSV) | Every tool accepts files; Excel is the universal format for industrial data | LOW | openpyxl handles xlsx including multi-sheet; pandas handles CSV |
| Automatic PII column detection | Manual column selection is unusable for 15–37 column files; auto-detect is the baseline since Presidio/ARX | MEDIUM | Column name heuristics + value sampling. Industrial Russian names/companies need custom patterns (not just English NER) |
| Checkbox overrides for detected columns | Users know their data better than the tool; every serious tool lets you confirm/adjust detection | LOW | Standard Streamlit checkbox list |
| Text masking via pseudonymization | Replace-with-placeholder is the universal baseline: Presidio, anonLLM, ARX all do this | LOW | Deterministic: same value = same pseudonym always |
| Consistent pseudonymization (same value → same alias) | Without this the LLM cannot reason about entity relationships; Google Cloud DLP does this by default | MEDIUM | Requires maintaining a mapping dict per-session; must be cross-sheet |
| Download masked file | The output delivery mechanism — without it nothing else matters | LOW | Generate in-memory Excel with openpyxl, serve via Streamlit download |
| Download mapping file | Users need the lookup table to reverse-engineer LLM output; every reversible-anon solution provides this | LOW | Two formats: JSON (machine use) + Excel (human use). Already a project requirement |
| De-anonymization / reverse mapping | Complete the workflow: masked → LLM → output → restore. anonLLM, Presidio+LangChain all support this | MEDIUM | Load JSON mapping + masked file, do value substitution. New LLM-added columns untouched |
| Data preview before masking | ARX and Amnesia both show before/after; users need to verify detection worked | LOW | Streamlit dataframe widget; show first N rows |
| Statistics after masking | Quantify what was done; every professional tool shows counts | LOW | Count of unique entities masked per column, total replacements |
| Preserve file structure (sheets, columns, row count) | LLM needs intact structure to analyze; stripping structure breaks analysis | LOW | openpyxl write-back preserving sheet names, column headers |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valued.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Auto-prefix from column name (e.g. "Предприятие A") | Balances readability and automation: LLM understands entity type from alias; more useful than opaque "ENTITY_1" | LOW | Split on column name, strip stop words, prepend to counter. Russian language aware |
| Numeric masking with ratio-preserving multiplier | Financial/quantity data retains proportional relationships for LLM analysis; standard variance tools destroy ratios | MEDIUM | Per-file random coefficient 0.5–1.5 applied uniformly (or per-column) to preserve relative magnitudes |
| Cross-sheet consistent masking | An entity appearing on sheet 1 and sheet 3 gets the same alias; enables LLM to join data mentally across sheets | MEDIUM | Single mapping dict for entire file, not per-sheet; non-obvious for tools that treat sheets independently |
| Stateless architecture (no server storage) | Industrial data is sensitive; users trust a tool that guarantees zero server persistence; competitive vs cloud solutions | LOW | Streamlit session state only; no DB, no disk writes beyond temp files |
| Russian-language interface | No comparable tool has a Russian-first UI; reduces friction for the target audience | LOW | All labels/instructions in Russian; already in requirements |
| Russian entity recognition (Cyrillic company names, patronymics) | Western NLP tools (Presidio, spaCy English) miss ООО "ЛУИС+", Леонов Алексей Борисович; custom patterns needed | HIGH | Regex patterns for Cyrillic legal entity forms (ООО, ОАО, АО, ИП) + ФИО (Фамилия Имя Отчество) structure |
| Column auto-detection from highlight color | Target file uses yellow highlighting to mark sensitive columns; reading cell fill color as a detection hint is unique | MEDIUM | openpyxl can read PatternFill; use as additional signal, not sole source. Gracefully degrade when absent |
| Masking statistics per-column breakdown | Shows exactly which columns produced how many unique aliases; helps users validate masking coverage | LOW | Aggregate mapping dict by source column |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Server-side storage of mapping history | "Convenience" — don't lose mappings between sessions | Contradicts core security value prop; creates a data liability; users said they don't want this | User owns the JSON mapping file; simple file management |
| User authentication / login system | Multi-user access control feels "enterprise" | Adds weeks of complexity for v1; the stateless model already limits exposure; not validated by users yet | Ship without auth, add in v2 if multi-tenant use emerges |
| Real-time/streaming anonymization | Feels modern and fast | v1 use case is batch file preparation, not streaming; adds async complexity with no user benefit | Synchronous processing with a progress indicator is sufficient |
| Automatic LLM integration (send to ChatGPT directly) | Reduces friction, one-click workflow | Requires API key management, model selection UI, prompt engineering — entirely separate product; dilutes the masking focus | Stay focused on masking; user pastes into LLM manually |
| Differential privacy / k-anonymity guarantees | Sounds rigorous; enterprise compliance tools (ARX) use it | Formal privacy models require generalization/suppression that destroys data utility for LLM analysis; incompatible with the use case | Pseudonymization with consistent mapping is the right model here |
| Word/PPT/PDF file support | Users have data in many formats | Each format needs a different parser; multi-format support multiplies QA burden; core use case is Excel | Explicitly defer to v2+; Excel covers the primary pain point |
| Multilingual UI switching | Internationalization feels professional | Russian-only users don't need this; adds translation maintenance overhead; weakens cohesion | Russian-only in v1; revisit if non-Russian users emerge |
| Cloud deployment with public URL | Broader access | Public deployment exposes internal corporate data to risk if auth is absent; target users expect intranet/VM deployment | Deploy on company VM, accessible only on internal network |

---

## Feature Dependencies

```
File Upload (Excel/CSV)
    └──requires──> Data Preview
    └──requires──> Column Detection
                       └──requires──> Checkbox Override UI
                       └──enhances──> Color-based Detection Hint (openpyxl fill)

Column Detection
    └──requires──> Masking Engine (text pseudonymization)
                       └──requires──> Consistent Mapping Dict (cross-sheet)
                                          └──requires──> Download Mapping (JSON + Excel)
                                          └──requires──> De-anonymization Engine

Masking Engine (text)
    └──parallel──> Numeric Masking (ratio-preserving multiplier)

Masking Engine
    └──requires──> Download Masked File
    └──produces──> Masking Statistics

De-anonymization Engine
    └──requires──> Upload Masked File
    └──requires──> Upload JSON Mapping
    └──produces──> Restored File Download

Russian Entity Recognition
    └──enhances──> Column Detection (value-level analysis)
    └──conflicts──> Using spaCy English NER as sole detector
```

### Dependency Notes

- **Column Detection requires Consistent Mapping Dict:** Detection determines what goes into the map; the map must be built at detection time, not per-sheet, to enable cross-sheet consistency.
- **De-anonymization requires JSON Mapping:** The JSON format is machine-readable and enables exact-match substitution; the Excel mapping is for human review only and does not drive de-anonymization.
- **Russian Entity Recognition enhances Column Detection:** Value-level entity recognition (spotting ООО "..." patterns in cells) raises confidence for columns the name-based heuristic might miss (e.g., a column named "Поставщик" is obvious; one named "Контрагент 1" is less so).
- **Color-based Detection conflicts with relying on it as sole source:** Yellow highlighting is a human convention, not a schema contract. Use as a boosting signal alongside name heuristics.
- **Numeric Masking is independent of text pseudonymization:** They share the masking pipeline but use separate logic; a column can be flagged as numeric (multiply by coeff) or text (pseudonymize), not both.

---

## MVP Definition

### Launch With (v1)

Minimum viable product — what's needed to validate the concept.

- [ ] File upload: Excel (multi-sheet) + CSV — the entry point; nothing works without it
- [ ] Data preview (first 50 rows) — user must verify what they uploaded before masking
- [ ] Auto-detection of sensitive columns via name heuristics — core automation value; manual selection is too slow for 30+ columns
- [ ] Checkbox override for detected columns — users will always need to add/remove columns
- [ ] Text pseudonymization with auto-prefix from column name — the core masking algorithm; readable aliases are a key differentiator
- [ ] Consistent cross-sheet mapping — without this, multi-sheet files are unusable for LLM analysis
- [ ] Numeric masking with ratio-preserving multiplier — financial/quantity columns are the second most common sensitive type in industrial data
- [ ] Download masked Excel (structure-preserving) — the primary output
- [ ] Download mapping as JSON + Excel — enables de-anonymization; without it the tool is destructive, not reversible
- [ ] De-anonymization (upload masked file + JSON mapping → restore) — completes the LLM workflow loop
- [ ] Masking statistics — users need to verify coverage; builds trust
- [ ] Russian-language UI — target audience; non-negotiable for adoption

### Add After Validation (v1.x)

Features to add once core is working.

- [ ] Russian entity recognition (Cyrillic regex patterns for ООО/ОАО/ИП, ФИО) — trigger: users report missed detections in Russian company names
- [ ] Color-based detection hint (read yellow fill from openpyxl) — trigger: users of the sample file ask why sensitive columns weren't auto-detected
- [ ] Per-column masking statistics breakdown — trigger: user feedback that aggregate stats aren't granular enough
- [ ] Fuzzy de-anonymization (handle LLM slight reformatting of aliases) — trigger: users report that LLM sometimes rewrites "Предприятие A" as "предприятие a"

### Future Consideration (v2+)

Features to defer until product-market fit is established.

- [ ] Word/PPT/PDF file support — defer: each format is a separate engineering effort; validate Excel demand first
- [ ] Authentication / user accounts — defer: validate stateless model first; add only if multi-tenant deployment requested
- [ ] LLM API integration — defer: scope creep risk; stays a masking tool not an AI interface
- [ ] Configurable anonymization strategies per column (hash vs pseudonym vs redact) — defer: current pseudonym+multiplier covers 95% of use cases

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| File upload (Excel multi-sheet + CSV) | HIGH | LOW | P1 |
| Auto column detection (name heuristics) | HIGH | MEDIUM | P1 |
| Text pseudonymization with column prefix | HIGH | LOW | P1 |
| Cross-sheet consistent mapping | HIGH | MEDIUM | P1 |
| Download masked file | HIGH | LOW | P1 |
| Download mapping (JSON + Excel) | HIGH | LOW | P1 |
| De-anonymization | HIGH | MEDIUM | P1 |
| Data preview | MEDIUM | LOW | P1 |
| Checkbox override | MEDIUM | LOW | P1 |
| Numeric ratio-preserving masking | HIGH | LOW | P1 |
| Masking statistics | MEDIUM | LOW | P1 |
| Russian UI | HIGH | LOW | P1 |
| Russian entity recognition (Cyrillic) | HIGH | HIGH | P2 |
| Color-based detection hint | MEDIUM | MEDIUM | P2 |
| Per-column stats breakdown | LOW | LOW | P2 |
| Fuzzy de-anonymization | MEDIUM | MEDIUM | P2 |
| Word/PPT/PDF support | MEDIUM | HIGH | P3 |
| Authentication | LOW | HIGH | P3 |
| LLM API integration | LOW | HIGH | P3 |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

---

## Competitor Feature Analysis

| Feature | Microsoft Presidio | ARX | anonLLM / simple tools | Our Approach |
|---------|-------------------|-----|------------------------|--------------|
| Input format | Text, structured data | CSV/relational DB | Text | Excel (multi-sheet) + CSV |
| Auto PII detection | Yes — NLP + regex, 50+ entity types | No — manual quasi-identifier selection | Yes — NLP | Column name heuristics + value sampling + Cyrillic regex |
| Anonymization method | Replace, redact, hash, encrypt, mask | Generalization + suppression | Replace with fake | Pseudonym with column-prefix (text) + ratio multiplier (numeric) |
| Consistent mapping | Yes (per document) | Yes (by design) | Yes | Yes, cross-sheet within file |
| Reversible | Yes (with Faker/mapping) | No (generalization is lossy) | Yes | Yes — JSON mapping file |
| Numeric data handling | Limited | Microaggregation | No | Ratio-preserving multiplier |
| Privacy model | None (pseudonymization) | k-anonymity, l-diversity, differential privacy | None | None needed — pseudonymization for LLM use |
| Russian language | No (English NER) | No | No | Yes — primary language |
| UI | REST API / Python SDK | Desktop GUI | Python library | Streamlit web app |
| Multi-sheet Excel | No native | No | No | Yes |
| Stateless | N/A | N/A | N/A | Yes — Streamlit session only |
| Target use case | Enterprise compliance, text pipelines | Academic research, formal privacy | Quick LLM prep | Industrial tabular data → cloud LLM |

---

## Sources

- [Microsoft Presidio GitHub](https://github.com/microsoft/presidio) — feature list, anonymization methods, referential integrity issue
- [Secure LLM Usage With Reversible Data Anonymization — DZone](https://dzone.com/articles/llm-pii-anonymization-guide) — reversible anonymization workflow patterns
- [ARX Data Anonymization Tool](https://arx.deidentifier.org/overview/) — privacy models, generalization/suppression techniques
- [Amnesia — OpenAIRE](https://www.openaire.eu/amnesia-guide) — k-anonymity UI patterns, preview features
- [anonLLM GitHub](https://github.com/fsndzomga/anonLLM) — simple reversible PII replacement for LLM APIs
- [City of Helsinki tabular-anonymizer](https://github.com/City-of-Helsinki/tabular-anonymizer) — DataFrame-level anonymization patterns
- [Consistent Cross-Table Data Pseudonymization — IRI](https://www.iri.com/blog/data-protection/consistent-cross-table-data-pseudonymization/) — cross-table referential integrity pattern
- [Protecting PII data with anonymization in LLM projects — TSH](https://tsh.io/blog/pii-anonymization-in-llm-projects) — LLM-specific workflow and tooling
- [Data Masking Wikipedia — numeric variance methods](https://en.wikipedia.org/wiki/Data_masking) — ratio-preserving numeric masking techniques
- [Best Data Masking Tools 2026 — OvalEdge](https://www.ovaledge.com/blog/data-masking-tools/) — enterprise feature baseline

---
*Feature research for: data masking / anonymization tool for tabular LLM data preparation*
*Researched: 2026-03-19*
