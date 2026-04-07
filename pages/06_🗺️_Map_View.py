"""Full interactive map page with all DCs, routes, and leads."""

import streamlit as st
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database.connection import init_db
from database.models import (
    get_all_dcs, get_all_routes, get_all_customers,
    get_all_stops, get_leads_with_scores,
)
from maps.visualizations import create_full_map

init_db()

st.set_page_config(page_title="Map View", page_icon="🗺️", layout="wide")
st.title("🗺️ Interactive Map")
st.markdown("View all distribution centers, delivery routes, existing customers, and prospects on one map")

dcs = get_all_dcs()
if dcs.empty:
    st.info("No data found. Go to **Upload Data** to import your data.")
    st.stop()

# Layer controls
st.markdown("### Display Options")
col1, col2, col3, col4 = st.columns(4)

with col1:
    show_routes = st.checkbox("Show route paths", value=True)
with col2:
    show_customers = st.checkbox("Show existing customers", value=True)
with col3:
    show_leads = st.checkbox("Show prospects", value=True)
with col4:
    lead_grades = st.multiselect("Lead grades to show", ["A", "B", "C", "D", "F"], default=["A", "B", "C"])

# Load data
routes = get_all_routes() if show_routes else pd.DataFrame()
customers = get_all_customers() if show_customers else pd.DataFrame()
stops = get_all_stops() if show_routes else pd.DataFrame()
scored = get_leads_with_scores() if show_leads else pd.DataFrame()

# Filter leads by grade
if not scored.empty and lead_grades and "score_grade" in scored.columns:
    scored = scored[scored["score_grade"].isin(lead_grades)]

# Create and display map
try:
    from streamlit_folium import st_folium

    m = create_full_map(dcs, routes, customers, stops, scored)
    st_folium(m, width=None, height=650, use_container_width=True)

    # Stats below map
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("DCs on Map", len(dcs))
    with col2:
        st.metric("Routes Shown", len(routes))
    with col3:
        st.metric("Customers Shown", len(customers))
    with col4:
        st.metric("Leads Shown", len(scored))

except ImportError:
    st.error("Map visualization requires streamlit-folium. Install it with: `pip install streamlit-folium`")

# Nearest stop analysis
if not scored.empty and "nearest_stop_name" in scored.columns:
    st.markdown("---")
    st.markdown("### Nearest Stop Analysis")
    st.markdown("Click on any prospect marker on the map to see its relationship to nearby route stops")

    # Summary table
    if "nearest_route_code" in scored.columns:
        stop_summary = scored.groupby(["nearest_route_code", "nearest_stop_name"]).agg(
            leads_nearby=("id", "count"),
            avg_distance=("nearest_route_stop_distance_mi", "mean"),
            a_leads=("score_grade", lambda x: (x == "A").sum()),
        ).reset_index().sort_values("leads_nearby", ascending=False).head(20)

        stop_summary.columns = ["Route", "Nearest Stop", "Leads Nearby", "Avg Distance (mi)", "A-Grade Leads"]
        stop_summary["Avg Distance (mi)"] = stop_summary["Avg Distance (mi)"].round(1)
        st.dataframe(stop_summary, use_container_width=True, hide_index=True)
