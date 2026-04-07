"""Lead Explorer page - Search, filter, and manage individual leads."""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database.connection import init_db
from database.models import (
    get_leads_with_scores, update_lead_status, update_lead_assignment,
    update_lead_notes, delete_lead,
)
from scoring.engine import generate_why_text
import config

init_db()

st.set_page_config(page_title="Lead Explorer", page_icon="🔍", layout="wide")
st.title("🔍 Lead Explorer")

scored = get_leads_with_scores()

if scored.empty:
    st.info("No leads found. Go to **Upload Data** to import prospects.")
    st.stop()

has_scores = "total_score" in scored.columns and not scored["total_score"].isna().all()

# Filters
st.markdown("### Filters")
col1, col2, col3, col4 = st.columns(4)

with col1:
    if has_scores:
        grade_filter = st.multiselect("Grade", ["A", "B", "C", "D", "F"], default=["A", "B", "C"])
    else:
        grade_filter = []

with col2:
    btype_options = sorted(scored["business_type"].dropna().unique().tolist())
    btype_filter = st.multiselect("Business Type", btype_options)

with col3:
    status_filter = st.multiselect("Status", config.LEAD_STATUSES)

with col4:
    search = st.text_input("Search by name")

# Apply filters
filtered = scored.copy()

if grade_filter and has_scores:
    filtered = filtered[filtered["score_grade"].isin(grade_filter)]
if btype_filter:
    filtered = filtered[filtered["business_type"].isin(btype_filter)]
if status_filter:
    filtered = filtered[filtered["status"].isin(status_filter)]
if search:
    filtered = filtered[filtered["name"].str.contains(search, case=False, na=False)]

# Core segment filter
col1, col2 = st.columns(2)
with col1:
    core_only = st.checkbox("Show only core segment leads")
    if core_only and has_scores:
        filtered = filtered[filtered["is_core_segment"] == 1]

with col2:
    if has_scores:
        max_dist = st.slider("Max distance to nearest stop (miles)", 0.0, 25.0, 10.0, 0.5)
        if "nearest_route_stop_distance_mi" in filtered.columns:
            filtered = filtered[filtered["nearest_route_stop_distance_mi"] <= max_dist]

st.markdown(f"**Showing {len(filtered)} of {len(scored)} leads**")

st.markdown("---")

# Results table
if not filtered.empty:
    display_cols = {
        "name": "Business Name",
        "business_type": "Type",
        "segment": "Segment",
        "city": "City",
    }
    if has_scores:
        display_cols.update({
            "total_score": "Score",
            "score_grade": "Grade",
            "is_core_segment": "Core",
            "nearest_route_stop_distance_mi": "Dist (mi)",
            "nearest_route_code": "Route",
            "nearest_stop_name": "Nearest Stop",
        })
    display_cols.update({
        "estimated_weekly_revenue": "Est. Rev/wk",
        "phone": "Phone",
        "status": "Status",
        "assigned_salesperson": "Assigned To",
    })

    available = {k: v for k, v in display_cols.items() if k in filtered.columns}
    display = filtered[list(available.keys())].copy()
    display.columns = list(available.values())

    # Sort by score if available
    if "Score" in display.columns:
        display = display.sort_values("Score", ascending=False)

    st.dataframe(display, use_container_width=True, hide_index=True, height=400)

    # Lead detail view
    st.markdown("---")
    st.markdown("### Lead Details")
    st.markdown("Select a lead to view full details and update status")

    lead_options = {row["id"]: f"{row['name']} ({row.get('score_grade', 'N/A')})" for _, row in filtered.iterrows()}
    selected_lead_id = st.selectbox("Select Lead", options=list(lead_options.keys()),
                                     format_func=lambda x: lead_options[x])

    if selected_lead_id:
        lead = filtered[filtered["id"] == selected_lead_id].iloc[0]

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### Business Information")
            st.write(f"**Name:** {lead.get('name', 'N/A')}")
            st.write(f"**Address:** {lead.get('address', 'N/A')}, {lead.get('city', '')} {lead.get('state', '')} {lead.get('zip_code', '')}")
            st.write(f"**Type:** {lead.get('business_type', 'N/A')}")
            st.write(f"**Segment:** {lead.get('segment', 'N/A')}")
            st.write(f"**Phone:** {lead.get('phone', 'N/A')}")
            st.write(f"**Website:** {lead.get('website', 'N/A')}")
            st.write(f"**Source:** {lead.get('source', 'N/A')}")
            st.write(f"**Est. Weekly Revenue:** ${lead.get('estimated_weekly_revenue', 0):,.0f}")

        with col2:
            if has_scores:
                st.markdown("#### Score Breakdown")

                # Radar chart
                categories = ["Proximity", "Segment", "Density", "Revenue"]
                values = [
                    lead.get("proximity_score", 0),
                    lead.get("segment_score", 0),
                    lead.get("density_score", 0),
                    lead.get("revenue_score", 0),
                ]

                fig = go.Figure(data=go.Scatterpolar(
                    r=values + [values[0]],
                    theta=categories + [categories[0]],
                    fill="toself",
                    fillcolor="rgba(33, 150, 243, 0.2)",
                    line=dict(color="#2196F3"),
                ))
                fig.update_layout(
                    polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                    showlegend=False,
                    height=300,
                    margin=dict(l=40, r=40, t=20, b=20),
                )
                st.plotly_chart(fig, use_container_width=True)

                st.write(f"**Total Score:** {lead.get('total_score', 0):.0f} (Grade **{lead.get('score_grade', 'N/A')}**)")
                if lead.get("is_core_segment"):
                    st.success("⭐ This is a **Core Segment** lead")

                st.write(f"**Nearest Route:** {lead.get('nearest_route_code', 'N/A')}")
                st.write(f"**Nearest Stop:** {lead.get('nearest_stop_name', 'N/A')} ({lead.get('nearest_route_stop_distance_mi', 0):.1f} mi)")

        # Why this lead
        if has_scores:
            why = generate_why_text(lead)
            st.success(f"💡 **Why This Lead?** {why}")

        # Actions
        st.markdown("---")
        st.markdown("#### Actions")

        col1, col2, col3 = st.columns(3)

        with col1:
            current_status = lead.get("status", "New")
            new_status = st.selectbox(
                "Update Status",
                config.LEAD_STATUSES,
                index=config.LEAD_STATUSES.index(current_status) if current_status in config.LEAD_STATUSES else 0,
                key=f"status_{selected_lead_id}",
            )
            if st.button("Save Status", key=f"save_status_{selected_lead_id}"):
                update_lead_status(selected_lead_id, new_status)
                st.success(f"Status updated to: {new_status}")
                st.rerun()

        with col2:
            current_assign = lead.get("assigned_salesperson", "") or ""
            new_assign = st.text_input(
                "Assign Salesperson",
                value=current_assign,
                key=f"assign_{selected_lead_id}",
            )
            if st.button("Save Assignment", key=f"save_assign_{selected_lead_id}"):
                update_lead_assignment(selected_lead_id, new_assign)
                st.success(f"Assigned to: {new_assign}")
                st.rerun()

        with col3:
            current_notes = lead.get("notes", "") or ""
            new_notes = st.text_area(
                "Notes",
                value=current_notes,
                key=f"notes_{selected_lead_id}",
            )
            if st.button("Save Notes", key=f"save_notes_{selected_lead_id}"):
                update_lead_notes(selected_lead_id, new_notes)
                st.success("Notes saved!")

        # Delete
        if st.button("🗑️ Delete This Lead", type="secondary", key=f"delete_{selected_lead_id}"):
            delete_lead(selected_lead_id)
            st.success("Lead deleted.")
            st.rerun()

else:
    st.info("No leads match your filters.")
