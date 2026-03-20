---
phase: 4
slug: deployment
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-20
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3.5 |
| **Config file** | none (pytest discovers tests/ automatically) |
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
| 04-01-01 | 01 | 1 | INFRA-config | config | `grep maxUploadSize .streamlit/config.toml` | ✅ | ⬜ pending |
| 04-01-02 | 01 | 1 | INFRA-systemd | infra | `systemctl is-active enigma` (on VM) | ❌ W0 | ⬜ pending |
| 04-01-03 | 01 | 1 | INFRA-nginx | infra | `curl -s http://158.160.27.49/ \| grep Enigma` (on VM) | ❌ W0 | ⬜ pending |
| 04-01-04 | 01 | 1 | INFRA-deploy | script | `test -f deploy.sh` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- Existing test infrastructure covers application logic (49 tests)
- Phase 4 is infrastructure — most verification is operational (systemctl, curl, browser)
- No new pytest tests needed — verification is manual/operational

*Existing infrastructure covers all phase requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| App accessible via nginx | SC-1 | Requires VM network access | `curl http://158.160.27.49/` returns Streamlit HTML |
| App survives SSH disconnect | SC-1 | Requires SSH session management | SSH, start service, disconnect, verify still running |
| 30K row file < 30s | SC-2 | Requires real test file + timing | Upload "Данные для маскирования_13.03.xlsx", measure time |
| Session isolation | SC-3 | Requires two browsers | Open two browsers, upload different files, verify no cross-contamination |
| File size error message | SC-4 | Requires uploading >300MB file | Upload >300MB file, verify readable error instead of crash |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
