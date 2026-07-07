"""Pipeline page - Track deals through your sales stages."""

import datetime
import sys
import os

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database.connection import init_db, seed_pipeline_stages
from database.models import (
    get_all_leads,
    get_pipeline_stages, insert_deal, get_all_deals, get_deal,
    update_deal, update_deal_stage, get_deal_stage_history,
    get_pipeline_summary, get_won_lost_stats,
)
from utils.auth import require_auth
from utils.cached import invalidate
import config

init_db()
seed_pipeline_stages()

st.set_page_config(page_title="Pipeline", page_icon="📈", layout="wide")
require_auth()
st.title("📈 Sales Pipeline")
st.markdown("Track every deal from first contact to closed business")

CLOSED_STAGES = {"Closed Won", "Closed Lost"}


def find_col(df, *keywords):
    for kw in keywords:
        if kw in df.columns:
            return kw
    for col in df.columns:
        low = col.lower()
        if any(skip in low for skip in ("_id", "order", "days", "pct", "probability")):
            continue
        if any(kw in low for kw in keywords):
            return col
    return None


def money(value):
    if value is None or pd.isna(value):
        return "$0/wk"
    return f"${value:,.0f}/wk"


stages = get_pipeline_stages()
deals = get_all_deals()
summary = get_pipeline_summary()
stats = get_won_lost_stats(90) or {}

if stages.empty:
    st.info("Pipeline stages are not set up yet. Restart the app to load the default stages.")
    st.stop()

stages = stages.sort_values("display_order")
open_stages = stages[~stages["name"].isin(CLOSED_STAGES)]
stage_ids = [int(s) for s in stages["id"]]
stage_names = {int(row["id"]): row["name"] for _, row in stages.iterrows()}
name_to_stage_id = {row["name"]: int(row["id"]) for _, row in stages.iterrows()}

stage_col = find_col(deals, "stage_name", "stage") if not deals.empty else None
if not deals.empty and stage_col is None:
    st.error("Deal data is missing its stage information. Please refresh the page.")
    st.stop()

open_deals = deals[~deals[stage_col].isin(CLOSED_STAGES)] if not deals.empty else deals

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

sum_name_col = find_col(summary, "name") if not summary.empty else None
sum_count_col = find_col(summary, "count") if not summary.empty else None
sum_total_col = find_col(summary, "total") if not summary.empty else None
sum_weighted_col = find_col(summary, "weighted") if not summary.empty else None

open_summary = pd.DataFrame()
if not summary.empty and sum_name_col:
    open_summary = summary[~summary[sum_name_col].isin(CLOSED_STAGES)]

weighted_total = 0.0
if not open_summary.empty and sum_weighted_col:
    weighted_total = float(open_summary[sum_weighted_col].fillna(0).sum())

won_count = int(stats.get("won_count") or 0)
lost_count = int(stats.get("lost_count") or 0)
closed_total = won_count + lost_count
win_rate_display = f"{won_count / closed_total * 100:.0f}%" if closed_total else "—"

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Open Deals", len(open_deals))
with col2:
    st.metric("Weighted Pipeline", money(weighted_total))
with col3:
    st.metric("Won (last 90 days)", won_count)
with col4:
    st.metric("Win Rate (last 90 days)", win_rate_display)

if not open_summary.empty and sum_count_col:
    funnel = open_summary.copy()
    if "display_order" in funnel.columns:
        funnel = funnel.sort_values("display_order")
    totals = funnel[sum_total_col].fillna(0) if sum_total_col else pd.Series([0] * len(funnel))
    fig = go.Figure(go.Funnel(
        y=funnel[sum_name_col],
        x=funnel[sum_count_col].fillna(0),
        customdata=totals,
        hovertemplate="%{y}: %{x} deals<br>Total value: $%{customdata:,.0f}/wk<extra></extra>",
        textinfo="value",
    ))
    fig.update_layout(height=350, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# Kanban board
# ---------------------------------------------------------------------------

st.markdown("---")
st.markdown("### Deal Board")

if deals.empty:
    st.info("No deals yet. Use **➕ Create Deal** below to add your first one.")
else:
    board_cols = st.columns(len(open_stages))
    for col, (_, stage) in zip(board_cols, open_stages.iterrows()):
        stage_name = stage["name"]
        stage_deals = deals[deals[stage_col] == stage_name]
        with col:
            st.markdown(f"**{stage_name}** ({len(stage_deals)})")
            for _, deal in stage_deals.iterrows():
                deal_id = int(deal["id"])
                with st.container(border=True):
                    st.markdown(f"**{deal.get('name') or 'Unnamed deal'}**")
                    linked = deal.get("lead_name")
                    if linked is None or pd.isna(linked):
                        linked = deal.get("customer_name")
                    if linked is not None and pd.notna(linked):
                        st.write(linked)
                    st.write(money(deal.get("expected_weekly_revenue")))
                    days = deal.get("days_in_stage")
                    if days is not None and pd.notna(days):
                        st.write(f"{int(days)} days in stage")
                    salesperson = deal.get("assigned_salesperson")
                    if salesperson is not None and pd.notna(salesperson):
                        st.caption(salesperson)

                    current_stage_id = name_to_stage_id.get(stage_name)
                    move_to = st.selectbox(
                        "Move to…",
                        options=stage_ids,
                        index=stage_ids.index(current_stage_id) if current_stage_id in stage_ids else 0,
                        format_func=lambda x: stage_names[x],
                        key=f"move_stage_{deal_id}",
                    )
                    if st.button("Move", key=f"move_go_{deal_id}"):
                        if move_to != current_stage_id:
                            update_deal_stage(deal_id, move_to)
                            invalidate()
                            st.success(f"Moved to {stage_names[move_to]}!")
                            st.rerun()
                        else:
                            st.info("Deal is already in that stage.")

# ---------------------------------------------------------------------------
# Create deal
# ---------------------------------------------------------------------------

st.markdown("---")

leads = get_all_leads()
lead_options = {None: "No linked lead"}
if not leads.empty:
    lead_options.update({int(row["id"]): f"{row['name']} ({row['id']})" for _, row in leads.iterrows()})

with st.expander("➕ Create Deal"):
    selected_lead = st.selectbox(
        "Attach to Lead",
        options=list(lead_options.keys()),
        format_func=lambda x: lead_options[x],
        key="create_deal_lead",
    )
    default_name = lead_options[selected_lead] if selected_lead is not None else ""
    if selected_lead is not None:
        default_name = str(leads[leads["id"] == selected_lead].iloc[0]["name"])

    open_stage_ids = [int(s) for s in open_stages["id"]]
    prospect_id = name_to_stage_id.get("Prospect", open_stage_ids[0] if open_stage_ids else stage_ids[0])

    with st.form("create_deal_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            deal_name = st.text_input("Deal Name *", value=default_name)
            initial_stage = st.selectbox(
                "Starting Stage",
                options=stage_ids,
                index=stage_ids.index(prospect_id) if prospect_id in stage_ids else 0,
                format_func=lambda x: stage_names[x],
            )
            expected_revenue = st.number_input("Expected Weekly Revenue ($)", min_value=0.0, step=50.0, value=0.0)
        with col2:
            close_date = st.date_input("Expected Close Date", value=datetime.date.today() + datetime.timedelta(days=30))
            salesperson = st.text_input("Salesperson")
            deal_notes = st.text_area("Notes")

        if st.form_submit_button("Create Deal", type="primary"):
            if not deal_name.strip():
                st.error("Deal name is required.")
            else:
                insert_deal(
                    name=deal_name.strip(),
                    stage_id=initial_stage,
                    lead_id=selected_lead,
                    expected_weekly_revenue=expected_revenue,
                    expected_close_date=close_date.isoformat() if close_date else None,
                    assigned_salesperson=salesperson.strip() or None,
                    notes=deal_notes.strip() or None,
                )
                invalidate()
                st.success(f"Deal '{deal_name.strip()}' created!")
                st.rerun()

# ---------------------------------------------------------------------------
# Deal detail
# ---------------------------------------------------------------------------

st.markdown("---")
st.markdown("### Deal Details")

if open_deals is None or open_deals.empty:
    st.info("No open deals to review right now.")
else:
    deal_options = {
        int(row["id"]): f"{row.get('name') or 'Unnamed deal'} — {row[stage_col]}"
        for _, row in open_deals.iterrows()
    }
    selected_deal_id = st.selectbox(
        "Select Deal",
        options=list(deal_options.keys()),
        format_func=lambda x: deal_options[x],
    )
    deal = get_deal(selected_deal_id)

    if deal:
        deal_row = open_deals[open_deals["id"] == selected_deal_id].iloc[0]
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### Deal Information")
            st.write(f"**Name:** {deal.get('name') or 'N/A'}")
            st.write(f"**Stage:** {deal_row[stage_col]}")
            linked = deal_row.get("lead_name")
            if linked is None or pd.isna(linked):
                linked = deal_row.get("customer_name")
            st.write(f"**Linked Business:** {linked if linked is not None and pd.notna(linked) else 'Not linked'}")
            st.write(f"**Expected Revenue:** {money(deal.get('expected_weekly_revenue'))}")
        with col2:
            st.markdown("#### Status")
            st.write(f"**Expected Close Date:** {deal.get('expected_close_date') or 'N/A'}")
            st.write(f"**Salesperson:** {deal.get('assigned_salesperson') or 'Unassigned'}")
            days = deal_row.get("days_in_stage")
            st.write(f"**Days in Stage:** {int(days) if days is not None and pd.notna(days) else 'N/A'}")
            st.write(f"**Notes:** {deal.get('notes') or 'None'}")

        with st.expander("✏️ Edit Deal"):
            raw_date = deal.get("expected_close_date")
            try:
                default_close = datetime.date.fromisoformat(str(raw_date)[:10]) if raw_date else datetime.date.today()
            except ValueError:
                default_close = datetime.date.today()

            with st.form(f"edit_deal_{selected_deal_id}"):
                col1, col2 = st.columns(2)
                with col1:
                    e_name = st.text_input("Deal Name *", value=deal.get("name") or "")
                    e_revenue = st.number_input(
                        "Expected Weekly Revenue ($)", min_value=0.0, step=50.0,
                        value=float(deal.get("expected_weekly_revenue") or 0),
                    )
                with col2:
                    e_close = st.date_input("Expected Close Date", value=default_close)
                    e_salesperson = st.text_input("Salesperson", value=deal.get("assigned_salesperson") or "")
                e_notes = st.text_area("Notes", value=deal.get("notes") or "")

                if st.form_submit_button("Save Changes", type="primary"):
                    if not e_name.strip():
                        st.error("Deal name is required.")
                    else:
                        update_deal(
                            selected_deal_id,
                            name=e_name.strip(),
                            expected_weekly_revenue=e_revenue,
                            expected_close_date=e_close.isoformat() if e_close else None,
                            assigned_salesperson=e_salesperson.strip() or None,
                            notes=e_notes.strip() or None,
                        )
                        invalidate()
                        st.success("Deal updated!")
                        st.rerun()

        st.markdown("#### Stage History")
        history = get_deal_stage_history(selected_deal_id)
        if history is None or history.empty:
            st.info("This deal hasn't changed stages yet.")
        else:
            history = history.copy()
            drop_cols = [c for c in history.columns if c.lower().endswith("id") or c.lower() == "id"]
            history = history.drop(columns=drop_cols)
            rename = {}
            for c in history.columns:
                low = c.lower()
                if "from" in low:
                    rename[c] = "From Stage"
                elif "to" in low:
                    rename[c] = "To Stage"
                elif "by" in low:
                    rename[c] = "Changed By"
                elif "at" in low or "date" in low:
                    rename[c] = "When"
            st.dataframe(history.rename(columns=rename), use_container_width=True, hide_index=True)

        lost_stage_id = name_to_stage_id.get("Closed Lost")
        if lost_stage_id is not None:
            st.markdown("#### Mark as Lost")
            with st.form(f"lost_deal_{selected_deal_id}"):
                loss_reason = st.text_input("Why was this deal lost?")
                if st.form_submit_button("Mark as Closed Lost"):
                    update_deal(selected_deal_id, loss_reason=loss_reason.strip() or None)
                    update_deal_stage(selected_deal_id, lost_stage_id)
                    invalidate()
                    st.success("Deal marked as Closed Lost.")
                    st.rerun()

# ---------------------------------------------------------------------------
# Win / Loss
# ---------------------------------------------------------------------------

st.markdown("---")
st.markdown("### Wins & Losses (last 90 days)")

if closed_total == 0:
    st.info("No deals have closed in the last 90 days yet.")
else:
    col1, col2 = st.columns([2, 1])
    with col1:
        fig = go.Figure(go.Bar(
            x=["Won", "Lost"],
            y=[won_count, lost_count],
            marker_color=["#2E7D32", "#C62828"],
        ))
        fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10), yaxis_title="Deals")
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        st.metric("Won Revenue", money(stats.get("won_revenue")))
        st.metric("Average Deal Size", money(stats.get("avg_deal_size")))
