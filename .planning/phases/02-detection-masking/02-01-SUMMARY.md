---
phase: 02-detection-masking
plan: 01
subsystem: core
tags: [pandas, keyword-detection, text-masking, numeric-masking, tdd, pytest]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: parse_upload() returning dict[str, DataFrame], pytest infrastructure, session state machine
provides:
  - core/detector.py with detect_sensitive_columns() and classify_column_type()
  - core/masker.py with mask_sheets(), build_text_mapping(), build_numeric_mapping()
  - core/state_keys.py extended with Phase 2 keys (SELECTED_COLUMNS, MASK_CONFIG, MAPPING, MASKED_SHEETS, STATS)
  - 21 unit tests covering DETC-01, DETC-03, MASK-01..04
affects:
  - 02-02 (UI plan consuming detector/masker engine)
  - 03 (download/export plan)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Single-pass text mapping build before sheet iteration (cross-sheet consistency guarantee)"
    - "Vectorized masking via pd.Series.map() — no iterrows()"
    - "Dual-keyword classification: dtype + column name substring match for numeric ID detection"
    - "NFC normalization + quote removal for Russian company name variant deduplication"
    - "Excel-column-style labels (A, B, ..., Z, AA, AB) for pseudonym indices"
    - "TDD RED-GREEN cycle per module with pytest"

key-files:
  created:
    - core/detector.py
    - core/masker.py
    - tests/test_detector.py
    - tests/test_masker.py
  modified:
    - core/state_keys.py
    - tests/conftest.py

key-decisions:
  - "Single global mapping dict and counter dict built before any sheet is processed — prerequisite for cross-sheet consistency"
  - "Prefix derivation: skip service words (имя, наименование, название, номер, рабочего), take first remaining word, normalize genitive suffix -ия -> -ие"
  - "Integer columns use nullable Int64 after numeric masking (round().astype('Int64')) to handle NaN and avoid float noise"
  - "NUMERIC_ID_KEYWORDS classification overrides dtype: int64 column with 'документ'/'договор'/etc. in name gets text masking, not coefficient"
  - "Numeric proportions test uses float column — integer rounding makes strict proportional equality non-deterministic for small values"

patterns-established:
  - "Pattern: Core business logic in pure Python (no Streamlit imports) — core/ modules are UI-independent"
  - "Pattern: mask_config dict[sheet, dict[col, 'text'|'numeric']] as the interface between detector and masker"
  - "Pattern: mask_sheets() returns (masked_sheets, mapping, stats) tuple — all results in one call"

requirements-completed: [DETC-01, DETC-03, MASK-01, MASK-02, MASK-03, MASK-04]

# Metrics
duration: 25min
completed: 2026-03-19
---

# Phase 2 Plan 01: Detection and Masking Engine Summary

**Keyword-based column detector and two-phase masking engine (text pseudonyms with auto-prefix + numeric coefficients) with 21 unit tests covering cross-sheet consistency and numeric ID classification**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-03-19T20:15:00Z
- **Completed:** 2026-03-19T20:40:00Z
- **Tasks:** 2 (both TDD: RED + GREEN)
- **Files modified:** 6

## Accomplishments

- `core/detector.py`: keyword detection with 20+ SENSITIVE_KEYWORDS and 16 NUMERIC_ID_KEYWORDS; case-insensitive substring matching; dtype + name-keyword dual classification
- `core/masker.py`: single-pass cross-sheet text mapping build; vectorized apply via Series.map(); integer dtype preservation; NaN skipping; stats counting
- 21 tests pass (9 detector + 12 masker) on top of 11 existing parser tests — 32 total, zero regressions

## Task Commits

Each task was committed atomically (TDD = 2 commits per task):

1. **Task 1 RED — detector tests (failing)** - `9553f42` (test)
2. **Task 1 GREEN — detector + state keys implementation** - `c930777` (feat)
3. **Task 2 RED — masker tests (failing)** - `27fb1c9` (test)
4. **Task 2 GREEN — masker implementation** - `9cf61e4` (feat)

_Note: TDD tasks each have RED (test) + GREEN (implementation) commits._

## Files Created/Modified

- `core/detector.py` — SENSITIVE_KEYWORDS, NUMERIC_ID_KEYWORDS, detect_sensitive_columns(), classify_column_type()
- `core/masker.py` — _normalize, _derive_prefix, _index_to_label, build_text_mapping, build_numeric_mapping, apply_text_masking, apply_numeric_masking, mask_sheets
- `core/state_keys.py` — added SELECTED_COLUMNS, MASK_CONFIG, MAPPING, MASKED_SHEETS, STATS
- `tests/test_detector.py` — 9 unit tests for detection and classification
- `tests/test_masker.py` — 12 unit tests for masking engine
- `tests/conftest.py` — added sample_detection_sheets fixture

## Decisions Made

- **Cross-sheet consistency via single-pass mapping:** The text mapping and counters dict are created once before the sheet loop, then shared across all sheets. This is the critical guarantee that "ООО Альфа" on Sheet1 and Sheet2 gets the same pseudonym.
- **Prefix derivation algorithm:** Skip service words (имя, наименование, название, номер, рабочего), take first remaining word, normalize genitive suffix (-ия -> -ие). Gives "Предприятие" from "Имя предприятия", "Автор" from "Автор изменения".
- **Integer masking via Int64:** After multiplying integer series by float coefficient, result.round().astype("Int64") converts back to nullable integer, preserving dtype without float noise.
- **Proportion test uses floats:** Testing proportions with integer columns is non-deterministic (rounding at boundaries can change ratios for small values like 10, 15). Float columns give exact proportional preservation.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Prefix derivation test mismatch — "Автор изменения" expected "Автор" not "Изменения"**
- **Found during:** Task 2 GREEN (first test run)
- **Issue:** Plan spec says `_derive_prefix("Автор изменения") returns "Автор"` but implementation took last word. For "Автор изменения", last word "изменения" capitalized gives "Изменения".
- **Fix:** Changed `_derive_prefix` to take FIRST remaining word (after skipping service words), not last. This matches "Автор изменения" -> "Автор" and "Имя предприятия" -> "Предприятие" (after genitive suffix normalization).
- **Files modified:** core/masker.py, tests/test_masker.py
- **Verification:** All 12 masker tests pass
- **Committed in:** 9cf61e4

**2. [Rule 1 - Bug] Numeric proportions test failed non-deterministically with integer rounding**
- **Found during:** Task 2 GREEN (full suite run)
- **Issue:** Proportions test used integer column [10, 20, 30]; random multiplier ~0.526 gives [5, 11, 16] where 5/11 ≠ 10/20 (rounding at boundaries)
- **Fix:** Changed test to use float column [1000.0, 2000.0, 3000.0] where round(2) preserves proportions exactly
- **Files modified:** tests/test_masker.py
- **Verification:** 32 tests pass deterministically across multiple runs
- **Committed in:** 9cf61e4

---

**Total deviations:** 2 auto-fixed (both Rule 1 — bug in test/implementation alignment)
**Impact on plan:** Both fixes necessary for correctness. No scope creep.

## Issues Encountered

None beyond the two auto-fixed deviations above.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- `core/detector.py` and `core/masker.py` are ready for Phase 2 Plan 02 (UI layer)
- `mask_config` dict format (`{sheet: {col: "text"|"numeric"}}`) is the interface between detector, checkbox UI, and masker
- `mask_sheets()` returns `(masked_sheets, mapping, stats)` — all results needed for Phase 2 Plan 02 UI rendering
- Zero new dependencies added; all from Phase 1 stack (pandas, stdlib random/unicodedata/re)

---
*Phase: 02-detection-masking*
*Completed: 2026-03-19*
