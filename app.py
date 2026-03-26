import pathlib
import streamlit as st

st.set_page_config(
    page_title="Enigma — Шифрование данных для LLM",
    layout="wide",
    initial_sidebar_state="expanded",
)

from ui.sidebar import render_sidebar

page = render_sidebar()

if page == "excel_mask":
    from views.masking import render
    render()
elif page == "excel_decrypt":
    from views.decryption import render
    render()
elif page in ("word_mask", "word_decrypt", "pdf_to_word", "pdf_to_md"):
    from views.wip import render
    render(page)
elif page == "help":
    from views.help import render
    render()
