"""DC View page - Distribution center level analysis with map."""

import streamlit as st
import plotly.express as px
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database.connection import init_db
from database.models import (
    get_all_dcs, get_routes_by_dc, get_customers_by_dc,
    get_all_stops, get_leads_with_scores, get_dc,
)
from reports.dc_report import generate_dc_report
from maps.visualizations import create_dc_map

init_db()

st.set_page_config(page_title="DC View", page_icon="🏢", layout="wide")
st.title("🏢 Distribution Center View")

dcs = get_all_dcs()
if dcs.empty:
    st.info("No distribution centers found. Go to **Upload Data** to import your data.")
    st.stop()

# DC selector
dc_options = {row["id"]: f"{row['code']} - {row['name']}" for _, row in dcs.iterrows()}
selected_dc_id = st.selectbox(
    "Select Distribution Center",
    options=list(dc_options.keys()),
    format_func=lambda x: dc_options[x],
)

if selected_dc_id:
    report = generate_dc_report(selected_dc_id)

    if not report:
        st.error("Could not generate report for this DC.")
        st.stop()

    summary = report["summary"]

    # Summary metrics
    st.markdown("---")
    st.markdown(f"### {summary['dc_name']} ({summary['dc_code']})")
    st.markdown(f"📍 {summary['dc_address']}")

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Routes", summary["total_routes"])
    with col2:
        st.metric("Customers", summary["total_customers"])
    with col3:
        st.metric("Total Leads", summary["total_leads"])
    with col4:
        st.metric("Core Segment Leads", summary["core_segment_leads"])
    with col5:
        st.metric("Est. Revenue Opportunity", f"${summary['estimated_revenue_opportunity']:,.0f}/wk")

    # Grade distribution
    st.markdown("---")
    col1, col2 = st.columns([1, 2])

    with col1:
        st.markdown("#### Lead Grades")
        grades = summary["grade_distribution"]
        for grade in ["A", "B", "C", "D", "F"]:
            count = grades.get(grade, 0)
            label = {"A": "🔥 Hot", "B": "💪 Strong", "C": "📊 Moderate", "D": "📉 Low", "F": "❌ Poor"}
            st.write(f"**{grade}** {label[grade]}: {count}")

    with col2:
        st.markdown("#### Route Comparison")
        if not report["route_comparison"].empty:
            rc = report["route_comparison"]
            fig = px.bar(
                rc, x="route_code", y="lead_count",
                color="avg_lead_score",
                color_continuous_scale="RdYlGn",
                labels={"route_code": "Route", "lead_count": "Leads", "avg_lead_score": "Avg Score"},
                text="a_leads",
            )
            fig.update_traces(texttemplate="%{text} A-leads", textposition="outside")
            fig.update_layout(height=350)
            st.plotly_chart(fig, use_container_width=True)

    # Map
    st.markdown("---")
    st.markdown("#### DC Coverage Map")
    st.markdown("Shows all routes (colored lines), delivery stops, and prospects (color-coded by grade)")

    dc_info = get_dc(selected_dc_id)
    routes = get_routes_by_dc(selected_dc_id)
    customers = get_customers_by_dc(selected_dc_id)
    all_stops = get_all_stops()
    dc_stops = all_stops[all_stops["dc_id"] == selected_dc_id] if not all_stops.empty and "dc_id" in all_stops.columns else pd.DataFrame()
    scored = get_leads_with_scores()
    dc_leads = scored[scored["nearest_dc_id"] == selected_dc_id] if not scored.empty and "nearest_dc_id" in scored.columns else pd.DataFrame()

    try:
        from streamlit_folium import st_folium
        m = create_dc_map(dc_info, routes, customers, dc_stops, dc_leads)
        st_folium(m, width=None, height=500, use_container_width=True)
    except ImportError:
        st.warning("Install streamlit-folium for interactive maps: `pip install streamlit-folium`")

    # Route comparison table
    st.markdown("---")
    st.markdown("#### Route Details")
    if not report["route_comparison"].empty:
        rc = report["route_comparison"].copy()
        rc.columns = ["Route", "Name", "Days", "Customers", "Revenue/wk",
                       "Leads", "Avg Score", "A Leads", "B Leads", "Lead Revenue Opp."]
        st.dataframe(rc, use_container_width=True, hide_index=True)

    # Top leads
    st.markdown("---")
    st.markdown("#### Top 20 Leads")
    if not report["top_leads"].empty:
        tl = report["top_leads"].copy()
        display_cols = {
            "name": "Business Name", "business_type": "Type", "segment": "Segment",
            "total_score": "Score", "score_grade": "Grade", "is_core_segment": "Core",
            "nearest_route_stop_distance_mi": "Distance (mi)",
            "nearest_route_code": "Nearest Route", "nearest_stop_name": "Nearest Stop",
            "estimated_weekly_revenue": "Est. Rev/wk",
        }
        available = {k: v for k, v in display_cols.items() if k in tl.columns}
        tl_display = tl[list(available.keys())].copy()
        tl_display.columns = list(available.values())
        st.dataframe(tl_display, use_container_width=True, hide_index=True)

    # Segment analysis
    st.markdown("---")
    st.markdown("#### Segment Analysis")
    st.markdown("Compare your existing customer segments vs. available leads to find growth opportunities")
    if not report["segment_analysis"].empty:
        sa = report["segment_analysis"]
        fig = px.bar(
            sa, x="segment", y=["existing_customers", "available_leads"],
            barmode="group",
            labels={"value": "Count", "segment": "Segment", "variable": ""},
            color_discrete_map={"existing_customers": "#2196F3", "available_leads": "#FF9800"},
        )
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)
