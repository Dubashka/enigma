"""MD restoration view — upload anonymized .md + mapping.json, get original back."""
from __future__ import annotations

import streamlit as st
from ui.step_indicator import render_steps, STEPS_MD_DECR

_STAGE        = "md_decr_stage"
_STAGE_UPLOAD = "upload"
_STAGE_RESULT = "result"

_FILE_NAME    = "md_decr_file_name"
_ANON_TEXT    = "md_decr_anon_text"
_RESTORED     = "md_decr_restored"


def render() -> None:
    st.header("Демаскирование MD")
    stage = st.session_state.get(_STAGE, _STAGE_UPLOAD)
    if stage == _STAGE_UPLOAD:
        _render_upload()
    elif stage == _STAGE_RESULT:
        _render_result()


def _render_upload() -> None:
    render_steps(current=1, steps=STEPS_MD_DECR)
    st.subheader("Загрузите файлы")

    col_md, col_json = st.columns(2)
    with col_md:
        uploaded_md = st.file_uploader(
            "Маскриванный MD-файл",
            type=["md", "txt"],
            key="md_decr_md_uploader",
        )
    with col_json:
        uploaded_json = st.file_uploader(
            "Файл маппинга (.json)",
            type=["json"],
            key="md_decr_json_uploader",
        )

    if uploaded_md and uploaded_json:
        if st.button("Восстановить", type="primary", use_container_width=True):
            anon_text = uploaded_md.read().decode("utf-8", errors="replace")
            from core.md_anonymizer import mapping_from_json, restore
            mapping = mapping_from_json(uploaded_json.read())
            restored = restore(anon_text, mapping)

            st.session_state[_FILE_NAME] = uploaded_md.name
            st.session_state[_ANON_TEXT] = anon_text
            st.session_state[_RESTORED] = restored
            st.session_state[_STAGE] = _STAGE_RESULT
            st.rerun()


def _render_result() -> None:
    render_steps(current=2, steps=STEPS_MD_DECR)
    restored = st.session_state[_RESTORED]
    file_name = st.session_state.get(_FILE_NAME, "файл")
    base = file_name.rsplit(".", 1)[0] if "." in file_name else file_name
    # Strip _anon suffix if present
    if base.endswith("_anon"):
        base = base[:-5]

    st.subheader("Результат демаскирования")

    col1, col2, col3 = st.columns(3)
    col1.metric("Строк", f"{len(restored.splitlines()):,}")
    col2.metric("Символов", f"{len(restored):,}")
    col3.metric("Слов", f"{len(restored.split()):,}")

    st.markdown("**Превью (первые 1000 символов)**")
    st.code(restored[:1000] + ("…" if len(restored) > 1000 else ""), language="markdown")

    st.download_button(
        label="Скачать восстановленный .md",
        data=restored.encode("utf-8"),
        file_name=f"{base}_restored.md",
        mime="text/markdown",
        use_container_width=True,
        type="primary",
    )

    col_back, col_reset = st.columns([1, 1])
    with col_back:
        if st.button("Назад", use_container_width=True):
            _reset()
            st.rerun()
    with col_reset:
        if st.button("Сбросить", use_container_width=True):
            _reset()
            st.rerun()


def _reset() -> None:
    for key in [_STAGE, _FILE_NAME, _ANON_TEXT, _RESTORED]:
        st.session_state.pop(key, None)
