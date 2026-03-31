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
    ["Маскирование", "Демаскирование", "Конвертация в MD", "Помощь"],
    label_visibility="collapsed",
)

if page == "Маскирование":
    from views.masking import render
    render()
elif page == "Демаскирование":
    from views.decryption import render
    render()
elif page == "Конвертация в MD":
    from views.pdf_to_md import render
    render()
elif page == "Помощь":
    from views.help import render
    render()
