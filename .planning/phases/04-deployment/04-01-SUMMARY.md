---
phase: 04-deployment
plan: "01"
subsystem: deployment
tags: [systemd, nginx, streamlit, deploy, infrastructure]
dependency_graph:
  requires: []
  provides: [deploy-configs, vm-setup-script, deploy-script]
  affects: [app-runtime]
tech_stack:
  added: []
  patterns: [systemd-service, nginx-reverse-proxy, rsync-deploy]
key_files:
  created:
    - deploy/enigma.service
    - deploy/enigma.nginx
    - deploy/setup-vm.sh
    - deploy/deploy.sh
  modified:
    - .streamlit/config.toml
decisions:
  - Streamlit config updated in-place; new keys maxMessageSize=300 and port=8501 added alongside existing headless=true
  - deploy.sh excludes .planning and deploy directories from rsync to keep VM app/ clean
  - setup-vm.sh runs entirely via SSH from local machine — no need to copy script to VM first
  - sudoers entry scoped to specific systemctl commands (restart + status enigma only) — minimal privilege
metrics:
  duration_minutes: 2
  completed_date: "2026-03-20"
  tasks_completed: 2
  files_created: 4
  files_modified: 1
---

# Phase 4 Plan 01: Deployment Configuration Files Summary

**One-liner:** Five production-ready deployment artifacts — systemd unit, nginx reverse proxy, updated Streamlit config, and SSH/rsync scripts — targeting VM 158.160.27.49 with 300MB upload limits and WebSocket support.

## What Was Built

All deployment configuration files needed to bring Enigma live on the VM. The approach: generate artifacts locally, copy to VM with scripts — zero manual config editing on the server.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Update Streamlit config and create systemd + nginx configs | 809455a | .streamlit/config.toml, deploy/enigma.service, deploy/enigma.nginx |
| 2 | Create VM setup and deploy scripts | afcdafc | deploy/setup-vm.sh, deploy/deploy.sh |

## Artifacts Produced

### .streamlit/config.toml (modified)
Updated `maxUploadSize` from 50 to 300, added `maxMessageSize = 300` and `port = 8501`. These values are synchronized with nginx `client_max_body_size 300m`.

### deploy/enigma.service
Systemd unit targeting `/home/enigma/venv/bin/streamlit` (absolute venv path — no shell activation needed). `Restart=always`, `RestartSec=5`, `MemoryMax=2G`, `Nice=10`. Runs as dedicated `enigma` user.

### deploy/enigma.nginx
Nginx reverse proxy: port 80 to 127.0.0.1:8501. WebSocket upgrade via `map $http_upgrade $connection_upgrade`. `proxy_buffering off` (required for Streamlit SSE). `proxy_read_timeout 300s` to survive long file processing. `client_max_body_size 300m`.

### deploy/setup-vm.sh
First-time VM provisioning in 7 steps: apt packages, dedicated user, app directory, Python 3.11 venv, systemd service install, nginx site enable, sudoers entry for enigma user. Runs all steps via SSH from local machine.

### deploy/deploy.sh
Incremental deploy in 4 steps: rsync with `--delete` (excludes .venv, __pycache__, .git, *.xlsx, .planning, deploy), pip install, systemctl restart, systemctl status check. One command from project root.

## Deviations from Plan

None — plan executed exactly as written. All acceptance criteria met verbatim.

## Self-Check

Files exist:
- [x] .streamlit/config.toml — confirmed, contains maxUploadSize=300, maxMessageSize=300, port=8501
- [x] deploy/enigma.service — confirmed, contains ExecStart=/home/enigma/venv/bin/streamlit, Restart=always
- [x] deploy/enigma.nginx — confirmed, contains proxy_buffering off, proxy_read_timeout 300s, client_max_body_size 300m
- [x] deploy/setup-vm.sh — confirmed, executable, contains useradd, python3.11 -m venv, systemctl enable enigma
- [x] deploy/deploy.sh — confirmed, executable, contains rsync -avz --delete with all required excludes

Commits exist:
- [x] 809455a — feat(04-01): add Streamlit config, systemd unit, and nginx reverse proxy config
- [x] afcdafc — feat(04-01): add VM setup and deploy scripts

## Self-Check: PASSED
