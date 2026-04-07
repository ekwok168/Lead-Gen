"""Route View page - Route level analysis with stop-to-prospect visualization."""

import streamlit as st
import plotly.express as px
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database.connection import init_db
from database.models import (
    get_all_dcs, get_routes_by_dc, get_all_routes, get_stops_by_route,
    get_dc, get_leads_with_scores,
)
from reports.route_report import generate_route_report
from maps.visualizations import create_route_map
from scoring.engine import generate_why_text

init_db()

st.set_page_config(page_title="Route View", page_icon="🚛", layout="wide")
st.title("🚛 Route View")

dcs = get_all_dcs()
if dcs.empty:
    st.info("No data found. Go to **Upload Data** to import your data.")
    st.stop()

# DC filter
col1, col2 = st.columns(2)

with col1:
    dc_options = {"all": "All Distribution Centers"}
    dc_options.update({row["id"]: f"{row['code']} - {row['name']}" for _, row in dcs.iterrows()})
    selected_dc = st.selectbox("Filter by DC", options=list(dc_options.keys()),
                                format_func=lambda x: dc_options[x])

with col2:
    if selected_dc == "all":
        routes = get_all_routes()
    else:
        routes = get_routes_by_dc(selected_dc)

    if routes.empty:
        st.warning("No routes found.")
        st.stop()

    route_options = {row["id"]: f"{row['route_code']} - {row.get('route_name', '')}" for _, row in routes.iterrows()}
    selected_route_id = st.selectbox("Select Route", options=list(route_options.keys()),
                                      format_func=lambda x: route_options[x])

if selected_route_id:
    report = generate_route_report(selected_route_id)

    if not report:
        st.error("Could not generate report.")
        st.stop()

    summary = report["summary"]
    dc_info = report["dc_info"]

    # Summary
    st.markdown("---")
    st.markdown(f"### Route {summary['route_code']}: {summary['route_name']}")
    st.markdown(f"🏢 DC: {summary['dc_name']} | 📅 {summary['day_of_week']} | 🚛 {summary.get('driver_name', 'N/A')}")

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Customers", summary["customer_count"])
    with col2:
        st.metric("Weekly Revenue", f"${summary['total_weekly_revenue']:,.0f}")
    with col3:
        st.metric("Nearby Leads", summary["lead_count"])
    with col4:
        st.metric("Hot Leads (A)", summary["a_leads"])
    with col5:
        st.metric("Avg Lead Score", summary["avg_lead_score"])

    # Route Map with stops and prospects
    st.markdown("---")
    st.markdown("#### Route Map")
    st.markdown("""
    **Blue numbered markers** = existing delivery stops (in sequence)
    | **Red** = Hot leads (A) | **Orange** = Strong (B) | **Yellow** = Moderate (C) | **Gray** = Low (D/F)
    | **Dashed lines** = connection from A/B leads to their nearest stop
    """)

    show_radius = st.checkbox("Show delivery radius circles (0.5 mi / 1.0 mi)", value=True)
    show_connectors = st.checkbox("Show connector lines to nearest stops", value=True)

    stops = report["stops"]
    leads = report["leads"]

    try:
        from streamlit_folium import st_folium

        route_info = {"route_code": summary["route_code"]}
        m = create_route_map(
            route_info, report["customers"], stops, leads, dc_info,
            show_radius=show_radius, show_connectors=show_connectors,
        )
        st_folium(m, width=None, height=550, use_container_width=True)
    except ImportError:
        st.warning("Install streamlit-folium for interactive maps: `pip install streamlit-folium`")

    # Customer list (in delivery sequence)
    st.markdown("---")
    st.markdown("#### Delivery Stops (in sequence)")
    if not report["customers"].empty:
        cust = report["customers"].copy()
        cust.columns = ["Business Name", "Address", "Type", "Segment", "Revenue/wk", "Stop #"]
        st.dataframe(cust, use_container_width=True, hide_index=True)

    # Leads near this route
    st.markdown("---")
    st.markdown("#### Prospects Near This Route")

    if not leads.empty and "total_score" in leads.columns:
        # Grade filter
        grade_filter = st.multiselect(
            "Filter by grade",
            ["A", "B", "C", "D", "F"],
            default=["A", "B", "C"],
        )
        filtered = leads[leads["score_grade"].isin(grade_filter)] if grade_filter else leads

        if not filtered.empty:
            st.write(f"Showing {len(filtered)} leads")

            for _, lead in filtered.iterrows():
                grade = lead.get("score_grade", "F")
                grade_colors = {"A": "🔴", "B": "🟠", "C": "🟡", "D": "⚪", "F": "⬜"}
                core_badge = " ⭐ Core Segment" if lead.get("is_core_segment") else ""

                with st.expander(
                    f"{grade_colors.get(grade, '⬜')} **{lead['name']}** | "
                    f"Grade {grade} ({lead.get('total_score', 0):.0f}) | "
                    f"{lead.get('nearest_route_stop_distance_mi', 0):.1f} mi from nearest stop"
                    f"{core_badge}"
                ):
                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown("**Business Details**")
                        st.write(f"📍 {lead.get('address', 'N/A')}, {lead.get('city', '')} {lead.get('state', '')}")
                        st.write(f"🏪 {lead.get('business_type', 'N/A')} - {lead.get('segment', 'N/A')}")
                        st.write(f"📞 {lead.get('phone', 'N/A')}")
                        st.write(f"💰 Est. Revenue: ${lead.get('estimated_weekly_revenue', 0):,.0f}/week")

                    with col2:
                        st.markdown("**Score Breakdown**")
                        st.write(f"📍 Proximity: **{lead.get('proximity_score', 0):.0f}**/100")
                        st.write(f"🏷️ Segment: **{lead.get('segment_score', 0):.0f}**/100")
                        st.write(f"📊 Density: **{lead.get('density_score', 0):.0f}**/100")
                        st.write(f"💵 Revenue: **{lead.get('revenue_score', 0):.0f}**/100")

                    # Nearest stop info
                    st.markdown("**Route Relationship**")
                    stop_info = lead.get("nearest_stop_info", "")
                    if stop_info:
                        st.info(f"📌 {stop_info}")

                    # Why this lead
                    why = lead.get("why_this_lead", "")
                    if why:
                        st.success(f"💡 **Why This Lead?** {why}")
        else:
            st.info("No leads match the selected grade filters.")
    else:
        st.info("No scored leads for this route. Run **Score All Leads** first.")
