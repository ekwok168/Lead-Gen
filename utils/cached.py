"""Cached data access helpers."""

import streamlit as st

from database import models


@st.cache_data(ttl=60)
def leads_with_scores():
    return models.get_leads_with_scores()


def invalidate():
    st.cache_data.clear()
