import streamlit as st

st.set_page_config(
    page_title="Enigma — Шифрование данных для LLM",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.sidebar.title("Enigma")
page = st.sidebar.radio(
    "Режим",
    ["Маскирование", "Дешифровка"],
    label_visibility="collapsed",
)

if page == "Маскирование":
    from views.masking import render
    render()
elif page == "Дешифровка":
    from views.decryption import render
    render()
