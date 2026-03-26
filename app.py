import pathlib
import streamlit as st

st.set_page_config(
    page_title="Enigma — Шифрование данных для LLM",
    layout="wide",
    initial_sidebar_state="expanded",
)

_logo = pathlib.Path(__file__).parent / "assets" / "logo.png"
if _logo.exists():
    st.sidebar.image(str(_logo), use_container_width=True)
else:
    st.sidebar.title("Enigma")

page = st.sidebar.radio(
    "Режим",
    ["Маскирование", "Дешифровка", "PDF → Markdown", "Помощь"],
    label_visibility="collapsed",
)

if page == "Маскирование":
    from views.masking import render
    render()
elif page == "Дешифровка":
    from views.decryption import render
    render()
elif page == "PDF → Markdown":
    from views.pdf_to_md import render
    render()
elif page == "Помощь":
    from views.help import render
    render()
