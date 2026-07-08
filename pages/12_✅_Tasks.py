"""Tasks page - Follow-ups and to-dos with due dates."""

import datetime
import sys
import os

import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database.connection import init_db
from database.models import (
    get_all_leads, get_all_deals,
    insert_task, get_all_tasks, get_overdue_tasks,
    get_tasks_due_today, get_tasks_due_this_week,
    update_task, update_task_status, delete_task,
)
from utils.auth import require_auth
from utils.cached import invalidate
import config

init_db()

st.set_page_config(page_title="Tasks", page_icon="✅", layout="wide")
require_auth()
st.title("✅ Tasks")
st.markdown("Stay on top of follow-ups and to-dos so no lead slips through the cracks")

PRIORITY_BADGES = {"Urgent": "🔴", "High": "🟠", "Medium": "🟡", "Low": "⚪"}
DONE_STATUSES = {"Completed", "Cancelled"}


def text_or_none(value):
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def linked_label(task):
    parts = []
    lead = text_or_none(task.get("lead_name"))
    if lead:
        parts.append(f"🎯 {lead}")
    deal = text_or_none(task.get("deal_name"))
    if deal:
        parts.append(f"📈 {deal}")
    return " · ".join(parts)


def parse_due(value):
    raw = text_or_none(value)
    if not raw:
        return None
    try:
        return datetime.date.fromisoformat(raw[:10])
    except ValueError:
        return None


overdue = get_overdue_tasks()
due_today = get_tasks_due_today()
due_week = get_tasks_due_this_week()
open_tasks = get_all_tasks()

# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("🔴 Overdue", len(overdue))
with col2:
    st.metric("📅 Due Today", len(due_today))
with col3:
    st.metric("🗓️ Due This Week", len(due_week))
with col4:
    st.metric("📋 Total Open", len(open_tasks))

if not overdue.empty:
    st.error(f"⏰ You have {len(overdue)} overdue task(s) that need attention!")
    with st.expander("View overdue tasks"):
        for _, task in overdue.iterrows():
            due = text_or_none(task.get("due_date")) or "No due date"
            assigned = text_or_none(task.get("assigned_to")) or "Unassigned"
            line = f"🔴 **{task.get('title') or 'Untitled task'}** — due {due} · {assigned}"
            linked = linked_label(task)
            if linked:
                line += f" · {linked}"
            st.markdown(line)

# ---------------------------------------------------------------------------
# Task list
# ---------------------------------------------------------------------------

st.markdown("---")
st.markdown("### Task List")

col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
with col1:
    assignee_filter = st.text_input("Filter by assignee")
with col2:
    priority_filter = st.multiselect("Priority", config.TASK_PRIORITIES)
with col3:
    type_filter = st.multiselect("Type", config.TASK_TYPES)
with col4:
    show_completed = st.checkbox("Show completed")

tasks = get_all_tasks(include_completed=show_completed)

filtered = tasks
if not filtered.empty:
    if assignee_filter:
        filtered = filtered[filtered["assigned_to"].str.contains(assignee_filter, case=False, na=False)]
    if priority_filter:
        filtered = filtered[filtered["priority"].isin(priority_filter)]
    if type_filter:
        filtered = filtered[filtered["task_type"].isin(type_filter)]

if tasks.empty:
    st.info("No tasks yet. Use **➕ Create Task** below to add your first one.")
elif filtered.empty:
    st.info("No tasks match your filters.")
else:
    st.markdown(f"**Showing {len(filtered)} of {len(tasks)} tasks**")
    today = datetime.date.today()

    for _, task in filtered.iterrows():
        task_id = int(task["id"])
        status = text_or_none(task.get("status")) or "Open"
        priority = text_or_none(task.get("priority")) or "Medium"
        due_date = parse_due(task.get("due_date"))
        is_done = status in DONE_STATUSES
        is_overdue = due_date is not None and due_date < today and not is_done

        c1, c2, c3, c4, c5, c6 = st.columns([1, 1.2, 3.5, 2.5, 1.8, 1.5])
        with c1:
            done = st.checkbox("Done", value=status == "Completed", key=f"done_{task_id}")
            if done and status != "Completed":
                update_task_status(task_id, "Completed")
                invalidate()
                st.rerun()
            elif not done and status == "Completed":
                update_task_status(task_id, "Open")
                invalidate()
                st.rerun()
        with c2:
            st.write(f"{PRIORITY_BADGES.get(priority, '⚪')} {priority}")
        with c3:
            st.markdown(f"**{task.get('title') or 'Untitled task'}**")
            st.caption(text_or_none(task.get("task_type")) or "Task")
        with c4:
            st.write(linked_label(task) or "—")
        with c5:
            if due_date is None:
                st.write("No due date")
            elif is_overdue:
                st.markdown(f":red[**⚠️ {due_date.isoformat()}**]")
            else:
                st.write(due_date.isoformat())
        with c6:
            st.write(text_or_none(task.get("assigned_to")) or "Unassigned")

        with st.expander("Details", expanded=False):
            description = text_or_none(task.get("description"))
            st.write(f"**Description:** {description or 'None'}")
            st.write(f"**Status:** {status}")

            with st.form(f"edit_task_{task_id}"):
                col1, col2 = st.columns(2)
                with col1:
                    e_title = st.text_input("Title *", value=text_or_none(task.get("title")) or "")
                    current_type = text_or_none(task.get("task_type")) or config.TASK_TYPES[0]
                    e_type = st.selectbox(
                        "Type", config.TASK_TYPES,
                        index=config.TASK_TYPES.index(current_type)
                        if current_type in config.TASK_TYPES else 0,
                    )
                    e_priority = st.selectbox(
                        "Priority", config.TASK_PRIORITIES,
                        index=config.TASK_PRIORITIES.index(priority)
                        if priority in config.TASK_PRIORITIES else 0,
                    )
                    e_status = st.selectbox(
                        "Status", config.TASK_STATUSES,
                        index=config.TASK_STATUSES.index(status)
                        if status in config.TASK_STATUSES else 0,
                    )
                with col2:
                    e_due = st.date_input("Due Date", value=due_date or today)
                    e_no_due = st.checkbox("No due date", value=due_date is None,
                                           key=f"edit_no_due_{task_id}")
                    e_assigned = st.text_input("Assigned To", value=text_or_none(task.get("assigned_to")) or "")
                e_description = st.text_area("Description", value=description or "")

                if st.form_submit_button("Save Changes", type="primary"):
                    if not e_title.strip():
                        st.error("Title is required.")
                    else:
                        update_task(
                            task_id,
                            title=e_title.strip(),
                            task_type=e_type,
                            priority=e_priority,
                            status=e_status,
                            due_date=None if e_no_due else e_due.isoformat(),
                            assigned_to=e_assigned.strip() or None,
                            description=e_description.strip() or None,
                        )
                        invalidate()
                        st.success("Task updated!")
                        st.rerun()

            if st.button("🗑️ Delete Task", key=f"delete_task_{task_id}"):
                delete_task(task_id)
                invalidate()
                st.success("Task deleted.")
                st.rerun()

# ---------------------------------------------------------------------------
# Create task
# ---------------------------------------------------------------------------

st.markdown("---")

leads = get_all_leads()
deals = get_all_deals()

lead_options = {None: "None"}
if not leads.empty:
    lead_options.update({int(row["id"]): f"{row['name']} ({row['id']})" for _, row in leads.iterrows()})

deal_options = {None: "None"}
if not deals.empty:
    deal_options.update({
        int(row["id"]): f"{text_or_none(row.get('name')) or 'Unnamed deal'} ({row['id']})"
        for _, row in deals.iterrows()
    })

with st.expander("➕ Create Task"):
    with st.form("create_task_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            n_title = st.text_input("Title *")
            n_type = st.selectbox("Type", config.TASK_TYPES)
            n_priority = st.selectbox(
                "Priority", config.TASK_PRIORITIES,
                index=config.TASK_PRIORITIES.index("Medium"),
            )
        with col2:
            n_due = st.date_input("Due Date", value=datetime.date.today() + datetime.timedelta(days=7))
            n_no_due = st.checkbox("No due date")
            n_assigned = st.text_input("Assigned To")
            n_created_by = st.text_input("Created By")

        col1, col2 = st.columns(2)
        with col1:
            n_lead = st.selectbox("Link to Lead", options=list(lead_options.keys()),
                                  format_func=lambda x: lead_options[x])
        with col2:
            n_deal = st.selectbox("Link to Deal", options=list(deal_options.keys()),
                                  format_func=lambda x: deal_options[x])

        n_description = st.text_area("Description")

        if st.form_submit_button("Create Task", type="primary"):
            if not n_title.strip():
                st.error("Title is required.")
            else:
                insert_task(
                    title=n_title.strip(),
                    description=n_description.strip() or None,
                    task_type=n_type,
                    priority=n_priority,
                    assigned_to=n_assigned.strip() or None,
                    due_date=None if n_no_due else n_due.isoformat(),
                    lead_id=n_lead,
                    deal_id=n_deal,
                    created_by=n_created_by.strip() or None,
                )
                invalidate()
                st.success(f"Task '{n_title.strip()}' created!")
                st.rerun()
