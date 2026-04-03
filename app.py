import pathlib
import streamlit as st

st.set_page_config(
    page_title="Reksoft Consulting. Шифрование данных для LLM",
    layout="wide",
    initial_sidebar_state="expanded",
)

_logo = pathlib.Path(__file__).parent / "assets" / "logo.png"
if _logo.exists():
    st.sidebar.image(str(_logo), use_container_width=True)
else:
    st.sidebar.title("Enigma")

st.sidebar.markdown("** **")
page = st.sidebar.radio(
    "Режим",
    ["Маскирование Excel/CSV", "Демаскирование Excel/CSV", "Конвертация в MD", "Маскирование текстовых файлов", "Демаскирование текстовых файлов", "Помощь"],
    label_visibility="collapsed",
)

if page == "Маскирование Excel/CSV":
    from views.masking import render
    render()
elif page == "Демаскирование Excel/CSV":
    from views.decryption import render
    render()
elif page == "Конвертация в MD":
    from views.pdf_to_md import render
    render()
elif page == "Маскирование текстовых файлов":
    from views.md_masking import render
    render()
elif page == "Демаскирование текстовых файлов":
    from views.md_decryption import render
    render()
elif page == "Помощь":
    from views.help import render
    render()
