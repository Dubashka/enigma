# Stack Research

**Domain:** Streamlit data masking/anonymization web app for tabular (Excel/CSV) data
**Researched:** 2026-03-19
**Confidence:** HIGH (core stack); MEDIUM (deployment patterns)

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.11+ | Runtime | pandas 3.0.1 requires Python 3.11+; 3.12 is the sweet spot for performance and compatibility |
| Streamlit | 1.55.0 | UI framework | The only mature option for data-focused Python web apps without needing frontend skills; stateless-by-default fits the no-server-storage requirement |
| pandas | 3.0.1 | DataFrame operations, reading/writing Excel/CSV, in-memory data manipulation | Industry standard for tabular data in Python; tight openpyxl integration via read_excel/to_excel; handles multi-sheet Excel natively |
| openpyxl | 3.1.5 | Excel read/write engine (used under pandas' hood + directly for structure preservation) | Required by pandas as Excel engine; also needed directly when writing back Excel with preserved sheet structure, formatting hints ignored by pandas |
| Faker | 40.11.0 | NOT used for pseudonym generation (see note) | — |

**Note on Faker:** Faker generates plausible fake human names/companies/emails, which is excellent for NLP or general anonymization. For this project, the requirement is deterministic column-prefixed pseudonyms ("Предприятие A", "Предприятие B"), not realistic-looking fake names. Faker adds 30+ MB and complexity for no gain here. Use a plain Python counter-based mapping instead.

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| numpy | 2.x (comes with pandas) | Numeric perturbation — multiplying columns by a per-file random scalar in [0.5, 1.5] | Already available as pandas dependency; use `np.random.uniform(0.5, 1.5)` for the scalar coefficient |
| xlsxwriter | 3.2.9 | Alternative Excel write engine | Only if you need cell formatting (colors, bold headers) in the output masked file. openpyxl write engine is simpler for plain data; XlsxWriter is faster for write-only large files |
| python-dotenv | 1.x | Environment config for deployment (port, base path) | Use if you add any config that varies between dev and prod VM |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| uv | Fast Python package manager and virtualenv | Use instead of pip+venv; `uv venv && uv pip install -r requirements.txt` is significantly faster on fresh VM deploys |
| systemd | Process management on VM | Run Streamlit as a systemd service; handles auto-restart on crash and boot |
| nginx | Reverse proxy | Sit in front of Streamlit (default port 8501); required to forward WebSocket upgrade headers (`Upgrade`, `Connection`); also provides HTTPS termination point |

## Installation

```bash
# On the VM (Ubuntu/Debian)
python3.12 -m pip install uv
uv venv .venv
source .venv/bin/activate

# Core
uv pip install streamlit==1.55.0 pandas==3.0.1 openpyxl==3.1.5

# Supporting
uv pip install xlsxwriter==3.2.9

# Dev (local only)
uv pip install pytest ruff
```

**requirements.txt (minimal):**
```
streamlit==1.55.0
pandas==3.0.1
openpyxl==3.1.5
xlsxwriter==3.2.9
```

numpy is included automatically as a pandas dependency — do not pin it separately unless there is a conflict.

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| openpyxl (read engine) | calamine (python-calamine) | If read performance on very large xlsx files is critical; calamine uses a Rust backend and is ~3x faster to read. pandas 2.2+ supports it via `engine='calamine'`. Downside: write is not supported, so you still need openpyxl for output |
| openpyxl (write engine) | xlsxwriter | When writing large files with formatting; XlsxWriter is write-only but faster. For this project openpyxl handles the typical load (tens of thousands of rows); switch only if profiling shows write bottlenecks |
| Plain counter-based pseudonymizer | Faker | If the requirement shifts to generating realistic-looking names (e.g., for sharing with external parties who should not realize data is masked); Faker 40.11.0 has `locale='ru_RU'` support for Russian names |
| systemd + nginx | Docker + nginx | If the team wants containerized deploys in future; for a single-VM internal tool, systemd is simpler and has no container overhead |
| Streamlit session_state | Redis / server-side store | Only needed if multiple concurrent users must share state or if files exceed 200 MB (session_state keeps data in-process memory per session; fine for the stated use case) |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| pandas 2.x | pandas 3.0 (February 2026) is now the stable release; 2.x is in maintenance. Copy-on-Write became default in 3.0 — any code written against 3.0 won't silently mutate DataFrames, which is safer for masking logic | pandas 3.0.1 |
| xlrd | xlrd 2.0+ dropped support for .xlsx; only reads legacy .xls (Excel 97-2003). Many tutorials still reference it. It will raise `XLRDError` on any modern .xlsx file | openpyxl |
| Streamlit Cloud (community) | Free tier has 1 GB memory limit and puts apps to sleep after inactivity — not suitable for internal corporate use with sensitive data | Self-hosted on the provided VM |
| Faker for pseudonyms | Adds 30 MB dependency, requires locale tuning for Russian names, and produces names like "Иванов Иван" which could collide with real names in the dataset — defeating the purpose of masking | Counter-based mapping: `{original_value: f"{column_prefix}_{chr(65 + i)}"}` |
| pickle for mapping persistence | pickle is not human-readable; the requirement explicitly calls for JSON + Excel output | json.dumps() for JSON, openpyxl/pandas for Excel mapping |

## Stack Patterns by Variant

**For masking text columns (consistent cross-sheet pseudonyms):**
- Use a single Python `dict` as the global mapping store, built during the first pass over all sheets
- Key: `(column_name, original_value)` — namespaced by column so "Предприятие A" and "Сотрудник A" can coexist
- Or: a flat dict keyed by `original_value` if cross-column consistency is desired (a contractor name appearing in two columns gets the same pseudonym)
- Populate lazily during the masking loop; serialize to JSON afterward

**For masking numeric columns (proportional perturbation):**
- Generate ONE random scalar `k = np.random.uniform(0.5, 1.5)` per file (not per column)
- Apply: `df[col] = df[col] * k` — this preserves inter-column and inter-row ratios within a column
- Store `k` in the mapping JSON so decryption can reverse it: `original = masked / k`
- If per-column scalars are needed for finer control, generate `k` per column but still seed consistently

**For multi-sheet Excel read:**
```python
import pandas as pd

# Returns dict of {sheet_name: DataFrame}
sheets = pd.read_excel("file.xlsx", sheet_name=None, engine="openpyxl")
```

**For writing multi-sheet Excel output:**
```python
import openpyxl
# Use ExcelWriter context manager to preserve sheet order
with pd.ExcelWriter("masked.xlsx", engine="openpyxl") as writer:
    for sheet_name, df in masked_sheets.items():
        df.to_excel(writer, sheet_name=sheet_name, index=False)
```

**For Streamlit stateless architecture:**
- Store the uploaded file bytes and derived DataFrames in `st.session_state`
- Never write to disk (use `io.BytesIO` for in-memory Excel generation)
- Use `st.download_button` with a callable (supported since Streamlit 1.36+) for on-demand file generation without pre-generating the file on every rerun

**For VM deployment (systemd + nginx):**
```ini
# /etc/systemd/system/enigma.service
[Unit]
Description=Enigma Data Masking App
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/enigma
ExecStart=/home/ubuntu/enigma/.venv/bin/streamlit run app.py --server.port 8501 --server.headless true
Restart=always

[Install]
WantedBy=multi-user.target
```

```nginx
# /etc/nginx/sites-available/enigma
server {
    listen 80;
    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
```

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| pandas 3.0.1 | Python 3.11–3.14 | Requires Python 3.11+ (hard requirement, not advisory) |
| pandas 3.0.1 | openpyxl 3.1.5 | No known conflicts; openpyxl is the recommended engine |
| streamlit 1.55.0 | pandas 3.0.x | Compatible; Streamlit's st.dataframe renders pandas 3.0 DataFrames correctly |
| openpyxl 3.1.5 | xlsxwriter 3.2.9 | Do not use both as write engines in the same ExcelWriter — pick one per write operation |
| Faker 40.11.0 | Python 3.10+ | Hard requirement; not needed for this project but noted for future reference |

## Sources

- [streamlit · PyPI](https://pypi.org/project/streamlit/) — confirmed version 1.55.0 (March 3, 2026) — HIGH confidence
- [openpyxl · PyPI](https://pypi.org/project/openpyxl/) — confirmed version 3.1.5 (June 28, 2024) — HIGH confidence
- [pandas · PyPI](https://pypi.org/project/pandas/) — confirmed version 3.0.1 (February 17, 2026), Python 3.11+ requirement — HIGH confidence
- [Faker · PyPI](https://pypi.org/project/Faker/) — confirmed version 40.11.0 (March 13, 2026) — HIGH confidence
- [xlsxwriter · PyPI](https://pypi.org/project/xlsxwriter/) — confirmed version 3.2.9 (September 16, 2025) — HIGH confidence
- [Streamlit deployment with nginx](https://discuss.streamlit.io/t/streamlit-deployment-with-nginx/111676) — WebSocket headers pattern — MEDIUM confidence
- [Streamlit 2025 release notes](https://docs.streamlit.io/develop/quick-reference/release-notes/2025) — download_button callable support, session_state architecture — MEDIUM confidence
- [pandas 2.3.0 whatsnew](https://pandas.pydata.org/docs/dev/whatsnew/v2.3.0.html) — calamine engine, copy-on-write default — MEDIUM confidence

---
*Stack research for: Streamlit data masking/anonymization app (Энигма)*
*Researched: 2026-03-19*
