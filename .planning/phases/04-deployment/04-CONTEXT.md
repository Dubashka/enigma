# Phase 4: Deployment - Context

**Gathered:** 2026-03-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Деплой приложения на VM (158.160.27.49) через systemd + nginx reverse proxy. Hardening производительности на реальных данных. Приложение должно оставаться запущенным после disconnect SSH, обслуживать параллельные сессии без утечки данных и обрабатывать файлы до 300 МБ.

</domain>

<decisions>
## Implementation Decisions

### Лимит загрузки файлов
- Увеличить maxUploadSize в `.streamlit/config.toml` с 50 до 300 МБ
- В nginx конфиге: `client_max_body_size 300m`
- Streamlit `server.maxMessageSize` тоже выставить на 300 (для WebSocket frame)

### Systemd service
- Unit-файл `enigma.service` в `/etc/systemd/system/`
- `Type=simple`, `Restart=always`, `RestartSec=5`
- `WorkingDirectory` указывает на директорию проекта на VM
- `ExecStart` запускает streamlit через venv Python
- `Environment="STREAMLIT_SERVER_HEADLESS=true"`
- User — выделенный непривилегированный пользователь (не root)

### Nginx reverse proxy
- Слушает на порту 80 (HTTP) — внутренняя сеть, TLS не требуется для v1
- `proxy_pass http://127.0.0.1:8501`
- WebSocket upgrade для Streamlit (`Upgrade`, `Connection` headers)
- `proxy_read_timeout 300s` — для обработки больших файлов
- `client_max_body_size 300m` — синхронизировано с Streamlit

### Структура деплоя
- Код копируется на VM через `scp` или `rsync`
- venv создаётся на VM из `requirements.txt`
- Конфигурационные файлы (.streamlit/config.toml) входят в проект
- Никаких Docker/контейнеров — прямой деплой через systemd

### Изоляция сессий
- Streamlit по умолчанию изолирует session_state между пользователями — проверяем двумя параллельными браузерами
- Никаких глобальных переменных вне session_state — уже обеспечено архитектурой

### Обработка ошибок при превышении лимита
- Streamlit сам показывает ошибку при превышении maxUploadSize — проверяем, что сообщение читаемо
- Nginx вернёт 413 при превышении client_max_body_size — Streamlit покажет ошибку соединения

### Claude's Discretion
- Конкретные параметры systemd (limits, nice, capabilities)
- Стратегия обновления кода на VM (скрипт deploy.sh)
- Настройки логирования nginx

</decisions>

<specifics>
## Specific Ideas

- VM уже доступна: 158.160.27.49 (SSH)
- Максимальный размер файла = 300 МБ (явное требование пользователя)
- Внутренняя сеть — TLS не нужен для v1
- Тестовый файл: "Данные для маскирования_13.03.xlsx" (4 листа, ~30K строк)

</specifics>

<canonical_refs>
## Canonical References

No external specs — requirements are fully captured in decisions above and in ROADMAP.md Phase 4 success criteria.

### Project context
- `.planning/PROJECT.md` — VM address (158.160.27.49), constraints, tech stack
- `.planning/ROADMAP.md` — Phase 4 success criteria (4 items)
- `.streamlit/config.toml` — Current server config (maxUploadSize=50, headless=true)
- `requirements.txt` — Python dependencies for VM venv

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `.streamlit/config.toml` — уже содержит server.headless=true, нужно только обновить maxUploadSize
- `requirements.txt` — полный список зависимостей, готов для `pip install -r` на VM
- `.claude/launch.json` — конфигурация запуска Streamlit (порт 8501)

### Established Patterns
- Stateless архитектура — все данные в session_state, нет файлов на диске, нет глобальных переменных
- Нет конфигурационных секретов — приложение не использует .env, API keys и т.д.
- pytest для тестирования — можно запустить на VM для smoke-check

### Integration Points
- `app.py` — точка входа, запускается через `streamlit run app.py`
- Порт 8501 — стандартный для Streamlit, nginx проксирует на него

</code_context>

<deferred>
## Deferred Ideas

- HTTPS/TLS — потребуется при переходе к публичному доступу или авторизации
- CI/CD pipeline — автоматический деплой при пуше
- Мониторинг (healthcheck endpoint, alerting) — v2
- Авторизация — отдельная фаза в v2

</deferred>

---

*Phase: 04-deployment*
*Context gathered: 2026-03-20*
