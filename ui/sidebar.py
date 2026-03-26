"""Custom sidebar navigation with section headers, icons and active item highlight."""
from __future__ import annotations

import streamlit as st

# Navigation structure: (key, label, icon, section)
# section=True means this item is a non-clickable header
NAV_ITEMS = [
    {"key": None,                  "label": "РАБОТА С EXCEL",           "icon": "📊", "section": True},
    {"key": "excel_mask",          "label": "Шифрование",               "icon": "🔒", "section": False},
    {"key": "excel_decrypt",       "label": "Дешифровка",               "icon": "🔓", "section": False},
    {"key": None,                  "label": "РАБОТА С WORD",            "icon": "📝", "section": True},
    {"key": "word_mask",           "label": "Шифрование",               "icon": "🔒", "section": False},
    {"key": "word_decrypt",        "label": "Дешифровка",               "icon": "🔓", "section": False},
    {"key": None,                  "label": "РАБОТА С PDF",             "icon": "📄", "section": True},
    {"key": "pdf_to_word",         "label": "Конвертация в Word",        "icon": "🔄", "section": False},
    {"key": "pdf_to_md",           "label": "Конвертация в MD",          "icon": "🔄", "section": False},
    {"key": None,                  "label": "────────────────────",  "icon": "",    "section": True},
    {"key": "help",                "label": "Помощь",                      "icon": "❓", "section": False},
]

_CSS = """
<style>
/* Hide default Streamlit sidebar nav elements */
[data-testid="stSidebarNav"] { display: none; }

/* Sidebar background */
[data-testid="stSidebar"] > div:first-child {
    padding-top: 0rem;
}

/* Nav item button base */
.nav-item {
    display: block;
    width: 100%;
    padding: 0.45rem 1rem 0.45rem 1.6rem;
    margin: 1px 0;
    border: none;
    border-radius: 6px;
    background: transparent;
    text-align: left;
    cursor: pointer;
    font-size: 0.92rem;
    color: #374151;
    transition: background 0.15s;
    text-decoration: none;
}
.nav-item:hover {
    background: #e5e7eb;
    color: #111827;
}
.nav-item.active {
    background: #dbeafe;
    color: #1d4ed8;
    font-weight: 600;
}

/* Section header */
.nav-section {
    padding: 0.7rem 1rem 0.2rem 1rem;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.07em;
    color: #9ca3af;
    text-transform: uppercase;
    user-select: none;
}

/* Divider section */
.nav-divider {
    border: none;
    border-top: 1px solid #e5e7eb;
    margin: 0.5rem 1rem;
}

/* Logo area */
.nav-logo {
    padding: 1.2rem 1rem 0.8rem 1rem;
    font-size: 1.25rem;
    font-weight: 700;
    color: #1d4ed8;
    letter-spacing: -0.01em;
    display: flex;
    align-items: center;
    gap: 0.4rem;
}
</style>
"""


def render_sidebar() -> str:
    """Render custom sidebar navigation and return the currently selected page key."""
    # Inject CSS once
    st.sidebar.markdown(_CSS, unsafe_allow_html=True)

    # Logo
    st.sidebar.markdown(
        '<div class="nav-logo">🔐 Enigma</div>',
        unsafe_allow_html=True,
    )

    current = st.session_state.get("_nav_page", "excel_mask")

    for item in NAV_ITEMS:
        if item["section"]:
            # Divider or section header
            label = item["label"]
            if label.startswith("─"):
                st.sidebar.markdown('<hr class="nav-divider">', unsafe_allow_html=True)
            else:
                st.sidebar.markdown(
                    f'<div class="nav-section">{item["icon"]} {label}</div>',
                    unsafe_allow_html=True,
                )
        else:
            key = item["key"]
            label = item["label"]
            icon = item["icon"]
            is_active = current == key
            active_class = " active" if is_active else ""
            # Render as Streamlit button (invisible label) with styled div overlay
            # We use st.sidebar.button for click handling
            btn_label = f"{icon}\u2002{label}"
            if st.sidebar.button(
                btn_label,
                key=f"nav_btn_{key}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                # Clear page-specific state on navigation
                _clear_page_state(current, key)
                st.session_state["_nav_page"] = key
                st.rerun()

    return current


def _clear_page_state(old_page: str, new_page: str) -> None:
    """Clear session state keys belonging to the old page when navigating away."""
    if old_page == new_page:
        return
    # Masking flow
    if old_page == "excel_mask":
        masking_keys = [
            "sheets", "raw_bytes", "file_path", "stage", "file_name",
            "selected_columns", "mask_config", "mapping", "masked_sheets", "stats",
            "dl_xlsx", "dl_map_json", "dl_map_xlsx", "format_mode",
        ]
        cb_keys = [k for k in st.session_state if k.startswith(("cb_", "type_"))]
        for k in masking_keys + cb_keys:
            st.session_state.pop(k, None)
    # Decryption flow
    if old_page == "excel_decrypt":
        decrypt_keys = [
            "decr_sheets", "decr_mapping", "decr_result", "decr_file_path",
            "format_mode", "decr_stage", "decr_file_name",
        ]
        for k in decrypt_keys:
            st.session_state.pop(k, None)
