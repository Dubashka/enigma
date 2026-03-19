---
phase: 3
slug: output-decryption
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-20
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (already configured) |
| **Config file** | pytest.ini |
| **Quick run command** | `.venv2/bin/python -m pytest tests/ -x -q` |
| **Full suite command** | `.venv2/bin/python -m pytest tests/ -v` |
| **Estimated runtime** | ~1 second |

---

## Sampling Rate

- **After every task commit:** Run `.venv2/bin/python -m pytest tests/ -x -q`
- **After every plan wave:** Run `.venv2/bin/python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 2 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | OUT-01 | unit | `pytest tests/test_output.py -k xlsx` | ❌ W0 | ⬜ pending |
| 03-01-02 | 01 | 1 | OUT-02 | unit | `pytest tests/test_output.py -k json` | ❌ W0 | ⬜ pending |
| 03-01-03 | 01 | 1 | OUT-03 | unit | `pytest tests/test_output.py -k mapping_excel` | ❌ W0 | ⬜ pending |
| 03-02-01 | 02 | 1 | DECR-01, DECR-02, DECR-03 | unit | `pytest tests/test_decryptor.py` | ❌ W0 | ⬜ pending |
| 03-03-01 | 03 | 2 | OUT-01..03 | visual | manual — verify download buttons | N/A | ⬜ pending |
| 03-03-02 | 03 | 2 | DECR-01..03 | visual | manual — verify decryption page | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_output.py` — stubs for OUT-01, OUT-02, OUT-03
- [ ] `tests/test_decryptor.py` — stubs for DECR-01, DECR-02, DECR-03

*Existing infrastructure (pytest, conftest.py) covers framework needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Download buttons work in browser | OUT-01..03 | st.download_button requires browser | Upload file → mask → click download buttons → verify files |
| Decryption page flow | DECR-01..03 | Full UI flow | Upload masked file + JSON → click decrypt → verify preview + download |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 2s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
