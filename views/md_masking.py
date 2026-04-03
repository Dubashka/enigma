"""MD anonymization view — Step 1: upload, Step 2: review entities, Step 3: download.

Ollama AI NER запускается вручную кнопкой на шаге 2 — аналогично Excel-маскированию.
"""
from __future__ import annotations

import streamlit as st
from ui.step_indicator import render_steps, STEPS_MD_MASK

_STAGE         = "md_mask_stage"
_STAGE_UPLOAD  = "upload"
_STAGE_REVIEW  = "review"
_STAGE_RESULT  = "result"

_FILE_NAME   = "md_mask_file_name"
_FILE_TEXT   = "md_mask_file_text"
_ANON_TEXT   = "md_mask_anon_text"
_MAPPING     = "md_mask_mapping"
_ENTITIES    = "md_mask_entities"
_AI_DONE     = "md_mask_ai_done"   # флаг: Ollama уже отработала
_AI_DELTA    = "md_mask_ai_delta"  # количество новых сущностей от Ollama

ALL_LABELS = ["ФИО", "ОРГ", "EMAIL", "ТЕЛЕФОН", "IP", "ДОГОВОР", "СУММА", "ДАТА", "АДРЕС",
              "ПАСПОРТ", "СНИЛС", "ИНН", "КПП"]

LABEL_DESCRIPTIONS = {
    "ФИО":     "Имена и фамилии людей",
    "ОРГ":     "Названия организаций",
    "EMAIL":   "Адреса электронной почты",
    "ТЕЛЕФОН": "Номера телефонов",
    "IP":      "IP-адреса",
    "ДОГОВОР": "Номера договоров и документов",
    "СУММА":   "Денежные суммы",
    "ДАТА":    "Даты",
    "АДРЕС":   "Физические адреса",
    "ПАСПОРТ": "Паспортные данные (серия + номер)",
    "СНИЛС":   "СНИЛС",
    "ИНН":     "ИНН физического или юридического лица",
    "КПП":     "КПП организации",
}


def render() -> None:
    st.header("Маскирование MD")
    stage = st.session_state.get(_STAGE, _STAGE_UPLOAD)
    if stage == _STAGE_UPLOAD:
        _render_upload()
    elif stage == _STAGE_REVIEW:
        _render_review()
    elif stage == _STAGE_RESULT:
        _render_result()


# ---------------------------------------------------------------------------
# Шаг 1 — загрузка файла
# ---------------------------------------------------------------------------

def _render_upload() -> None:
    render_steps(current=1, steps=STEPS_MD_MASK)
    st.subheader("Загрузите MD-файл")

    uploaded = st.file_uploader(" ", type=["md", "txt"], key="md_mask_uploader")

    if uploaded is not None:
        text = uploaded.read().decode("utf-8", errors="replace")
        st.session_state[_FILE_NAME] = uploaded.name
        st.session_state[_FILE_TEXT] = text

        # Базовое детектирование: Natasha + Presidio + regex (без Ollama)
        with st.spinner("Ищем чувствительные данные в тексте…"):
            from core.md_anonymizer import detect_entities
            entities = detect_entities(text)

        st.session_state[_ENTITIES] = entities
        st.session_state[_AI_DONE]  = False
        st.session_state[_AI_DELTA] = 0
        st.session_state[_STAGE]    = _STAGE_REVIEW
        st.rerun()


# ---------------------------------------------------------------------------
# Шаг 2 — просмотр сущностей + опциональный запуск Ollama
# ---------------------------------------------------------------------------

def _render_review() -> None:
    render_steps(current=2, steps=STEPS_MD_MASK)
    text      = st.session_state[_FILE_TEXT]
    entities  = st.session_state[_ENTITIES]
    file_name = st.session_state.get(_FILE_NAME, "файл")
    ai_done   = st.session_state.get(_AI_DONE, False)
    ai_delta  = st.session_state.get(_AI_DELTA, 0)

    st.subheader(f"Найденные чувствительные данные: {file_name}")

    # --- Блок Ollama --------------------------------------------------------
    st.markdown("---")
    ai_col1, ai_col2 = st.columns([2, 3])
    with ai_col1:
        btn_label = "✅ Ollama уже применена" if ai_done else "🤖 Уточнить через Ollama"
        clicked = st.button(
            btn_label,
            disabled=ai_done,
            use_container_width=True,
            key="btn_ollama",
            help="Запустить локальную LLM (Ollama) для поиска дополнительных сущностей. "
                 "Требует запущенного Ollama на localhost:11434.",
        )

    with ai_col2:
        if ai_done:
            msg = (
                f"Ollama нашла **{ai_delta}** новых сущностей — список обновлён."
                if ai_delta else
                "Ollama завершила анализ. Новых сущностей сверх базовых не найдено."
            )
            st.success(msg, icon="✅")
        else:
            st.info(
                "Базовое сканирование выполнено (Natasha + Presidio + regex). "
                "Нажмите кнопку слева, чтобы запустить Ollama для поиска "
                "сущностей, которые базовые методы могли пропустить.",
                icon="ℹ️",
            )

    # Обработка нажатия — ПОСЛЕ рендера обоих столбцов,
    # чтобы st.spinner не ломал layout
    if clicked and not ai_done:
        _run_ollama_and_merge(text)
        st.rerun()

    st.markdown("---")

    # --- Отображение найденных сущностей ------------------------------------
    by_label: dict[str, list[str]] = {}
    for _, _, label, value in entities:
        by_label.setdefault(label, [])
        if value not in by_label[label]:
            by_label[label].append(value)

    if not by_label:
        st.info("Чувствительные данные в файле не обнаружены. Можно скачать файл без изменений.")
    else:
        st.markdown("Выберите типы данных для маскирования:")
        for label in ALL_LABELS:
            if label not in by_label:
                continue
            values = by_label[label]
            col_cb, col_vals = st.columns([0.25, 0.75])
            with col_cb:
                st.checkbox(
                    f"**{label}** ({len(values)} шт.)",
                    value=True,
                    key=f"md_label_{label}",
                )
            with col_vals:
                preview = ",  ".join(f"`{v}`" for v in values[:5])
                if len(values) > 5:
                    preview += f"  _...ещё {len(values) - 5}_"
                st.markdown(
                    f"<span style='color:#666;font-size:0.85em'>{preview}</span>",
                    unsafe_allow_html=True,
                )

    # --- Дополнительные термины ---------------------------------------------
    st.markdown("---")
    st.markdown("Дополнительные слова и фразы для маскировки")
    st.text_area(
        "Введите через запятую слова или фразы, которые нужно скрыть дополнительно",
        key="md_extra_terms",
        height=80,
        placeholder="Проект Альфа, сервер БД, филиал №3",
    )

    # --- Кнопки навигации ---------------------------------------------------
    col_back, col_anon = st.columns([1, 1])
    with col_back:
        if st.button("Назад", use_container_width=True):
            _reset()
            st.rerun()
    with col_anon:
        if st.button("Маскировать", type="primary", use_container_width=True):
            enabled = {l for l in ALL_LABELS if st.session_state.get(f"md_label_{l}", False)}
            if not enabled and not st.session_state.get("md_extra_terms", "").strip():
                st.warning("Выберите хотя бы один тип данных или введите дополнительные слова")
            else:
                from core.md_anonymizer import anonymize, anonymize_extra_terms
                anon_text, mapping = anonymize(
                    text,
                    enabled_labels=enabled if enabled else None,
                    predetected_entities=st.session_state.get(_ENTITIES),
                )

                raw_extra = st.session_state.get("md_extra_terms", "")
                extra_terms = [t.strip() for t in raw_extra.split(",") if t.strip()]
                if extra_terms:
                    anon_text, mapping = anonymize_extra_terms(anon_text, extra_terms, mapping)

                st.session_state[_ANON_TEXT] = anon_text
                st.session_state[_MAPPING]   = mapping
                st.session_state[_STAGE]     = _STAGE_RESULT
                st.rerun()


# ---------------------------------------------------------------------------
# Вспомогательная функция: запуск Ollama и обогащение списка сущностей
# ---------------------------------------------------------------------------

def _run_ollama_and_merge(text: str) -> None:
    """Запустить Ollama, смержить результат с базовыми сущностями.

    Исключения пробрасываются через st.error() — состояние не теряется.
    """
    from core.ai_ner import AINer, merge_entity_lists, OllamaUnavailableError, OllamaParseError

    base_entities = st.session_state.get(_ENTITIES, [])
    base_count    = len(base_entities)

    with st.spinner("Ollama анализирует текст… Это может занять 15–120 секунд."):
        try:
            ner = AINer(mode="ollama")
            ai_entities = ner.extract(text)
        except OllamaUnavailableError as exc:
            st.error(
                f"**Ollama недоступна.**\n\n{exc}\n\n"
                "Базовый список сущностей сохранён — можно продолжить без Ollama.",
                icon="🔴",
            )
            return
        except OllamaParseError as exc:
            st.error(
                f"**Ollama вернула некорректный ответ.**\n\n{exc}\n\n"
                "Попробуйте снова или используйте другую модель (ENIGMA_OLLAMA_MODEL).",
                icon="🟠",
            )
            return
        except Exception as exc:
            st.error(f"**Неожиданная ошибка Ollama:** {exc}", icon="🔴")
            return

    merged = merge_entity_lists(base_entities, ai_entities)
    delta  = len(merged) - base_count

    st.session_state[_ENTITIES] = merged
    st.session_state[_AI_DONE]  = True
    st.session_state[_AI_DELTA] = delta


# ---------------------------------------------------------------------------
# Шаг 3 — результат
# ---------------------------------------------------------------------------

def _render_result() -> None:
    render_steps(current=3, steps=STEPS_MD_MASK)
    anon_text = st.session_state[_ANON_TEXT]
    mapping   = st.session_state[_MAPPING]
    file_name = st.session_state.get(_FILE_NAME, "файл")
    base = file_name.rsplit(".", 1)[0] if "." in file_name else file_name

    st.subheader("Результат маскирования")

    cols = st.columns(len(mapping) if mapping else 1)
    for i, (label, items) in enumerate(mapping.items()):
        cols[i % len(cols)].metric(label, len(items))

    st.markdown("Превью (первые 1000 символов)")
    st.code(anon_text[:1000] + ("…" if len(anon_text) > 1000 else ""), language="markdown")

    st.warning("⚠️ Не забудьте скачать маппинг (.json) для дальнейшего демаскирования")

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            label="Маскированный .md",
            data=anon_text.encode("utf-8"),
            file_name=f"{base}_anon.md",
            mime="text/markdown",
            use_container_width=True,
            type="primary",
        )
    with col2:
        from core.md_anonymizer import mapping_to_json
        st.download_button(
            label="Маппинг (.json)",
            data=mapping_to_json(mapping),
            file_name=f"{base}_mapping.json",
            mime="application/json",
            use_container_width=True,
            type="primary",
        )

    col_back, col_reset = st.columns([1, 1])
    with col_back:
        if st.button("Назад к выбору сущностей", use_container_width=True):
            st.session_state.pop(_ANON_TEXT, None)
            st.session_state.pop(_MAPPING, None)
            st.session_state[_STAGE] = _STAGE_REVIEW
            st.rerun()
    with col_reset:
        if st.button("Сбросить", use_container_width=True):
            _reset()
            st.rerun()


def _reset() -> None:
    for key in [_STAGE, _FILE_NAME, _FILE_TEXT, _ANON_TEXT, _MAPPING,
                _ENTITIES, _AI_DONE, _AI_DELTA]:
        st.session_state.pop(key, None)
    for label in ALL_LABELS:
        st.session_state.pop(f"md_label_{label}", None)
    st.session_state.pop("md_extra_terms", None)
