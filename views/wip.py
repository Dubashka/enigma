"""Placeholder view for features that are not yet implemented."""
from __future__ import annotations

import streamlit as st


_DESCRIPTIONS = {
    "word_mask":    ("Шифрование Word",       "Замаскирование чувствительных данных в документах .docx с сохранением форматирования."),
    "word_decrypt": ("Дешифровка Word",      "Восстановление оригинальных значений в замаскированных документах Word."),
    "pdf_to_word":  ("Конвертация PDF → Word", "Преобразование PDF-файлов в редактируемый формат .docx."),
    "pdf_to_md":    ("Конвертация PDF → MD",   "Преобразование PDF-файлов в Markdown для удобной работы с LLM."),
}


def render(page_key: str) -> None:
    title, description = _DESCRIPTIONS.get(page_key, ("Раздел", "Описание недоступно."))
    st.header(title)
    st.markdown(
        f"""
        <div style="
            background: #fffbeb;
            border: 1px solid #fcd34d;
            border-radius: 10px;
            padding: 2rem 2rem;
            margin-top: 1.5rem;
            text-align: center;
        ">
            <div style="font-size: 3rem; margin-bottom: 0.5rem">🚧</div>
            <div style="font-size: 1.3rem; font-weight: 600; color: #92400e; margin-bottom: 0.5rem">
                В разработке
            </div>
            <div style="color: #78350f; font-size: 0.95rem">
                {description}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
