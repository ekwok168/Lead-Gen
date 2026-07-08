"""Analytics page - Forecasting, territory performance, and team productivity."""

import sys
import os

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database.connection import init_db
from reports.analytics import (
    compute_pipeline_forecast, compute_territory_performance,
    compute_salesperson_leaderboard, compute_revenue_trending,
    compute_activity_metrics,
)
from reports.export import export_analytics_excel
from utils.auth import require_auth

init_db()

st.set_page_config(page_title="Analytics", page_icon="📊", layout="wide")
require_auth()
st.title("📊 Analytics")
st.markdown("Forecasting, territory performance, and team productivity in one place")


def money(value):
    if value is None or pd.isna(value):
        return "$0/wk"
    return f"${value:,.0f}/wk"


def col_of(df, name):
    if name in df.columns:
        return name
    for c in df.columns:
        if name in c.lower():
            return c
    return None


# ---------------------------------------------------------------------------
# Forecast
# ---------------------------------------------------------------------------

st.markdown("### 💰 Forecast")

forecast = compute_pipeline_forecast() or {}
by_stage = forecast.get("by_stage")
if by_stage is None:
    by_stage = pd.DataFrame()

if by_stage.empty:
    st.info("No open deals to forecast yet. Create deals on the **📈 Pipeline** page to build your forecast.")
else:
    count_col = col_of(by_stage, "deal_count")
    open_deal_total = int(by_stage[count_col].fillna(0).sum()) if count_col else 0

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Weighted Pipeline", money(forecast.get("weighted_total")))
    with col2:
        st.metric("Best Case", money(forecast.get("best_case")))
    with col3:
        st.metric("Open Deals", open_deal_total)

    stage_col = col_of(by_stage, "stage_name")
    weighted_col = col_of(by_stage, "weighted_revenue")
    if stage_col and weighted_col:
        fig = go.Figure(go.Bar(
            x=by_stage[stage_col],
            y=by_stage[weighted_col].fillna(0),
            marker_color="#2196F3",
            hovertemplate="%{x}: $%{y:,.0f}/wk<extra></extra>",
        ))
        fig.update_layout(height=350, margin=dict(l=10, r=10, t=10, b=10),
                          yaxis_title="Weighted Revenue ($/wk)")
        st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# Territory performance
# ---------------------------------------------------------------------------

st.markdown("---")
st.markdown("### 🗺️ Territory Performance")

territory = compute_territory_performance()
if territory is None:
    territory = pd.DataFrame()

if territory.empty:
    st.info("No territory data yet. Upload routes and score leads to compare territories.")
else:
    pipeline_col = col_of(territory, "pipeline_revenue")
    territory_display = territory.copy()
    if pipeline_col:
        territory_display = territory_display.sort_values(pipeline_col, ascending=False)
    labels = {
        "route_code": "Route",
        "route_name": "Route Name",
        "customer_count": "Customers",
        "total_weekly_revenue": "Weekly Revenue ($)",
        "lead_count": "Leads",
        "a_b_lead_count": "A/B Leads",
        "open_deal_count": "Open Deals",
        "pipeline_revenue": "Pipeline ($/wk)",
    }
    territory_display = territory_display.rename(
        columns={k: v for k, v in labels.items() if k in territory_display.columns}
    )
    st.dataframe(territory_display, use_container_width=True, hide_index=True)
    st.caption(
        "Per route: current customers and their weekly revenue, scored leads "
        "(A/B = top grades), open deals, and the weekly revenue those deals would add."
    )

# ---------------------------------------------------------------------------
# Salesperson leaderboard
# ---------------------------------------------------------------------------

st.markdown("---")
st.markdown("### 🏆 Salesperson Leaderboard")

lb_days = st.selectbox("Period", [30, 60, 90], index=2,
                       format_func=lambda d: f"Last {d} days", key="leaderboard_days")

leaderboard = compute_salesperson_leaderboard(days=lb_days)
if leaderboard is None:
    leaderboard = pd.DataFrame()

if leaderboard.empty:
    st.info("No salesperson data yet. Assign salespeople to deals and log activities to build the leaderboard.")
else:
    won_rev_col = col_of(leaderboard, "won_revenue")
    lb_display = leaderboard.copy()
    if won_rev_col:
        lb_display = lb_display.sort_values(won_rev_col, ascending=False)
    rate_col = col_of(lb_display, "win_rate")
    if rate_col:
        rates = pd.to_numeric(lb_display[rate_col], errors="coerce")
        if rates.notna().any() and rates.max() <= 1:
            rates = rates * 100
        lb_display[rate_col] = rates.map(lambda v: f"{v:.0f}%" if pd.notna(v) else "—")
    labels = {
        "assigned_salesperson": "Salesperson",
        "salesperson": "Salesperson",
        "won_count": "Deals Won",
        "won_revenue": "Won Revenue ($/wk)",
        "open_count": "Open Deals",
        "open_pipeline": "Open Pipeline ($/wk)",
        "activities_logged": "Activities",
        "win_rate": "Win Rate",
    }
    lb_display = lb_display.rename(columns={k: v for k, v in labels.items() if k in lb_display.columns})
    st.dataframe(lb_display, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Revenue trend
# ---------------------------------------------------------------------------

st.markdown("---")
st.markdown("### 📈 Revenue Trend")

trend_months = st.slider("Months to include", min_value=3, max_value=12, value=6)

trending = compute_revenue_trending(months=trend_months)
if trending is None:
    trending = pd.DataFrame()

month_col = col_of(trending, "month") if not trending.empty else None
if trending.empty or not month_col:
    st.info("No trend data yet. New leads and won deals will show up here month by month.")
else:
    won_col = col_of(trending, "deals_won")
    rev_col = col_of(trending, "revenue_won")
    leads_col = col_of(trending, "new_leads")

    fig = go.Figure()
    if won_col:
        fig.add_trace(go.Bar(
            x=trending[month_col], y=trending[won_col].fillna(0),
            name="Deals Won", marker_color="#2E7D32",
        ))
    if leads_col:
        fig.add_trace(go.Bar(
            x=trending[month_col], y=trending[leads_col].fillna(0),
            name="New Leads", marker_color="#9e9e9e",
        ))
    if rev_col:
        fig.add_trace(go.Scatter(
            x=trending[month_col], y=trending[rev_col].fillna(0),
            name="Revenue Won ($/wk)", mode="lines+markers",
            line=dict(color="#2196F3", width=3), yaxis="y2",
        ))
    fig.update_layout(
        height=380, margin=dict(l=10, r=10, t=30, b=10),
        barmode="group",
        yaxis=dict(title="Count"),
        yaxis2=dict(title="Revenue Won ($/wk)", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# Activity
# ---------------------------------------------------------------------------

st.markdown("---")
st.markdown("### 🔄 Activity")

activity_days = st.selectbox("Window", [30, 60, 90], index=0,
                             format_func=lambda d: f"Last {d} days", key="activity_days")

activity = compute_activity_metrics(days=activity_days) or {}
by_type = activity.get("by_type")
by_person = activity.get("by_person")
total_activities = int(activity.get("total") or 0)

if total_activities == 0:
    st.info("No activities logged in this window. Log calls and meetings from the **Lead Explorer** or **Contacts** page.")
else:
    st.metric("Activities Logged", total_activities)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### By Type")
        if by_type is not None and not by_type.empty:
            type_col = col_of(by_type, "activity_type") or by_type.columns[0]
            count_col = col_of(by_type, "count") or by_type.columns[-1]
            fig = px.bar(
                by_type, x=type_col, y=count_col,
                labels={type_col: "Activity Type", count_col: "Count"},
                color_discrete_sequence=["#2196F3"],
            )
            fig.update_layout(height=300, showlegend=False, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption("No breakdown by type available.")
    with col2:
        st.markdown("#### By Person")
        if by_person is not None and not by_person.empty:
            person_col = col_of(by_person, "logged_by") or by_person.columns[0]
            count_col = col_of(by_person, "count") or by_person.columns[-1]
            fig = px.bar(
                by_person, x=person_col, y=count_col,
                labels={person_col: "Logged By", count_col: "Count"},
                color_discrete_sequence=["#2E7D32"],
            )
            fig.update_layout(height=300, showlegend=False, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption("No breakdown by person available.")

# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

st.markdown("---")
st.markdown("### ⬇️ Export")

excel_data = export_analytics_excel(forecast, territory, leaderboard, trending)
st.download_button(
    "⬇️ Download Analytics (Excel)",
    excel_data,
    "analytics.xlsx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)
