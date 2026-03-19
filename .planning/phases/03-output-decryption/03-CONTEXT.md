# Phase 3: Output + Decryption - Context

**Gathered:** 2026-03-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Выгрузка замаскированных файлов (xlsx), маппингов (JSON + Excel), и полный цикл дешифровки (загрузка замаскированного файла + маппинг → восстановление оригинальных значений). Статистика уже реализована в Phase 2 (OUT-04 — st.metric на Шаге 3). Деплой — в Phase 4.

</domain>

<decisions>
## Implementation Decisions

### Скачивание файлов (OUT-01, OUT-02, OUT-03)
- Заменить заглушки (disabled st.button) на st.download_button с реальными данными
- Генерация файлов в памяти через BytesIO — без записи на диск (stateless)
- xlsx через pandas ExcelWriter с engine='xlsxwriter' — сохраняет все листы и структуру
- Три кнопки скачивания: замаскированный xlsx, маппинг JSON, маппинг Excel

### Формат маппинга JSON (OUT-02)
- Использовать существующий формат из masker.py как есть: `{"text": {norm_val: pseudonym}, "numeric": {col: multiplier}}`
- Файл называется `{original_name}_mapping.json`
- UTF-8 encoding, ensure_ascii=False для кириллицы

### Формат маппинга Excel (OUT-03)
- Два листа в файле:
  - "Текстовый маппинг": колонки Оригинал | Псевдоним
  - "Числовой маппинг": колонки Колонка | Коэффициент
- Файл называется `{original_name}_mapping.xlsx`

### Статистика (OUT-04)
- Уже реализована в Phase 2 (Step 3: st.metric "Замаскировано значений" и "Уникальных сущностей")
- Никаких дополнительных изменений не нужно — требование выполнено

### Дешифровка — загрузка файлов (DECR-01)
- Вкладка "Дешифровка" в сайдбаре — уже есть placeholder в views/decryption.py
- Два st.file_uploader на странице: замаскированный файл (xlsx/csv) + JSON маппинг
- После загрузки обоих файлов показать превью замаскированных данных
- Кнопка "Дешифровать" запускает обратную замену

### Дешифровка — логика замены (DECR-02, DECR-03)
- Инвертировать text mapping: {pseudonym -> original} и применить Series.map()
- Для числовых колонок: разделить на коэффициент (обратная операция)
- Новые колонки/строки от LLM (не найденные в маппинге) — оставить без изменений
- NaN остаются NaN
- После дешифровки: превью восстановленных данных + кнопка скачивания xlsx

### Claude's Discretion
- Обработка ошибок при загрузке невалидного JSON маппинга
- Дизайн страницы дешифровки (layout, подписи)
- Именование скачиваемого восстановленного файла

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project context
- `.planning/PROJECT.md` — Core value, constraints (stateless, no disk writes)
- `.planning/REQUIREMENTS.md` — Требования OUT-01..04, DECR-01..03 для этой фазы

### Phase 2 code (integration points)
- `core/masker.py` — `mask_sheets()` returns `(masked_sheets, mapping, stats)` — mapping format is the contract for JSON export and decryption
- `core/state_keys.py` — Session state keys: MASKED_SHEETS, MAPPING, STATS already defined
- `views/masking.py:_render_step_masked()` — Contains download button stubs to replace (lines 156-159)
- `views/decryption.py` — Placeholder to replace with full decryption flow
- `ui/upload_widget.py:render_preview()` — Reuse for masked and decrypted data preview

### Sample data
- `Данные для маскирования_13.03.xlsx` — Тестовый файл для end-to-end проверки

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `core/masker.py:mask_sheets()` — Returns mapping dict that becomes JSON export and decryption input
- `core/masker.py:apply_text_masking()` and `apply_numeric_masking()` — Vectorized pattern to reuse for reverse
- `core/parser.py:parse_upload()` — Can parse both the masked xlsx and original files
- `ui/upload_widget.py:render_preview()` — Tab-based preview, reusable for decrypted data
- `core/masker.py:_normalize()` — Normalization function needed for decryption matching

### Established Patterns
- Session state stage machine: stage transitions via `st.session_state[STAGE] = ...` + `st.rerun()`
- BytesIO for in-memory file handling (parse_upload already uses this pattern)
- Tab-based multi-sheet display (st.tabs)
- Two-column button layout for navigation (Назад/Далее)

### Integration Points
- `views/masking.py:_render_step_masked()` lines 156-159 — Replace disabled buttons with st.download_button
- `views/decryption.py` — Replace placeholder with full decryption page
- `core/state_keys.py` — May need new keys for decryption state (decrypted_sheets, etc.)
- `app.py` — No changes needed, already routes to views/decryption.py

</code_context>

<specifics>
## Specific Ideas

- JSON маппинг должен быть читаемым (json.dumps с indent=2, ensure_ascii=False)
- Excel маппинг — для пользователя-человека, поэтому русские заголовки колонок
- Дешифровка должна работать даже если LLM добавил новые колонки или строки в файл

</specifics>

<deferred>
## Deferred Ideas

- DECR-04: Нечёткая дешифровка (fuzzy matching) — v2
- Скачивание в формате CSV (только xlsx в v1)
- Предпросмотр различий до/после дешифровки

</deferred>

---

*Phase: 03-output-decryption*
*Context gathered: 2026-03-20*
