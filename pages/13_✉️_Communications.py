"""Communications page - Email templates, compose, and call logging."""

import sys
import os

import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database.connection import init_db, seed_communication_templates
from database.models import (
    get_all_leads, get_contacts_by_lead,
    insert_activity, get_activities_by_lead,
    get_all_templates, get_template,
    insert_template, update_template, delete_template,
    insert_email, get_emails_by_lead, mark_email_sent,
)
from utils.auth import require_auth
from utils.cached import invalidate

init_db()
seed_communication_templates()

st.set_page_config(page_title="Communications", page_icon="✉️", layout="wide")
require_auth()
st.title("✉️ Communications")
st.markdown("Email templates, drafting, and call logging")

TEMPLATE_TYPES = ["email", "call_script", "meeting_agenda"]
TEMPLATE_TYPE_LABELS = {
    "email": "✉️ Email",
    "call_script": "📞 Call Script",
    "meeting_agenda": "🤝 Meeting Agenda",
}
CALL_OUTCOMES = ["Connected", "Left Voicemail", "No Answer", "Wrong Number"]
PLACEHOLDER_HINT = (
    "Placeholders: `{business_name}`, `{contact_name}`, `{salesperson_name}` "
    "are filled in automatically when composing."
)


def text_or_none(value):
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def lead_label(row):
    name = text_or_none(row.get("name")) or "Unnamed lead"
    city = text_or_none(row.get("city"))
    return f"{name} ({city})" if city else name


def contact_label(row):
    name = " ".join(
        p for p in [text_or_none(row.get("first_name")), text_or_none(row.get("last_name"))] if p
    ) or "Unnamed contact"
    title = text_or_none(row.get("title"))
    return f"{name} — {title}" if title else name


def fill_placeholders(text, lead_row, contact_row):
    if not text:
        return ""
    business_name = text_or_none(lead_row.get("name")) or "" if lead_row is not None else ""
    contact_name = "there"
    if contact_row is not None:
        contact_name = text_or_none(contact_row.get("first_name")) or "there"
    salesperson = ""
    if lead_row is not None:
        salesperson = text_or_none(lead_row.get("assigned_salesperson")) or ""
    return (
        text.replace("{business_name}", business_name)
        .replace("{contact_name}", contact_name)
        .replace("{salesperson_name}", salesperson)
    )


def lead_and_contact_pickers(key_prefix):
    leads = get_all_leads()
    if leads.empty:
        st.info("No leads found. Go to **Upload Data** to import prospects.")
        return None, None, None

    lead_options = {int(row["id"]): lead_label(row) for _, row in leads.iterrows()}
    lead_id = st.selectbox(
        "Lead", options=list(lead_options.keys()),
        format_func=lambda x: lead_options[x],
        key=f"{key_prefix}_lead",
    )
    lead_row = leads[leads["id"] == lead_id].iloc[0]

    contacts = get_contacts_by_lead(lead_id)
    contact_options = {None: "No contact"}
    if not contacts.empty:
        contact_options.update({int(row["id"]): contact_label(row) for _, row in contacts.iterrows()})
    contact_id = st.selectbox(
        "Contact (optional)", options=list(contact_options.keys()),
        format_func=lambda x: contact_options[x],
        key=f"{key_prefix}_contact",
    )
    contact_row = None
    if contact_id is not None:
        contact_row = contacts[contacts["id"] == contact_id].iloc[0]

    return lead_row, contact_id, contact_row


templates_tab, compose_tab, calls_tab = st.tabs(["📝 Templates", "✉️ Compose", "📞 Call Log"])

# ---------------------------------------------------------------------------
# Templates tab
# ---------------------------------------------------------------------------

with templates_tab:
    templates = get_all_templates()

    if templates.empty:
        st.info("No templates yet. Create one below.")
    else:
        st.markdown(f"**{len(templates)} template(s)**")
        template_options = {
            int(row["id"]): f"{TEMPLATE_TYPE_LABELS.get(row.get('template_type'), '📄')} {text_or_none(row.get('name')) or 'Untitled'}"
            for _, row in templates.iterrows()
        }
        selected_template_id = st.selectbox(
            "Select a template", options=list(template_options.keys()),
            format_func=lambda x: template_options[x],
        )
        template = templates[templates["id"] == selected_template_id].iloc[0]
        template_type = text_or_none(template.get("template_type")) or "email"

        subject = text_or_none(template.get("subject"))
        if subject:
            st.markdown(f"**Subject:** {subject}")
        st.code(text_or_none(template.get("body")) or "", language=None)

        with st.expander("✏️ Edit Template"):
            with st.form(f"edit_template_{selected_template_id}"):
                col1, col2 = st.columns(2)
                with col1:
                    e_name = st.text_input("Name *", value=text_or_none(template.get("name")) or "")
                    e_type = st.selectbox(
                        "Type", TEMPLATE_TYPES,
                        index=TEMPLATE_TYPES.index(template_type) if template_type in TEMPLATE_TYPES else 0,
                        format_func=lambda x: TEMPLATE_TYPE_LABELS[x],
                    )
                with col2:
                    e_subject = st.text_input("Subject", value=subject or "")
                e_body = st.text_area("Body *", value=text_or_none(template.get("body")) or "", height=200)
                st.caption(PLACEHOLDER_HINT)

                if st.form_submit_button("Save Changes", type="primary"):
                    if not e_name.strip() or not e_body.strip():
                        st.error("Name and body are required.")
                    else:
                        update_template(
                            int(selected_template_id),
                            name=e_name.strip(),
                            template_type=e_type,
                            subject=e_subject.strip() or None,
                            body=e_body.strip(),
                        )
                        invalidate()
                        st.success("Template updated!")
                        st.rerun()

        confirm_delete = st.checkbox("Confirm delete", key=f"confirm_delete_{selected_template_id}")
        if st.button("🗑️ Delete Template", key=f"delete_template_{selected_template_id}"):
            if confirm_delete:
                delete_template(int(selected_template_id))
                invalidate()
                st.success("Template deleted.")
                st.rerun()
            else:
                st.warning("Check **Confirm delete** first.")

    st.markdown("---")
    with st.expander("➕ New Template"):
        with st.form("new_template_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                n_name = st.text_input("Name *")
                n_type = st.selectbox(
                    "Type", TEMPLATE_TYPES,
                    format_func=lambda x: TEMPLATE_TYPE_LABELS[x],
                )
            with col2:
                n_subject = st.text_input("Subject")
            n_body = st.text_area("Body *", height=200)
            st.caption(PLACEHOLDER_HINT)

            if st.form_submit_button("Create Template", type="primary"):
                if not n_name.strip() or not n_body.strip():
                    st.error("Name and body are required.")
                else:
                    insert_template(
                        name=n_name.strip(),
                        template_type=n_type,
                        body=n_body.strip(),
                        subject=n_subject.strip() or None,
                    )
                    invalidate()
                    st.success(f"Template '{n_name.strip()}' created!")
                    st.rerun()

# ---------------------------------------------------------------------------
# Compose tab
# ---------------------------------------------------------------------------

with compose_tab:
    lead_row, contact_id, contact_row = lead_and_contact_pickers("compose")

    if lead_row is not None:
        lead_id = int(lead_row["id"])

        templates = get_all_templates()
        email_templates = pd.DataFrame()
        if not templates.empty and "template_type" in templates.columns:
            email_templates = templates[templates["template_type"] == "email"]

        compose_template_options = {None: "Blank"}
        if not email_templates.empty:
            compose_template_options.update({
                int(row["id"]): text_or_none(row.get("name")) or "Untitled"
                for _, row in email_templates.iterrows()
            })
        compose_template_id = st.selectbox(
            "Template", options=list(compose_template_options.keys()),
            format_func=lambda x: compose_template_options[x],
        )

        default_subject = ""
        default_body = ""
        if compose_template_id is not None:
            tmpl = email_templates[email_templates["id"] == compose_template_id].iloc[0]
            default_subject = fill_placeholders(text_or_none(tmpl.get("subject")) or "", lead_row, contact_row)
            default_body = fill_placeholders(text_or_none(tmpl.get("body")) or "", lead_row, contact_row)

        default_to = ""
        if contact_row is not None:
            default_to = text_or_none(contact_row.get("email")) or ""

        state_key = f"{lead_id}_{contact_id}_{compose_template_id}"
        to_address = st.text_input("To", value=default_to, key=f"compose_to_{state_key}")
        email_subject = st.text_input("Subject", value=default_subject, key=f"compose_subject_{state_key}")
        email_body = st.text_area("Body", value=default_body, height=250, key=f"compose_body_{state_key}")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("💾 Save Draft", use_container_width=True):
                if not email_body.strip():
                    st.error("Body is required.")
                else:
                    insert_email(
                        subject=email_subject.strip() or None,
                        body=email_body.strip(),
                        to_address=to_address.strip() or None,
                        lead_id=lead_id,
                        contact_id=contact_id,
                        template_id=compose_template_id,
                        status="Draft",
                    )
                    invalidate()
                    st.success("Draft saved!")
        with col2:
            if st.button("📋 Mark as Sent & Log", type="primary", use_container_width=True):
                if not email_body.strip():
                    st.error("Body is required.")
                else:
                    email_id = insert_email(
                        subject=email_subject.strip() or None,
                        body=email_body.strip(),
                        to_address=to_address.strip() or None,
                        lead_id=lead_id,
                        contact_id=contact_id,
                        template_id=compose_template_id,
                        status="Draft",
                    )
                    mark_email_sent(email_id)
                    insert_activity(
                        activity_type="Email",
                        subject=email_subject.strip() or "Email sent",
                        description=f"To: {to_address.strip() or 'N/A'}",
                        lead_id=lead_id,
                        contact_id=contact_id,
                    )
                    invalidate()
                    st.success("Email marked as sent and logged to the activity timeline!")

        if email_body.strip():
            st.markdown("**Final email body**")
            st.code(email_body, language=None)
            st.caption("Copy and send from your email client — this tool doesn't send email.")

        emails = get_emails_by_lead(lead_id)
        if not emails.empty:
            st.markdown("---")
            st.markdown(f"#### 📨 Emails for {text_or_none(lead_row.get('name')) or 'this lead'}")
            for _, email in emails.iterrows():
                status = text_or_none(email.get("status")) or "Draft"
                icon = "📤" if status == "Sent" else "📝"
                subject = text_or_none(email.get("subject")) or "(no subject)"
                created = str(email.get("created_at") or "")[:16]
                line = f"{icon} **{subject}** — {status}"
                if created:
                    line += f" · {created}"
                to_addr = text_or_none(email.get("to_address"))
                if to_addr:
                    line += f" · {to_addr}"
                st.markdown(line)

# ---------------------------------------------------------------------------
# Call Log tab
# ---------------------------------------------------------------------------

with calls_tab:
    lead_row, contact_id, contact_row = lead_and_contact_pickers("call")

    if lead_row is not None:
        lead_id = int(lead_row["id"])

        with st.form("log_call_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                outcome = st.selectbox("Outcome", CALL_OUTCOMES)
                duration = st.number_input("Duration (minutes)", min_value=0, value=0, step=1)
            with col2:
                logged_by = st.text_input("Logged By")
            notes = st.text_area("Notes")

            if st.form_submit_button("📞 Log Call", type="primary"):
                description = notes.strip() or None
                if duration:
                    description = f"Duration: {int(duration)} min" + (f"\n{description}" if description else "")
                insert_activity(
                    activity_type="Call",
                    subject=f"Call - {outcome}",
                    description=description,
                    outcome=outcome,
                    lead_id=lead_id,
                    contact_id=contact_id,
                    logged_by=logged_by.strip() or None,
                )
                invalidate()
                st.success("Call logged!")
                st.rerun()

        st.markdown("---")
        st.markdown(f"#### 📋 Recent Calls & Emails for {text_or_none(lead_row.get('name')) or 'this lead'}")

        activities = get_activities_by_lead(lead_id)
        if not activities.empty and "activity_type" in activities.columns:
            activities = activities[activities["activity_type"].isin(["Call", "Email"])]
        if activities.empty:
            st.caption("No calls or emails logged yet for this lead.")
        else:
            if "activity_date" in activities.columns:
                activities = activities.sort_values("activity_date", ascending=False)
            for _, activity in activities.iterrows():
                icon = "📞" if activity.get("activity_type") == "Call" else "✉️"
                subject = text_or_none(activity.get("subject")) or activity.get("activity_type")
                date = str(activity.get("activity_date") or "")[:16]
                header = f"{icon} **{subject}** — {date}"
                by = text_or_none(activity.get("logged_by"))
                if by:
                    header += f" · {by}"
                st.markdown(header)
                desc = text_or_none(activity.get("description"))
                if desc:
                    st.caption(desc)
                out = text_or_none(activity.get("outcome"))
                if out:
                    st.caption(f"Outcome: {out}")
