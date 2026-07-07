"""Dashboard page - KPIs, grade distribution, and overview."""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database.connection import init_db
from database.models import (
    get_table_counts, get_all_dcs, get_all_routes, get_all_customers,
    get_recent_activities,
)
from utils.auth import require_auth
from utils.cached import leads_with_scores

init_db()

st.set_page_config(page_title="Dashboard", page_icon="📊", layout="wide")
require_auth()
st.title("📊 Dashboard")

counts = get_table_counts()

if counts.get("leads", 0) == 0:
    st.info("No data yet. Go to **Upload Data** to import your data, or load sample data from the home page.")
    st.stop()

# KPI row
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("Distribution Centers", counts.get("distribution_centers", 0))
with col2:
    st.metric("Routes", counts.get("routes", 0))
with col3:
    st.metric("Existing Customers", counts.get("customers", 0))
with col4:
    st.metric("Total Leads", counts.get("leads", 0))
with col5:
    st.metric("Scored Leads", counts.get("lead_scores", 0))

try:
    from reports.analytics import compute_pipeline_forecast

    weighted_total = float((compute_pipeline_forecast() or {}).get("weighted_total") or 0)
    st.metric("Weighted Pipeline", f"${weighted_total:,.0f}/wk")
except Exception:
    pass

# Load scored leads
scored = leads_with_scores()

if scored.empty or "total_score" not in scored.columns or scored["total_score"].isna().all():
    st.warning("Leads have not been scored yet. Click **'Score All Leads'** in the sidebar to run scoring.")
    st.stop()

st.markdown("---")

# Grade distribution
col1, col2 = st.columns([1, 1])

with col1:
    st.markdown("### Lead Grade Distribution")
    grade_counts = scored["score_grade"].value_counts().reindex(["A", "B", "C", "D", "F"], fill_value=0)

    fig = px.bar(
        x=grade_counts.index,
        y=grade_counts.values,
        color=grade_counts.index,
        color_discrete_map={"A": "#f44336", "B": "#ff9800", "C": "#ffc107", "D": "#9e9e9e", "F": "#bdbdbd"},
        labels={"x": "Grade", "y": "Number of Leads"},
    )
    fig.update_layout(showlegend=False, height=350)
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.markdown("### Leads by Segment")
    seg_counts = scored["segment"].value_counts().head(10)

    fig = px.pie(
        values=seg_counts.values,
        names=seg_counts.index,
        hole=0.4,
    )
    fig.update_layout(height=350)
    st.plotly_chart(fig, use_container_width=True)

# Score summary metrics
st.markdown("---")
col1, col2, col3, col4 = st.columns(4)

a_count = int((scored["score_grade"] == "A").sum())
b_count = int((scored["score_grade"] == "B").sum())
core_count = int(scored["is_core_segment"].sum()) if "is_core_segment" in scored.columns else 0
avg_score = round(scored["total_score"].mean(), 1)

with col1:
    st.metric("🔥 Hot Leads (A)", a_count)
with col2:
    st.metric("💪 Strong Leads (B)", b_count)
with col3:
    st.metric("⭐ Core Segment Leads", core_count)
with col4:
    st.metric("📈 Avg Score", avg_score)

# Revenue opportunity
ab_leads = scored[scored["score_grade"].isin(["A", "B"])]
total_opportunity = ab_leads["estimated_weekly_revenue"].sum() if not ab_leads.empty else 0
st.markdown(f"### Estimated Weekly Revenue Opportunity (A+B Leads): **${total_opportunity:,.0f}**")

st.markdown("---")

# Top 10 leads table
st.markdown("### Top 10 Leads")
if not scored.empty:
    top10 = scored.nlargest(10, "total_score")
    display_cols = {
        "name": "Business Name",
        "business_type": "Type",
        "segment": "Segment",
        "total_score": "Score",
        "score_grade": "Grade",
        "is_core_segment": "Core",
        "nearest_route_stop_distance_mi": "Distance (mi)",
        "nearest_route_code": "Nearest Route",
        "estimated_weekly_revenue": "Est. Revenue/wk",
        "status": "Status",
    }
    available = {k: v for k, v in display_cols.items() if k in top10.columns}
    display = top10[list(available.keys())].copy()
    display.columns = list(available.values())
    st.dataframe(display, use_container_width=True, hide_index=True)

# Leads by route chart
st.markdown("---")
st.markdown("### Leads by Route")

if "nearest_route_code" in scored.columns:
    route_leads = scored.groupby("nearest_route_code").agg(
        lead_count=("id", "count"),
        avg_score=("total_score", "mean"),
        a_leads=("score_grade", lambda x: (x == "A").sum()),
    ).reset_index().sort_values("lead_count", ascending=True)

    if not route_leads.empty:
        fig = px.bar(
            route_leads,
            y="nearest_route_code",
            x="lead_count",
            orientation="h",
            color="avg_score",
            color_continuous_scale="RdYlGn",
            labels={"nearest_route_code": "Route", "lead_count": "Number of Leads", "avg_score": "Avg Score"},
        )
        fig.update_layout(height=max(300, len(route_leads) * 30))
        st.plotly_chart(fig, use_container_width=True)

# Score distribution histogram
st.markdown("---")
st.markdown("### Score Distribution")
fig = px.histogram(
    scored, x="total_score", nbins=20,
    labels={"total_score": "Lead Score", "count": "Number of Leads"},
    color_discrete_sequence=["#2196F3"],
)
fig.update_layout(height=300)
st.plotly_chart(fig, use_container_width=True)

# Recent activity
st.markdown("---")
st.markdown("### 🕒 Recent Activity")

ACTIVITY_ICONS = {
    "Call": "📞",
    "Email": "✉️",
    "Meeting": "🤝",
    "Note": "📝",
    "Status Change": "🔄",
}

recent = get_recent_activities(10)
if recent.empty:
    st.caption("No activities logged yet — log calls and meetings from the Lead Explorer or Contacts page.")
else:
    for _, activity in recent.iterrows():
        icon = ACTIVITY_ICONS.get(activity.get("activity_type"), "📝")
        parts = [f"{icon} **{activity.get('activity_type', '')}**"]
        if activity.get("subject"):
            parts.append(activity["subject"])
        contact_name = " ".join(
            p for p in [activity.get("first_name"), activity.get("last_name")] if isinstance(p, str) and p
        )
        lead_name = activity.get("lead_name")
        who = lead_name if isinstance(lead_name, str) and lead_name else contact_name
        if who:
            parts.append(who)
        date = str(activity.get("activity_date") or "")[:16]
        if date:
            parts.append(date)
        st.markdown(" · ".join(parts))
