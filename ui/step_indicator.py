import streamlit as st

STEPS = ["Загрузка файла", "Выбор колонок", "Результат"]


def render_steps(current: int) -> None:
    """Render step indicator. current is 1-based (1, 2, or 3)."""
    cols = st.columns(len(STEPS))
    for i, (col, label) in enumerate(zip(cols, STEPS), start=1):
        if i == current:
            col.markdown(f"**:blue[Шаг {i}: {label}]**")
        elif i < current:
            col.markdown(f"~~Шаг {i}: {label}~~")
        else:
            col.markdown(f"Шаг {i}: {label}")
