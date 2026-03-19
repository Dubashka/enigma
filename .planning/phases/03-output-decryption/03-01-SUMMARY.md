---
phase: 03-output-decryption
plan: 01
subsystem: core
tags: [pandas, xlsxwriter, openpyxl, json, tdd, pytest]

# Dependency graph
requires:
  - phase: 02-detection-masking
    provides: "mask_sheets() returning mapping dict {text: {norm_val: pseudonym}, numeric: {col: multiplier}}"
provides:
  - "core/output.py: generate_masked_xlsx, generate_mapping_json, generate_mapping_xlsx — pure bytes-returning functions"
  - "core/decryptor.py: load_mapping_json, decrypt_sheets — pure decryption logic consuming mapping JSON"
affects:
  - 03-output-decryption (phase 03-02 UI wiring will import these functions directly)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure function design: all output/decryption logic takes dicts/DataFrames, returns bytes — no Streamlit dependency"
    - "TDD RED-GREEN cycle: tests created first and confirmed failing before implementation"
    - "ensure_ascii=False in json.dumps — Cyrillic literal in JSON, not \u escapes"
    - "xlsxwriter engine for write-only xlsx generation; openpyxl for read-back in tests"
    - "Inverted text map {pseudonym: original} built at call time — O(n) but n is always small"

key-files:
  created:
    - core/output.py
    - core/decryptor.py
    - tests/test_output.py
    - tests/test_decryptor.py
  modified: []

key-decisions:
  - "load_mapping_json returns None on missing keys (not just on parse failure) — callers must check for None before use"
  - "Integer-dtype numeric columns use Int64 nullable after decryption to handle NaN correctly, matching masker.py convention"
  - "decrypt_sheets applies reverse_text map to ALL non-numeric columns — columns added by LLM that are not in the map just pass through unchanged (rt.get(str(v), v))"

patterns-established:
  - "Pure function pattern: all core functions are import-safe with no side effects or Streamlit dependency"
  - "Cyrillic-safe JSON: always use ensure_ascii=False for user-visible keys/values"

requirements-completed: [OUT-01, OUT-02, OUT-03, DECR-01, DECR-02, DECR-03]

# Metrics
duration: 5min
completed: 2026-03-20
---

# Phase 3 Plan 1: Output + Decryption Engine Summary

**Pure output generators (xlsx/json download bytes) and decryption engine (pseudonym inversion + numeric divide) with 17 TDD tests, all green**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-03-20T07:40:31Z
- **Completed:** 2026-03-20T07:45:00Z
- **Tasks:** 2
- **Files modified:** 4 (all created new)

## Accomplishments

- `core/output.py`: three functions generating masked xlsx, mapping JSON (UTF-8 Cyrillic), and mapping xlsx with correctly-named sheets and columns
- `core/decryptor.py`: `load_mapping_json` with validation + None sentinel; `decrypt_sheets` with inverted text map, numeric divide-by-coeff, NaN passthrough, unknown-value passthrough
- Full TDD coverage: 8 output tests + 9 decryptor tests = 17 new tests; full suite at 49/49

## Task Commits

Each task was committed atomically:

1. **Task 1: Output generators with TDD** - `6f9f39d` (feat)
2. **Task 2: Decryption engine with TDD** - `ca6dc93` (feat)

_Note: TDD tasks each used RED (import error confirmed) then GREEN (all tests pass) cycle._

## Files Created/Modified

- `core/output.py` - Three pure output functions: generate_masked_xlsx, generate_mapping_json, generate_mapping_xlsx
- `core/decryptor.py` - Two pure decryption functions: load_mapping_json, decrypt_sheets
- `tests/test_output.py` - 8 tests covering xlsx structure, JSON encoding, Cyrillic literal output
- `tests/test_decryptor.py` - 9 tests covering text/numeric decryption, NaN, unknowns, multi-sheet, Int64 rounding

## Decisions Made

- `load_mapping_json` returns None both on JSON parse errors and when "text"/"numeric" keys are missing — callers in UI must check for None before calling `decrypt_sheets`
- `decrypt_sheets` iterates all columns: numeric columns in `numeric_map` get divide-by-coeff treatment; all other columns (whether in text mapping or not) get the reverse-text lookup with passthrough fallback — this correctly handles LLM-added columns
- Integer-dtype columns cast back to Int64 (nullable) after decryption to match masker.py's own Int64 convention and handle NaN in integer series

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- `core/output.py` and `core/decryptor.py` are ready to import in Streamlit UI (phase 03-02)
- Both modules have no Streamlit dependency — safe to unit-test and import in any context
- API surface is stable: 3 output functions + 2 decryption functions with clear signatures

---
*Phase: 03-output-decryption*
*Completed: 2026-03-20*
