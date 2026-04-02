"""MD anonymization view — Step 1: upload, Step 2: review entities, Step 3: download."""
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

ALL_LABELS = ["ФИО", "ОРГ", "EMAIL", "ТЕЛЕФОН", "IP", "ДОГОВОР", "СУММА", "ДАТА", "АДРЕС"]

LABEL_DESCRIPTIONS = {
    "ФИО": "Имена и фамилии людей",
    "ОРГ": "Названия организаций",
    "EMAIL": "Адреса электронной почты",
    "ТЕЛЕФОН": "Номера телефонов",
    "IP": "IP-адреса",
    "ДОГОВОР": "Номера договоров и документов",
    "СУММА": "Денежные суммы",
    "ДАТА": "Даты",
    "АДРЕС": "Физические адреса",
}


def render() -> None:
    st.header("Анонимизация MD")
    stage = st.session_state.get(_STAGE, _STAGE_UPLOAD)
    if stage == _STAGE_UPLOAD:
        _render_upload()
    elif stage == _STAGE_REVIEW:
        _render_review()
    elif stage == _STAGE_RESULT:
        _render_result()


def _render_upload() -> None:
    render_steps(current=1, steps=STEPS_MD_MASK)
    st.subheader("Загрузите MD-файл")

    uploaded = st.file_uploader(" ", type=["md", "txt"], key="md_mask_uploader")

    if uploaded is not None:
        text = uploaded.read().decode("utf-8", errors="replace")
        st.session_state[_FILE_NAME] = uploaded.name
        st.session_state[_FILE_TEXT] = text

        with st.spinner("Ищем персональные данные в тексте…"):
            from core.md_anonymizer import detect_entities
            entities = detect_entities(text)

        st.session_state[_ENTITIES] = entities
        st.session_state[_STAGE] = _STAGE_REVIEW
        st.rerun()


def _render_review() -> None:
    render_steps(current=2, steps=STEPS_MD_MASK)
    text = st.session_state[_FILE_TEXT]
    entities = st.session_state[_ENTITIES]
    file_name = st.session_state.get(_FILE_NAME, "файл")

    st.subheader(f"Найденные сущности: {file_name}")

    # Group entities by label for display
    by_label: dict[str, list[str]] = {}
    for _, _, label, value in entities:
        by_label.setdefault(label, [])
        if value not in by_label[label]:
            by_label[label].append(value)

    if not by_label:
        st.info("Персональные данные в файле не обнаружены. Можно скачать файл без изменений.")
    else:
        st.markdown("Выберите типы данных для анонимизации:")
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

    # ---------------------------------------------------------------------------
    # Extra terms — user-defined words/phrases to mask in addition to auto-detected
    # ---------------------------------------------------------------------------
    st.markdown("---")
    st.markdown("Дополнительные слова и фразы для маскировки")
    st.text_area(
        "Введите через запятую слова или фразы, которые нужно скрыть дополнительно",
        key="md_extra_terms",
        height=80,
        placeholder="Проект Альфа, сервер БД, филиал №3",
    )

    col_back, col_anon = st.columns([1, 1])
    with col_back:
        if st.button("Назад", use_container_width=True):
            _reset()
            st.rerun()
    with col_anon:
        if st.button("Анонимизировать", type="primary", use_container_width=True):
            enabled = {l for l in ALL_LABELS if st.session_state.get(f"md_label_{l}", False)}
            if not enabled and not st.session_state.get("md_extra_terms", "").strip():
                st.warning("Выберите хотя бы один тип данных или введите дополнительные слова")
            else:
                from core.md_anonymizer import anonymize, anonymize_extra_terms
                anon_text, mapping = anonymize(text, enabled_labels=enabled if enabled else None)

                raw_extra = st.session_state.get("md_extra_terms", "")
                extra_terms = [t.strip() for t in raw_extra.split(",") if t.strip()]
                if extra_terms:
                    anon_text, mapping = anonymize_extra_terms(anon_text, extra_terms, mapping)

                st.session_state[_ANON_TEXT] = anon_text
                st.session_state[_MAPPING] = mapping
                st.session_state[_STAGE] = _STAGE_RESULT
                st.rerun()


def _render_result() -> None:
    render_steps(current=3, steps=STEPS_MD_MASK)
    anon_text = st.session_state[_ANON_TEXT]
    mapping = st.session_state[_MAPPING]
    file_name = st.session_state.get(_FILE_NAME, "файл")
    base = file_name.rsplit(".", 1)[0] if "." in file_name else file_name

    st.subheader("Результат анонимизации")

    total = sum(len(v) for v in mapping.values())
    cols = st.columns(len(mapping) if mapping else 1)
    for i, (label, items) in enumerate(mapping.items()):
        cols[i % len(cols)].metric(label, len(items))

    st.markdown("Превью (первые 1000 символов)")
    st.code(anon_text[:1000] + ("…" if len(anon_text) > 1000 else ""), language="markdown")

    st.warning("⚠️ Не забудьте скачать маппинг (.json) для дальнейшего восстановления")

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            label="Анонимизированный .md",
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
    for key in [_STAGE, _FILE_NAME, _FILE_TEXT, _ANON_TEXT, _MAPPING, _ENTITIES]:
        st.session_state.pop(key, None)
    for label in ALL_LABELS:
        st.session_state.pop(f"md_label_{label}", None)
    st.session_state.pop("md_extra_terms", None)
