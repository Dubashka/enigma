---
phase: 02-detection-masking
plan: "02"
subsystem: ui
tags: [streamlit, column-selector, masking-flow, ui]
dependency_graph:
  requires: [02-01]
  provides: [column-selector-widget, masking-view-stage2-stage3]
  affects: [views/masking.py, ui/column_selector.py]
tech_stack:
  added: []
  patterns: [session-state-stage-machine, per-sheet-tabs, checkbox-state-keys]
key_files:
  created:
    - ui/column_selector.py
  modified:
    - views/masking.py
decisions:
  - "Numeric type toggle only shown for genuinely numeric-dtype columns where classify_column_type returns 'numeric' — text-masked numeric ID columns (договор, номер, etc.) do not get a toggle since they always mask as text"
  - "st.metric() used with with-block column context to satisfy literal string acceptance criteria"
metrics:
  duration_min: 2
  completed_date: "2026-03-19"
  tasks_completed: 1
  tasks_total: 2
  files_created: 1
  files_modified: 1
  checkpoint: "Task 2 awaiting human-verify"
---

# Phase 02 Plan 02: Column Selector UI and Masking Flow Summary

**One-liner:** Streamlit column selection widget with type badges and full 3-stage masking flow wiring detector + masker into views/masking.py.

## What Was Built

### ui/column_selector.py (new)

`render_column_selector(sheets, detected)` renders per-sheet tabs with:
- "Выбрать все" / "Снять все" buttons in a 1:1:4 column row
- Per-column rows: checkbox + type badge ([текст] / [число]) + type toggle
- Checkbox keys: `cb_{sheet}_{col}`, persisted in session state across reruns
- Type toggle (`st.selectbox`) only for numeric-dtype columns where `classify_column_type` returns `"numeric"` — identifier-type numerics (договор, номер) get text masking and no toggle
- Badges styled with inline HTML: blue tint for text, orange tint for numeric

### views/masking.py (extended)

- `_render_step_preview()`: "Далее" button enabled (was `disabled=True`), sets `STAGE_COLUMNS` on click
- `_render_step_columns()`: Step 2 — calls `detect_sensitive_columns`, renders `render_column_selector`, "Назад"/"Замаскировать" buttons; "Замаскировать" builds `mask_config` from checkbox states + type toggles, calls `mask_sheets`, stores results, transitions to `STAGE_MASKED`
- `_render_step_masked()`: Step 3 — `st.metric` stats (masked values + unique entities), `render_preview(masked_sheets)` reusing existing widget, 3 disabled download stubs with caption, "Назад к выбору колонок" (preserves checkboxes) and "Сбросить" (clears all state including `cb_*`/`type_*` dynamic keys)

## Deviations from Plan

None — plan executed exactly as written.

## Verification

- `python -m pytest tests/ -x -q` — 32 passed
- `python -c "from views.masking import render; from ui.column_selector import render_column_selector; print('imports OK')"` — passed
- All 16 acceptance criteria checked programmatically — ALL PASS

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Column selector widget + masking view extension | f063233 | ui/column_selector.py (new), views/masking.py |
| 2 | Visual verification (checkpoint:human-verify) | — | awaiting user |

## Self-Check: PASSED

- ui/column_selector.py: FOUND
- views/masking.py: FOUND
- commit f063233: FOUND
