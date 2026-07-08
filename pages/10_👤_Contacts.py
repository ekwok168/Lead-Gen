"""Contacts page - Manage contacts and log interactions."""

import streamlit as st
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database.connection import init_db
from database.models import (
    get_all_leads, get_all_customers,
    insert_contact, get_all_contacts, get_contact,
    update_contact, delete_contact,
    insert_activity, get_activities_by_contact,
)
from utils.auth import require_auth
import config

init_db()

st.set_page_config(page_title="Contacts", page_icon="👤", layout="wide")
require_auth()
st.title("👤 Contacts")
st.markdown("Keep track of the people behind your leads and customers, and log every interaction")

ACTIVITY_ICONS = {"Call": "📞", "Email": "✉️", "Meeting": "🤝", "Note": "📝"}

contacts = get_all_contacts()
leads = get_all_leads()
customers = get_all_customers()

# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Total Contacts", len(contacts))
with col2:
    linked_leads = int(contacts["lead_id"].notna().sum()) if not contacts.empty else 0
    st.metric("Linked to Leads", linked_leads)
with col3:
    linked_customers = int(contacts["customer_id"].notna().sum()) if not contacts.empty else 0
    st.metric("Linked to Customers", linked_customers)

# ---------------------------------------------------------------------------
# Add contact
# ---------------------------------------------------------------------------

lead_options = {None: "None"}
if not leads.empty:
    lead_options.update({int(row["id"]): f"{row['name']} ({row['id']})" for _, row in leads.iterrows()})

customer_options = {None: "None"}
if not customers.empty:
    customer_options.update({int(row["id"]): f"{row['name']} ({row['id']})" for _, row in customers.iterrows()})

add_contact_ver = st.session_state.setdefault("add_contact_ver", 0)

with st.expander("➕ Add Contact"):
    with st.form(f"add_contact_form_{add_contact_ver}", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            first_name = st.text_input("First Name *")
            last_name = st.text_input("Last Name")
            title = st.text_input("Title")
            email = st.text_input("Email")
        with col2:
            phone = st.text_input("Phone")
            mobile_phone = st.text_input("Mobile Phone")
            preferred_method = st.selectbox("Preferred Contact Method", config.CONTACT_METHODS)
            is_primary = st.checkbox("Primary contact for this business")

        col1, col2 = st.columns(2)
        with col1:
            link_lead = st.selectbox("Link to Lead", options=list(lead_options.keys()),
                                     format_func=lambda x: lead_options[x])
        with col2:
            link_customer = st.selectbox("Link to Customer", options=list(customer_options.keys()),
                                         format_func=lambda x: customer_options[x])

        notes = st.text_area("Notes")

        if st.form_submit_button("Save Contact", type="primary"):
            if not first_name.strip():
                st.error("First name is required.")
            else:
                insert_contact(
                    first_name=first_name.strip(),
                    last_name=last_name.strip() or None,
                    title=title.strip() or None,
                    email=email.strip() or None,
                    phone=phone.strip() or None,
                    mobile_phone=mobile_phone.strip() or None,
                    preferred_contact_method=preferred_method,
                    is_primary=1 if is_primary else 0,
                    notes=notes.strip() or None,
                    lead_id=link_lead,
                    customer_id=link_customer,
                )
                st.session_state["add_contact_ver"] = add_contact_ver + 1
                st.success(f"Contact {first_name.strip()} added!")
                st.rerun()

# ---------------------------------------------------------------------------
# Contact list
# ---------------------------------------------------------------------------

st.markdown("---")
st.markdown("### Contact List")

if contacts.empty:
    st.info("No contacts yet. Use **➕ Add Contact** above to create your first one.")
    st.stop()

contacts = contacts.copy()
contacts["full_name"] = (
    contacts["first_name"].fillna("") + " " + contacts["last_name"].fillna("")
).str.strip()
contacts["linked_business"] = contacts["lead_name"].fillna(contacts["customer_name"])

search = st.text_input("Search by name, email, or company")

filtered = contacts
if search:
    mask = (
        contacts["full_name"].str.contains(search, case=False, na=False)
        | contacts["email"].str.contains(search, case=False, na=False)
        | contacts["linked_business"].str.contains(search, case=False, na=False)
    )
    filtered = contacts[mask]

st.markdown(f"**Showing {len(filtered)} of {len(contacts)} contacts**")

display_cols = {
    "full_name": "Name",
    "title": "Title",
    "linked_business": "Business",
    "email": "Email",
    "phone": "Phone",
    "preferred_contact_method": "Preferred Method",
    "is_primary": "Primary",
}
available = {k: v for k, v in display_cols.items() if k in filtered.columns}
display = filtered[list(available.keys())].copy()
display.columns = list(available.values())
st.dataframe(display, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Contact detail
# ---------------------------------------------------------------------------

st.markdown("---")
st.markdown("### Contact Details")

if filtered.empty:
    st.info("No contacts match your search.")
    st.stop()

contact_options = {
    int(row["id"]): f"{row['full_name']}" + (f" — {row['linked_business']}" if pd.notna(row["linked_business"]) else "")
    for _, row in filtered.iterrows()
}
selected_id = st.selectbox("Select Contact", options=list(contact_options.keys()),
                           format_func=lambda x: contact_options[x])

contact = get_contact(selected_id)

if contact:
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Contact Information")
        full_name = f"{contact.get('first_name', '')} {contact.get('last_name') or ''}".strip()
        st.write(f"**Name:** {full_name}")
        st.write(f"**Title:** {contact.get('title') or 'N/A'}")
        st.write(f"**Email:** {contact.get('email') or 'N/A'}")
        st.write(f"**Phone:** {contact.get('phone') or 'N/A'}")
        st.write(f"**Mobile:** {contact.get('mobile_phone') or 'N/A'}")
    with col2:
        st.markdown("#### Details")
        st.write(f"**Preferred Method:** {contact.get('preferred_contact_method') or 'N/A'}")
        st.write(f"**Primary Contact:** {'Yes ⭐' if contact.get('is_primary') else 'No'}")
        row = filtered[filtered["id"] == selected_id].iloc[0]
        business = row["linked_business"] if pd.notna(row["linked_business"]) else "Not linked"
        st.write(f"**Business:** {business}")
        st.write(f"**Notes:** {contact.get('notes') or 'None'}")

    # Edit
    with st.expander("✏️ Edit Contact"):
        with st.form(f"edit_contact_{selected_id}"):
            col1, col2 = st.columns(2)
            with col1:
                e_first = st.text_input("First Name *", value=contact.get("first_name") or "")
                e_last = st.text_input("Last Name", value=contact.get("last_name") or "")
                e_title = st.text_input("Title", value=contact.get("title") or "")
                e_email = st.text_input("Email", value=contact.get("email") or "")
            with col2:
                e_phone = st.text_input("Phone", value=contact.get("phone") or "")
                e_mobile = st.text_input("Mobile Phone", value=contact.get("mobile_phone") or "")
                current_method = contact.get("preferred_contact_method") or "Phone"
                e_method = st.selectbox(
                    "Preferred Contact Method", config.CONTACT_METHODS,
                    index=config.CONTACT_METHODS.index(current_method)
                    if current_method in config.CONTACT_METHODS else 0,
                )
                e_primary = st.checkbox("Primary contact for this business",
                                        value=bool(contact.get("is_primary")))

            col1, col2 = st.columns(2)
            lead_keys = list(lead_options.keys())
            customer_keys = list(customer_options.keys())
            with col1:
                current_lead = contact.get("lead_id")
                e_lead = st.selectbox(
                    "Link to Lead", options=lead_keys,
                    index=lead_keys.index(current_lead) if current_lead in lead_keys else 0,
                    format_func=lambda x: lead_options[x],
                )
            with col2:
                current_customer = contact.get("customer_id")
                e_customer = st.selectbox(
                    "Link to Customer", options=customer_keys,
                    index=customer_keys.index(current_customer) if current_customer in customer_keys else 0,
                    format_func=lambda x: customer_options[x],
                )

            e_notes = st.text_area("Notes", value=contact.get("notes") or "")

            if st.form_submit_button("Save Changes", type="primary"):
                if not e_first.strip():
                    st.error("First name is required.")
                else:
                    update_contact(
                        selected_id,
                        first_name=e_first.strip(),
                        last_name=e_last.strip() or None,
                        title=e_title.strip() or None,
                        email=e_email.strip() or None,
                        phone=e_phone.strip() or None,
                        mobile_phone=e_mobile.strip() or None,
                        preferred_contact_method=e_method,
                        is_primary=1 if e_primary else 0,
                        notes=e_notes.strip() or None,
                        lead_id=e_lead,
                        customer_id=e_customer,
                    )
                    st.success("Contact updated!")
                    st.rerun()

    # Delete
    col1, col2 = st.columns([1, 3])
    with col1:
        confirm_delete = st.checkbox("Confirm delete", key=f"confirm_delete_{selected_id}")
    with col2:
        if st.button("🗑️ Delete This Contact", type="secondary", disabled=not confirm_delete):
            delete_contact(selected_id)
            st.success("Contact deleted.")
            st.rerun()

    # -----------------------------------------------------------------------
    # Activity timeline
    # -----------------------------------------------------------------------

    st.markdown("---")
    st.markdown("### 📅 Activity Timeline")

    with st.form(f"log_activity_{selected_id}", clear_on_submit=True):
        st.markdown("**Log a new interaction**")
        col1, col2 = st.columns(2)
        with col1:
            a_type = st.selectbox("Type", config.ACTIVITY_TYPES)
            a_subject = st.text_input("Subject")
            a_logged_by = st.text_input("Logged By")
        with col2:
            a_description = st.text_area("Description")
            a_outcome = st.text_input("Outcome")

        if st.form_submit_button("Log Activity", type="primary"):
            insert_activity(
                activity_type=a_type,
                subject=a_subject.strip() or None,
                description=a_description.strip() or None,
                outcome=a_outcome.strip() or None,
                contact_id=selected_id,
                lead_id=contact.get("lead_id"),
                customer_id=contact.get("customer_id"),
                logged_by=a_logged_by.strip() or None,
            )
            st.success("Activity logged!")
            st.rerun()

    activities = get_activities_by_contact(selected_id)

    if activities.empty:
        st.info("No activity logged for this contact yet. Use the form above to log your first interaction.")
    else:
        if "created_at" in activities.columns:
            activities = activities.sort_values("created_at", ascending=False)
        for _, act in activities.iterrows():
            icon = ACTIVITY_ICONS.get(act.get("activity_type"), "📌")
            when = act.get("created_at") or ""
            subject = act.get("subject") or "(no subject)"
            lines = [f"{icon} **{act.get('activity_type', 'Activity')}** — {subject}  \n"
                     f"<small>{when}" + (f" · logged by {act['logged_by']}" if pd.notna(act.get("logged_by")) else "") + "</small>"]
            if pd.notna(act.get("description")) and act.get("description"):
                lines.append(f"\n{act['description']}")
            if pd.notna(act.get("outcome")) and act.get("outcome"):
                lines.append(f"\n**Outcome:** {act['outcome']}")
            st.markdown("\n".join(lines), unsafe_allow_html=True)
            st.markdown("---")
