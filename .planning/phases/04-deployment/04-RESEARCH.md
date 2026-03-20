# Phase 4: Deployment - Research

**Researched:** 2026-03-20
**Domain:** Linux VM deployment — systemd + nginx + Streamlit
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- File upload limit: 300 MB (`maxUploadSize = 300` in `.streamlit/config.toml`, `client_max_body_size 300m` in nginx, `server.maxMessageSize = 300`)
- Systemd: `enigma.service` in `/etc/systemd/system/`, `Type=simple`, `Restart=always`, `RestartSec=5`, dedicated non-root user
- Nginx: port 80 (HTTP only, no TLS for v1), `proxy_pass http://127.0.0.1:8501`, WebSocket upgrade headers, `proxy_read_timeout 300s`
- Code transfer: `scp` or `rsync` (no Docker, no containers)
- Session isolation: Streamlit `session_state` only, no global variables (already enforced by architecture)
- VM: 158.160.27.49, SSH access, Python venv from `requirements.txt`

### Claude's Discretion

- Specific systemd resource limits (MemoryMax, Nice, CapabilityBoundingSet)
- Deploy script strategy (`deploy.sh` contents)
- Nginx logging configuration

### Deferred Ideas (OUT OF SCOPE)

- HTTPS/TLS (v2 when public access or auth is added)
- CI/CD pipeline (automated deploy on push)
- Monitoring/alerting/healthcheck endpoints (v2)
- Authorization (separate v2 phase)
</user_constraints>

---

## Summary

Phase 4 deploys the fully-built Enigma Streamlit application onto a Yandex Cloud VM (158.160.27.49) using the classic systemd + nginx pattern. The application uses no database, no secrets, no containers — just a Python venv, a systemd unit, and an nginx reverse proxy. All architectural decisions are already locked by the user.

The primary risk is WebSocket misconfiguration in nginx: Streamlit communicates over WebSocket, and the default nginx timeouts (60s) will terminate long-running file processing. The `proxy_read_timeout 300s` decision already addresses this. A secondary risk is the test suite currently failing 6/49 tests due to `xlsxwriter` missing from the system Python — these tests pass inside the project venv and will pass on the VM if the venv is correctly activated.

**Primary recommendation:** Follow the locked decisions exactly. The main implementation work is producing four files: `enigma.service`, the nginx site config, an updated `.streamlit/config.toml`, and a `deploy.sh` helper script. All are straightforward — no novel engineering required.

---

## Standard Stack

### Core

| Component | Version | Purpose | Why Standard |
|-----------|---------|---------|--------------|
| systemd | OS default (Ubuntu 22.04) | Process supervision, auto-restart | Linux standard for persistent services |
| nginx | Latest stable (1.24+) | Reverse proxy, WebSocket upgrade, file size limits | Standard HTTP gateway for Python web apps |
| Python venv | 3.11 (matches .venv on dev) | Isolated dependencies on VM | No pip collision with system Python |
| Streamlit | 1.55.0 (from requirements.txt) | App server on port 8501 | Already pinned |

### Supporting

| Component | Version | Purpose | When to Use |
|-----------|---------|---------|-------------|
| rsync | OS default | Incremental file sync to VM | Faster than scp for subsequent deploys |
| pytest | 8.3.5 (from requirements.txt) | Smoke test on VM after deploy | Run inside VM venv to verify install |

**Installation (on VM):**
```bash
# System packages
sudo apt-get update
sudo apt-get install -y nginx python3.11-venv python3.11-dev

# Project venv
python3.11 -m venv /home/enigma/venv
/home/enigma/venv/bin/pip install --upgrade pip
/home/enigma/venv/bin/pip install -r /home/enigma/app/requirements.txt
```

---

## Architecture Patterns

### Recommended Project Structure on VM

```
/home/enigma/
├── app/                    # project root (rsync target)
│   ├── app.py
│   ├── core/
│   ├── ui/
│   ├── views/
│   ├── tests/
│   ├── requirements.txt
│   └── .streamlit/
│       └── config.toml     # maxUploadSize=300, headless=true
└── venv/                   # Python virtualenv (not inside app/)
```

```
/etc/systemd/system/
└── enigma.service

/etc/nginx/sites-available/
└── enigma                  # symlinked to sites-enabled/

/var/log/nginx/
├── enigma_access.log
└── enigma_error.log
```

### Pattern 1: Systemd Service Unit

**What:** Runs `streamlit run app.py` as a systemd service under a dedicated user.
**When to use:** Any long-running Python server on Linux that must survive SSH disconnect and restart on crash.

```ini
# /etc/systemd/system/enigma.service
[Unit]
Description=Enigma — Streamlit Data Masking App
After=network.target

[Service]
Type=simple
User=enigma
Group=enigma
WorkingDirectory=/home/enigma/app
ExecStart=/home/enigma/venv/bin/streamlit run app.py \
    --server.port 8501 \
    --server.headless true
Restart=always
RestartSec=5
Environment=STREAMLIT_SERVER_HEADLESS=true
Environment=PYTHONUNBUFFERED=1

# Resource limits (Claude's Discretion)
MemoryMax=2G
Nice=10

[Install]
WantedBy=multi-user.target
```

**Key detail:** `ExecStart` uses the absolute path to the venv Python/streamlit binary directly. The venv does NOT need to be "activated" — using the binary path inside `venv/bin/` is equivalent. (HIGH confidence — verified pattern across multiple sources.)

### Pattern 2: Nginx Reverse Proxy with WebSocket Support

**What:** nginx proxies HTTP port 80 to Streamlit on 127.0.0.1:8501, upgrading WebSocket connections.
**When to use:** Every Streamlit deployment behind nginx.

```nginx
# /etc/nginx/sites-available/enigma
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 80;
    server_name 158.160.27.49;

    client_max_body_size 300m;

    access_log /var/log/nginx/enigma_access.log;
    error_log  /var/log/nginx/enigma_error.log warn;

    location / {
        proxy_pass         http://127.0.0.1:8501;
        proxy_http_version 1.1;

        proxy_set_header   Upgrade    $http_upgrade;
        proxy_set_header   Connection $connection_upgrade;
        proxy_set_header   Host       $host;
        proxy_set_header   X-Real-IP  $remote_addr;

        proxy_read_timeout  300s;
        proxy_send_timeout  300s;
        proxy_connect_timeout 60s;

        proxy_buffering off;
    }
}
```

**Critical:** `proxy_buffering off` is required for Streamlit. Buffered responses break the server-sent-events stream that Streamlit uses to push UI updates. The `map` block for `$connection_upgrade` is the idiomatic nginx pattern for WebSocket proxying.

### Pattern 3: .streamlit/config.toml (Updated)

```toml
[theme]
base = "light"

[server]
maxUploadSize = 300
maxMessageSize = 300
headless = true
port = 8501
```

**Current state:** `.streamlit/config.toml` has `maxUploadSize = 50` and `headless = true`. Both `maxUploadSize` and `maxMessageSize` must be raised to 300. `maxMessageSize` controls the WebSocket frame size — for large file uploads over WebSocket this must match `maxUploadSize`. (MEDIUM confidence — verified via Streamlit community forum; Streamlit docs confirm both settings exist in `[server]` section.)

### Pattern 4: Deploy Script

**What:** Shell script to sync code to VM and restart the service.

```bash
#!/bin/bash
# deploy.sh — run from local project root
set -euo pipefail

VM_USER="enigma"
VM_HOST="158.160.27.49"
VM_APP="/home/enigma/app"
VM_VENV="/home/enigma/venv"

echo "[1/4] Syncing code..."
rsync -avz --delete \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.git' \
    --exclude='*.xlsx' \
    --exclude='*.XLSX' \
    . "${VM_USER}@${VM_HOST}:${VM_APP}/"

echo "[2/4] Installing dependencies..."
ssh "${VM_USER}@${VM_HOST}" \
    "${VM_VENV}/bin/pip install -q -r ${VM_APP}/requirements.txt"

echo "[3/4] Restarting service..."
ssh "${VM_USER}@${VM_HOST}" \
    "sudo systemctl restart enigma"

echo "[4/4] Checking status..."
ssh "${VM_USER}@${VM_HOST}" \
    "sudo systemctl status enigma --no-pager"

echo "Deploy complete."
```

**Note:** `--exclude='*.xlsx'` prevents test data files (which are in the project root) from being uploaded to the VM. The `sudo systemctl restart` requires enigma user to have passwordless sudo for this specific command, configured via `/etc/sudoers.d/enigma`.

### Anti-Patterns to Avoid

- **Running Streamlit as root:** Streamlit would then run with full system access. Always use a dedicated unprivileged user.
- **Activating venv in ExecStart:** `source venv/bin/activate && streamlit run` does not work in systemd — use absolute path to `venv/bin/streamlit` directly.
- **Forgetting `proxy_buffering off`:** Without this, nginx buffers the response and Streamlit's live UI updates freeze.
- **Using `connection "upgrade"` (lowercase string):** Must use the `map` directive with variable `$connection_upgrade` — hardcoding `"upgrade"` causes WebSocket failures for non-WebSocket requests.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Process supervision | Custom restart loop | systemd `Restart=always` | Handles crashes, reboots, log rotation automatically |
| WebSocket proxying | Custom TCP proxy | nginx with upgrade headers | Battle-tested, handles connection lifecycle correctly |
| File size enforcement | In-app byte checking | nginx `client_max_body_size` + Streamlit `maxUploadSize` | Server-side enforcement before the app even runs |
| Session isolation | Custom state partitioning | Streamlit's built-in `session_state` | Each browser tab gets its own ScriptRunContext — this is guaranteed by Streamlit's architecture |

**Key insight:** The session isolation guarantee is architectural in Streamlit — each WebSocket connection creates an independent Python thread with its own `ScriptRunContext`. The only way sessions can leak is via Python module-level global variables (mutable dicts, lists defined outside any function). The current Enigma codebase uses no such globals — `state_keys.py` defines only string constants.

---

## Common Pitfalls

### Pitfall 1: WebSocket Timeout on Large File Processing

**What goes wrong:** nginx's default `proxy_read_timeout` is 60 seconds. Processing a 30K-row, 4-sheet Excel file with masking takes 5–20 seconds. Future larger files or slow VM may exceed 60s, killing the WebSocket mid-operation and showing "Connection lost" to the user.

**Why it happens:** nginx treats 60s of no data as a stale connection and closes it.

**How to avoid:** Set `proxy_read_timeout 300s` (already in locked decisions). Also set `proxy_send_timeout 300s`.

**Warning signs:** UI shows "Please wait..." indefinitely or "Connection lost" after exactly 60 seconds.

### Pitfall 2: 413 Request Entity Too Large from nginx vs Streamlit's Own Error

**What goes wrong:** nginx enforces `client_max_body_size` independently from Streamlit's `maxUploadSize`. If the two are not synchronized, a file that Streamlit allows may be rejected by nginx with HTTP 413, showing a confusing nginx error page rather than Streamlit's readable message.

**Why it happens:** nginx checks the request body size before it reaches Streamlit.

**How to avoid:** Both values locked at 300 MB. Verify both are applied after deploy.

**Warning signs:** Upload fails with a blank nginx error page (not a Streamlit UI message).

### Pitfall 3: Session State Leak via Module-Level Mutable State

**What goes wrong:** If any module defines a mutable object at module level (e.g., `CACHE = {}` outside a function), it is shared across ALL Streamlit sessions on the same server process.

**Why it happens:** Python imports are cached — module-level code runs once per process, not once per session.

**How to avoid:** Audit `core/`, `ui/`, `views/` for any mutable module-level variables. Only string constants (like `state_keys.py`) are safe. The current Enigma codebase is stateless by design — confirm during verification.

**Warning signs:** User A's uploaded file briefly visible to User B.

### Pitfall 4: xlsxwriter Missing from System Python

**What goes wrong:** Running `pytest` on the VM without activating the project venv causes 6 test failures (`ModuleNotFoundError: No module named 'xlsxwriter'`).

**Why it happens:** pytest is run against system Python instead of the venv.

**How to avoid:** Always run tests inside the venv: `/home/enigma/venv/bin/pytest tests/`.

**Warning signs:** `test_output.py` tests fail with ModuleNotFoundError.

### Pitfall 5: systemd Service Not Started on Reboot

**What goes wrong:** After a VM reboot, the service does not start automatically.

**Why it happens:** `systemctl enable` was never run after creating the unit file.

**How to avoid:** Run `sudo systemctl enable enigma` after initial setup.

**Warning signs:** App unavailable after VM reboot, `systemctl is-enabled enigma` shows `disabled`.

---

## Code Examples

### Verified Patterns from Official Sources

#### Enabling and Starting the Service

```bash
# After placing enigma.service in /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable enigma
sudo systemctl start enigma
sudo systemctl status enigma
```

#### Enabling the nginx Site

```bash
sudo ln -s /etc/nginx/sites-available/enigma /etc/nginx/sites-enabled/
sudo nginx -t          # test config syntax
sudo systemctl reload nginx
```

#### Creating the Dedicated User

```bash
sudo useradd --system --create-home --shell /bin/bash enigma
sudo chown -R enigma:enigma /home/enigma/app
```

#### Sudoers Entry for Deploy Script Restart

```
# /etc/sudoers.d/enigma
enigma ALL=(ALL) NOPASSWD: /bin/systemctl restart enigma, /bin/systemctl status enigma
```

#### Smoke Test on VM

```bash
# Run from /home/enigma/app after deploy
/home/enigma/venv/bin/pytest tests/ -q --ignore=tests/test_output.py
/home/enigma/venv/bin/pytest tests/test_output.py -q   # requires xlsxwriter in venv — will pass
```

#### Verify Session Isolation (Manual)

```bash
# Open two browser tabs to http://158.160.27.49
# Upload different files in each tab
# Confirm each tab sees only its own data
```

#### Verify File Size Limit

```bash
# Create a >50MB test file and upload it — should show readable error
# Create a ~290MB test file — should upload successfully
# Create a ~310MB test file — should be rejected by nginx with 413
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Gunicorn + Streamlit | Direct `streamlit run` + systemd | Streamlit always managed its own server | No WSGI layer needed |
| Activating venv in ExecStart | Absolute path to `venv/bin/python` | Long-standing systemd best practice | More reliable, no shell activation quirks |
| `proxy_connect_timeout` for timeouts | `proxy_read_timeout` for WebSocket | WebSocket-specific nginx knowledge | File processing time is read timeout, not connect |

---

## Open Questions

1. **VM RAM available**
   - What we know: VM is 158.160.27.49, SSH access confirmed
   - What's unclear: Total RAM. A 300MB xlsx file loaded into pandas as 4 DataFrames could use 1-3 GB RAM. The `MemoryMax=2G` in the service unit is a placeholder.
   - Recommendation: First task should SSH to VM and run `free -h` to confirm available memory before setting `MemoryMax`. If RAM < 4GB, consider whether concurrent users risk OOM.

2. **Python version on VM**
   - What we know: Dev environment uses Python 3.11 (.venv)
   - What's unclear: What Python version is default on the VM's Ubuntu installation
   - Recommendation: SSH to VM and check `python3 --version`. If not 3.11, install `python3.11` and `python3.11-venv` before creating the venv.

3. **Whether 158.160.27.49 already has nginx installed**
   - What we know: VM exists and has SSH access
   - What's unclear: Current state of the VM (fresh or has existing services)
   - Recommendation: Wave 1 should SSH and audit: `nginx -v`, `systemctl list-units`, `df -h`.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.3.5 |
| Config file | `pytest.ini` (testpaths = tests) |
| Quick run command | `/home/enigma/venv/bin/pytest tests/ -q` |
| Full suite command | `/home/enigma/venv/bin/pytest tests/ -v` |

### Phase Requirements to Test Map

This phase has no dedicated requirement IDs. The success criteria are infrastructure/operational:

| Success Criterion | Test Type | Automated Command | Notes |
|-------------------|-----------|-------------------|-------|
| App reachable at VM IP | smoke | `curl -s -o /dev/null -w "%{http_code}" http://158.160.27.49/` returns 200 | Manual verification |
| App survives SSH disconnect | operational | `sudo systemctl is-active enigma` returns `active` | After SSH disconnect and reconnect |
| 30K-row file processes < 30s | performance | Manual: upload real file, time in browser | No automated timing test exists |
| Two parallel sessions isolated | integration | Manual: two browsers, upload different files | No automated multi-session test |
| >50MB file shows readable error | smoke | Manual: attempt upload of oversized file | Readable = Streamlit UI message, not nginx 413 |

### Sampling Rate

- **Per task commit:** `/home/enigma/venv/bin/pytest tests/ -q` (43 tests, ~0.4s locally)
- **Per wave merge:** Full suite + manual smoke checks
- **Phase gate:** Full suite green + all 4 manual checks verified before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] No `deploy.sh` exists yet — to be created in Wave 1
- [ ] No `enigma.service` file exists yet — to be created in Wave 1
- [ ] No nginx config file exists yet — to be created in Wave 1
- [ ] `.streamlit/config.toml` needs update (maxUploadSize 50 → 300, add maxMessageSize = 300)

*(Existing test infrastructure covers all unit/integration tests. No new test files needed for deployment phase — verification is operational/manual.)*

---

## Sources

### Primary (HIGH confidence)

- systemd official documentation — `Type=simple`, `Restart=always`, `ExecStart` absolute path patterns
- nginx official docs — `proxy_read_timeout`, `client_max_body_size`, WebSocket `map $http_upgrade` pattern
- Streamlit community forum (verified against multiple threads) — WebSocket nginx configuration, `maxUploadSize`/`maxMessageSize` settings
- Project source: `requirements.txt`, `.streamlit/config.toml`, `pytest.ini` — current state confirmed by direct file read

### Secondary (MEDIUM confidence)

- Streamlit discuss thread "How to use Streamlit with Nginx?" — WebSocket header requirements confirmed by multiple users
- WebSearch: systemd venv ExecStart patterns — consistent across multiple sources (gists, official Adafruit docs, Medium articles)
- Streamlit architecture docs (DeepWiki mirror) — session isolation via ScriptRunContext confirmed

### Tertiary (LOW confidence)

- Memory usage estimate (1–3 GB for 300MB xlsx) — derived from pandas general knowledge, not benchmarked against this specific app

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — All components (systemd, nginx, Python venv) are decades-stable Linux infrastructure
- Architecture patterns: HIGH — systemd unit and nginx config are exact locked decisions from CONTEXT.md
- Pitfalls: MEDIUM — WebSocket timeout and session isolation pitfalls verified via Streamlit community; OOM estimate is LOW confidence
- Validation: HIGH — existing pytest suite confirmed running (43/49 pass locally; 6 failures are environment-specific, not code bugs)

**Research date:** 2026-03-20
**Valid until:** 2026-06-20 (stable infrastructure, 90-day validity)
