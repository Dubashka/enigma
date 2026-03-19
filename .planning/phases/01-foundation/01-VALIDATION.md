---
phase: 1
slug: foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-19
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | none — Wave 0 installs |
| **Quick run command** | `python -m pytest tests/ -x -q` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | LOAD-01 | integration | `python -m pytest tests/test_upload.py::test_xlsx_multisheet -x` | ❌ W0 | ⬜ pending |
| 01-01-02 | 01 | 1 | LOAD-02 | integration | `python -m pytest tests/test_upload.py::test_csv_upload -x` | ❌ W0 | ⬜ pending |
| 01-01-03 | 01 | 1 | LOAD-03 | unit | `python -m pytest tests/test_parser.py::test_structure_preserved -x` | ❌ W0 | ⬜ pending |
| 01-01-04 | 01 | 1 | UI-01 | manual | visual inspection | N/A | ⬜ pending |
| 01-01-05 | 01 | 1 | UI-02 | integration | `python -m pytest tests/test_session.py::test_stateless -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_upload.py` — stubs for LOAD-01, LOAD-02
- [ ] `tests/test_parser.py` — stubs for LOAD-03 (structure preservation)
- [ ] `tests/test_session.py` — stubs for UI-02 (stateless)
- [ ] `tests/conftest.py` — shared fixtures (sample xlsx/csv files)
- [ ] `pip install pytest` — framework not yet in project

*If none: "Existing infrastructure covers all phase requirements."*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| All UI text in Russian | UI-01 | Visual/language check | Open app, verify every label, button, header, error message is in Russian |
| Tabs show sheet names | LOAD-01 | Visual layout | Upload multi-sheet xlsx, verify st.tabs shows correct sheet names |
| Preview shows 20 rows | LOAD-01 | Visual count | Upload file, count rows in preview table |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
