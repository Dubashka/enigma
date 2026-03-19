# Phase 1: Foundation - Context

**Gathered:** 2026-03-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Загрузка Excel/CSV файлов, превью данных, русскоязычный интерфейс и stateless архитектура на Streamlit session state. Маскирование, детекция, выгрузка и дешифровка — в других фазах.

</domain>

<decisions>
## Implementation Decisions

### Структура приложения
- Сайдбар с навигацией: Маскирование / Дешифровка (два основных режима)
- Сайдбар содержит только навигацию, без дополнительной информации
- Пошаговый flow маскирования: Шаг 1 (Загрузка) → Шаг 2 (Выбор колонок) → Шаг 3 (Результат + скачивание)
- Кнопки Назад/Далее для перехода между шагами

### Превью данных
- Табы (st.tabs) с названиями листов для многолистовых Excel-файлов
- 20 строк в превью каждого листа
- Без метаданных файла (кол-во листов, строк) — сразу табы с таблицами
- Пустые листы пропускаются молча (не показываются в табах)

### Обработка ошибок
- Неподдерживаемые форматы → читаемое сообщение на русском ("Поддерживаются только файлы xlsx и csv")
- Битые файлы → ошибка "Не удалось прочитать файл"

### Claude's Discretion
- Ограничение на размер файла (определить на основе RAM VM)
- Обработка файлов с единственным листом (не показывать табы, если лист один)
- Дизайн кнопок Назад/Далее и индикатора шагов

### Внешний вид
- Светлая тема (light)
- Заголовок: "Enigma — Шифрование данных для LLM"
- Streamlit page config: wide layout для таблиц с 30+ колонками

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project context
- `.planning/PROJECT.md` — Видение продукта, core value, constraints (Streamlit + Python)
- `.planning/REQUIREMENTS.md` — Требования LOAD-01..03, UI-01..02 для этой фазы
- `.planning/research/STACK.md` — Рекомендации по стеку: Streamlit 1.55, pandas 3.0.1, openpyxl 3.1.5
- `.planning/research/ARCHITECTURE.md` — Архитектурные решения: BytesIO, session state, компоненты
- `.planning/research/PITFALLS.md` — Подводные камни: openpyxl RAM (50x), session state архитектура с первого дня

### Sample data
- `Данные для маскирования_13.03.xlsx` — Реальный тестовый файл с 4 листами (15–37 колонок, 7–9 строк)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Нет — greenfield проект

### Established Patterns
- Нет — всё создаётся с нуля

### Integration Points
- session_state должен хранить parsed DataFrames в формате dict[sheet_name, DataFrame] — этот формат будет использоваться Phase 2 (маскирование) и Phase 3 (выгрузка)

</code_context>

<specifics>
## Specific Ideas

- Заголовок именно "Enigma — Шифрование данных для LLM" (пользователь указал)
- Тестировать на реальном файле "Данные для маскирования_13.03.xlsx" с кириллическими заголовками и 4 листами

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-foundation*
*Context gathered: 2026-03-19*
