"""Shared password authentication for all pages."""

import hmac

import streamlit as st


def check_password() -> bool:
    """Return True if the user has entered the correct password."""
    # If no password is configured in secrets, skip auth
    try:
        correct_password = st.secrets["password"]
    except (KeyError, FileNotFoundError):
        return True

    if st.session_state.get("authenticated"):
        return True

    st.markdown("### 🔒 Lead Generation Tool")
    st.markdown("Please enter the password to access this tool.")
    password = st.text_input("Password", type="password", key="password_input")

    if password:
        if hmac.compare_digest(password, correct_password):
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password. Please try again.")
    return False


def require_auth():
    """Stop page execution if the user is not authenticated."""
    if not check_password():
        st.stop()
