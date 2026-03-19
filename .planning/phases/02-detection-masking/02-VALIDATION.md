---
phase: 2
slug: detection-masking
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-19
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | pytest.ini (from Phase 1) |
| **Quick run command** | `python -m pytest tests/ -x -q` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | DETC-01 | unit | `python -m pytest tests/test_detector.py::test_keyword_detection -x` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | DETC-03 | unit | `python -m pytest tests/test_detector.py::test_type_classification -x` | ❌ W0 | ⬜ pending |
| 02-01-03 | 01 | 1 | MASK-01 | unit | `python -m pytest tests/test_masker.py::test_text_pseudonym -x` | ❌ W0 | ⬜ pending |
| 02-01-04 | 01 | 1 | MASK-02 | unit | `python -m pytest tests/test_masker.py::test_numeric_coefficient -x` | ❌ W0 | ⬜ pending |
| 02-01-05 | 01 | 1 | MASK-03 | integration | `python -m pytest tests/test_masker.py::test_cross_sheet_consistency -x` | ❌ W0 | ⬜ pending |
| 02-01-06 | 01 | 1 | MASK-04 | unit | `python -m pytest tests/test_masker.py::test_identifier_as_text -x` | ❌ W0 | ⬜ pending |
| 02-02-01 | 02 | 2 | DETC-02 | manual | visual inspection | N/A | ⬜ pending |
| 02-02-02 | 02 | 2 | UI-01 | manual | visual inspection | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_detector.py` — stubs for DETC-01, DETC-03
- [ ] `tests/test_masker.py` — stubs for MASK-01, MASK-02, MASK-03, MASK-04
- [ ] `tests/conftest.py` — extend fixtures with sample DataFrames for masking

*Existing pytest infrastructure from Phase 1 covers framework needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Checkboxes show detected columns pre-checked | DETC-02 | Streamlit widget rendering | Upload real file, verify sensitive columns are checked |
| Type badges [текст]/[число] display correctly | DETC-03 | Visual layout | Check badges next to each checkbox on column selection |
| "Выбрать все" / "Снять все" buttons work | DETC-02 | Interactive UI | Click buttons, verify all checkboxes toggle |
| Превью замаскированных данных on Шаг 3 | MASK-01 | Visual rendering | Verify pseudonyms appear in preview table |
| Кнопка "Назад" returns to column selection | UI | Navigation flow | Click back, verify checkboxes preserved |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
