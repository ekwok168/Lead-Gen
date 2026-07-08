"""Data access layer for all database entities."""

import json

import pandas as pd

from database.connection import get_connection


# ---------------------------------------------------------------------------
# Distribution Centers
# ---------------------------------------------------------------------------

def get_all_dcs():
    """Return all distribution centers as a DataFrame."""
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM distribution_centers WHERE is_active = 1", conn)
    conn.close()
    return df


def get_dc(dc_id):
    """Return a single distribution center as a dict."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM distribution_centers WHERE id = ?", (dc_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def upsert_dc(name, code, address, city, state, zip_code, latitude, longitude):
    """Insert or update a distribution center."""
    conn = get_connection()
    conn.execute(
        """INSERT INTO distribution_centers (name, code, address, city, state, zip_code, latitude, longitude)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(code) DO UPDATE SET
               name=excluded.name, address=excluded.address, city=excluded.city,
               state=excluded.state, zip_code=excluded.zip_code,
               latitude=excluded.latitude, longitude=excluded.longitude""",
        (name, code, address, city, state, zip_code, latitude, longitude),
    )
    conn.commit()
    dc_id = conn.execute("SELECT id FROM distribution_centers WHERE code = ?", (code,)).fetchone()[0]
    conn.close()
    return dc_id


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def get_routes_by_dc(dc_id):
    """Return all routes for a DC."""
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT * FROM routes WHERE dc_id = ? AND is_active = 1", conn, params=(dc_id,)
    )
    conn.close()
    return df


def get_all_routes():
    """Return all active routes."""
    conn = get_connection()
    df = pd.read_sql_query(
        """SELECT r.*, dc.name as dc_name, dc.code as dc_code
           FROM routes r JOIN distribution_centers dc ON r.dc_id = dc.id
           WHERE r.is_active = 1""",
        conn,
    )
    conn.close()
    return df


def get_route(route_id):
    """Return a single route as a dict."""
    conn = get_connection()
    row = conn.execute(
        """SELECT r.*, dc.name as dc_name, dc.code as dc_code
           FROM routes r JOIN distribution_centers dc ON r.dc_id = dc.id
           WHERE r.id = ?""",
        (route_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def upsert_route(dc_id, route_code, route_name, day_of_week=None, driver_name=None):
    """Insert or update a route."""
    conn = get_connection()
    conn.execute(
        """INSERT INTO routes (dc_id, route_code, route_name, day_of_week, driver_name)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(route_code) DO UPDATE SET
               dc_id=excluded.dc_id, route_name=excluded.route_name,
               day_of_week=excluded.day_of_week, driver_name=excluded.driver_name""",
        (dc_id, route_code, route_name, day_of_week, driver_name),
    )
    conn.commit()
    route_id = conn.execute("SELECT id FROM routes WHERE route_code = ?", (route_code,)).fetchone()[0]
    conn.close()
    return route_id


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------

def get_customers_by_route(route_id):
    """Return all customers on a route, ordered by stop sequence."""
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT * FROM customers WHERE route_id = ? AND is_active = 1 ORDER BY stop_sequence",
        conn,
        params=(route_id,),
    )
    conn.close()
    return df


def get_customers_by_dc(dc_id):
    """Return all customers for routes under a DC."""
    conn = get_connection()
    df = pd.read_sql_query(
        """SELECT c.*, r.route_code, r.route_name
           FROM customers c
           JOIN routes r ON c.route_id = r.id
           WHERE r.dc_id = ? AND c.is_active = 1""",
        conn,
        params=(dc_id,),
    )
    conn.close()
    return df


def get_all_customers():
    """Return all active customers."""
    conn = get_connection()
    df = pd.read_sql_query(
        """SELECT c.*, r.route_code, r.route_name, dc.name as dc_name
           FROM customers c
           LEFT JOIN routes r ON c.route_id = r.id
           LEFT JOIN distribution_centers dc ON r.dc_id = dc.id
           WHERE c.is_active = 1""",
        conn,
    )
    conn.close()
    return df


def insert_customer(name, address, city, state, zip_code, latitude, longitude,
                     business_type=None, segment=None, weekly_revenue=0,
                     route_id=None, stop_sequence=None):
    """Insert a new customer."""
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO customers (name, address, city, state, zip_code, latitude, longitude,
               business_type, segment, weekly_revenue, route_id, stop_sequence)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (name, address, city, state, zip_code, latitude, longitude,
         business_type, segment, weekly_revenue, route_id, stop_sequence),
    )
    conn.commit()
    customer_id = cursor.lastrowid
    conn.close()
    return customer_id


def bulk_insert_customers(df):
    """Insert multiple customers from a DataFrame."""
    conn = get_connection()
    cols = ["name", "address", "city", "state", "zip_code", "latitude", "longitude",
            "business_type", "segment", "weekly_revenue", "route_id", "stop_sequence"]
    for col in cols:
        if col not in df.columns:
            df[col] = None
    df[cols].to_sql("customers", conn, if_exists="append", index=False)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Route Stops
# ---------------------------------------------------------------------------

def get_stops_by_route(route_id):
    """Return all stops on a route in sequence order."""
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT * FROM route_stops WHERE route_id = ? ORDER BY stop_sequence",
        conn,
        params=(route_id,),
    )
    conn.close()
    return df


def get_all_stops():
    """Return all route stops."""
    conn = get_connection()
    df = pd.read_sql_query(
        """SELECT rs.*, r.route_code, r.dc_id
           FROM route_stops rs
           JOIN routes r ON rs.route_id = r.id""",
        conn,
    )
    conn.close()
    return df


def insert_route_stop(route_id, stop_sequence, latitude, longitude,
                       stop_type="customer", stop_name=None, customer_id=None):
    """Insert a route stop."""
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO route_stops (route_id, customer_id, stop_sequence, latitude, longitude,
               stop_type, stop_name)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (route_id, customer_id, stop_sequence, latitude, longitude, stop_type, stop_name),
    )
    conn.commit()
    stop_id = cursor.lastrowid
    conn.close()
    return stop_id


def rebuild_route_stops(route_id):
    """Rebuild route_stops from customers on a route, adding depot stops."""
    conn = get_connection()
    # Clear existing stops for this route
    conn.execute("DELETE FROM route_stops WHERE route_id = ?", (route_id,))

    # Get the DC for this route (depot)
    dc = conn.execute(
        """SELECT dc.* FROM distribution_centers dc
           JOIN routes r ON r.dc_id = dc.id WHERE r.id = ?""",
        (route_id,),
    ).fetchone()

    seq = 1
    # Add depot as first stop
    if dc:
        conn.execute(
            """INSERT INTO route_stops (route_id, stop_sequence, latitude, longitude, stop_type, stop_name)
               VALUES (?, ?, ?, ?, 'depot', ?)""",
            (route_id, seq, dc["latitude"], dc["longitude"], dc["name"]),
        )
        seq += 1

    # Add customer stops
    customers = conn.execute(
        "SELECT * FROM customers WHERE route_id = ? AND is_active = 1 ORDER BY stop_sequence, id",
        (route_id,),
    ).fetchall()

    for cust in customers:
        conn.execute(
            """INSERT INTO route_stops (route_id, customer_id, stop_sequence, latitude, longitude,
                   stop_type, stop_name)
               VALUES (?, ?, ?, ?, ?, 'customer', ?)""",
            (route_id, cust["id"], seq, cust["latitude"], cust["longitude"], cust["name"]),
        )
        seq += 1

    # Add depot as last stop (return)
    if dc:
        conn.execute(
            """INSERT INTO route_stops (route_id, stop_sequence, latitude, longitude, stop_type, stop_name)
               VALUES (?, ?, ?, ?, 'depot', ?)""",
            (route_id, seq, dc["latitude"], dc["longitude"], dc["name"] + " (Return)"),
        )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Leads
# ---------------------------------------------------------------------------

def get_all_leads():
    """Return all leads."""
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM leads", conn)
    conn.close()
    return df


def get_leads_with_scores():
    """Return all leads joined with their latest scores."""
    conn = get_connection()
    df = pd.read_sql_query(
        """SELECT l.*, ls.proximity_score, ls.segment_score, ls.density_score,
               ls.revenue_score, ls.total_score, ls.score_grade, ls.is_core_segment,
               ls.nearest_customer_distance_mi, ls.nearest_route_stop_distance_mi,
               ls.nearest_route_id, ls.nearest_dc_id, ls.nearest_stop_id,
               ls.suggested_insertion_sequence, ls.scored_at,
               r.route_code as nearest_route_code,
               dc.name as nearest_dc_name,
               rs.stop_name as nearest_stop_name
           FROM leads l
           LEFT JOIN lead_scores ls ON l.id = ls.lead_id
               AND ls.id = (SELECT MAX(ls2.id) FROM lead_scores ls2 WHERE ls2.lead_id = l.id)
           LEFT JOIN routes r ON ls.nearest_route_id = r.id
           LEFT JOIN distribution_centers dc ON ls.nearest_dc_id = dc.id
           LEFT JOIN route_stops rs ON ls.nearest_stop_id = rs.id""",
        conn,
    )
    conn.close()
    # Fix SQLite boolean column (stored as bytes in some drivers)
    if "is_core_segment" in df.columns:
        df["is_core_segment"] = df["is_core_segment"].apply(
            lambda x: int.from_bytes(x, "little") if isinstance(x, bytes) else (0 if pd.isna(x) else int(x))
        )
    return df


def insert_lead(name, address, city, state, zip_code, latitude, longitude,
                 business_type=None, segment=None, estimated_weekly_revenue=0,
                 phone=None, website=None, source="Manual Entry",
                 assigned_salesperson=None):
    """Insert a new lead."""
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO leads (name, address, city, state, zip_code, latitude, longitude,
               business_type, segment, estimated_weekly_revenue, phone, website, source,
               assigned_salesperson)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (name, address, city, state, zip_code, latitude, longitude,
         business_type, segment, estimated_weekly_revenue, phone, website, source,
         assigned_salesperson),
    )
    conn.commit()
    lead_id = cursor.lastrowid
    conn.close()
    return lead_id


def bulk_insert_leads(df):
    """Insert multiple leads from a DataFrame."""
    conn = get_connection()
    cols = ["name", "address", "city", "state", "zip_code", "latitude", "longitude",
            "business_type", "segment", "estimated_weekly_revenue", "phone", "website",
            "source", "status", "assigned_salesperson"]
    for col in cols:
        if col not in df.columns:
            if col == "source":
                df[col] = "File Upload"
            elif col == "status":
                df[col] = "New"
            else:
                df[col] = None
    df[cols].to_sql("leads", conn, if_exists="append", index=False)
    conn.commit()
    conn.close()


UPDATABLE_LEAD_FIELDS = {"status", "assigned_salesperson", "notes"}


def update_lead_field(lead_id, field, value):
    """Update a single allowlisted field on a lead."""
    if field not in UPDATABLE_LEAD_FIELDS:
        raise ValueError(f"Field not updatable: {field}")
    conn = get_connection()
    conn.execute(
        f"UPDATE leads SET {field} = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (value, lead_id),
    )
    conn.commit()
    conn.close()


def update_lead_status(lead_id, status):
    """Update a lead's status."""
    update_lead_field(lead_id, "status", status)


def update_lead_assignment(lead_id, salesperson):
    """Update a lead's assigned salesperson."""
    update_lead_field(lead_id, "assigned_salesperson", salesperson)


def update_lead_notes(lead_id, notes):
    """Update a lead's notes."""
    update_lead_field(lead_id, "notes", notes)


def delete_lead(lead_id):
    """Delete a lead and its scores."""
    conn = get_connection()
    conn.execute("DELETE FROM lead_scores WHERE lead_id = ?", (lead_id,))
    conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Lead Scores
# ---------------------------------------------------------------------------

def insert_lead_score(lead_id, nearest_route_id, nearest_dc_id, nearest_stop_id,
                       proximity_score, segment_score, density_score, revenue_score,
                       total_score, score_grade, is_core_segment,
                       nearest_customer_distance_mi, nearest_route_stop_distance_mi,
                       suggested_insertion_sequence=None):
    """Insert a lead score record."""
    conn = get_connection()
    conn.execute(
        """INSERT INTO lead_scores (lead_id, nearest_route_id, nearest_dc_id, nearest_stop_id,
               proximity_score, segment_score, density_score, revenue_score,
               total_score, score_grade, is_core_segment,
               nearest_customer_distance_mi, nearest_route_stop_distance_mi,
               suggested_insertion_sequence)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (lead_id, nearest_route_id, nearest_dc_id, nearest_stop_id,
         proximity_score, segment_score, density_score, revenue_score,
         total_score, score_grade, is_core_segment,
         nearest_customer_distance_mi, nearest_route_stop_distance_mi,
         suggested_insertion_sequence),
    )
    conn.commit()
    conn.close()


def replace_all_lead_scores(rows):
    """Replace all lead scores with new rows in a single transaction."""
    conn = get_connection()
    conn.execute("DELETE FROM lead_scores")
    conn.executemany(
        """INSERT INTO lead_scores (lead_id, nearest_route_id, nearest_dc_id, nearest_stop_id,
               proximity_score, segment_score, density_score, revenue_score,
               total_score, score_grade, is_core_segment,
               nearest_customer_distance_mi, nearest_route_stop_distance_mi,
               suggested_insertion_sequence)
           VALUES (:lead_id, :nearest_route_id, :nearest_dc_id, :nearest_stop_id,
               :proximity_score, :segment_score, :density_score, :revenue_score,
               :total_score, :score_grade, :is_core_segment,
               :nearest_customer_distance_mi, :nearest_route_stop_distance_mi,
               :suggested_insertion_sequence)""",
        rows,
    )
    conn.commit()
    conn.close()


def clear_scores():
    """Clear all lead scores (before re-scoring)."""
    conn = get_connection()
    conn.execute("DELETE FROM lead_scores")
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Core Segments
# ---------------------------------------------------------------------------

def get_core_segments():
    """Return all core segments."""
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM core_segments ORDER BY priority", conn)
    conn.close()
    return df


def update_core_segments(segments_df):
    """Replace all core segments with new data."""
    conn = get_connection()
    conn.execute("DELETE FROM core_segments")
    segments_df.to_sql("core_segments", conn, if_exists="append", index=False)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# App Settings
# ---------------------------------------------------------------------------

def get_setting(key, default=None):
    """Return a JSON-decoded setting value, or default if not set."""
    conn = get_connection()
    conn.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT)")
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return json.loads(row["value"]) if row else default


def set_setting(key, value):
    """Store a JSON-encoded setting value."""
    conn = get_connection()
    conn.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute(
        """INSERT INTO app_settings (key, value) VALUES (?, ?)
           ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
        (key, json.dumps(value)),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------

UPDATABLE_CONTACT_FIELDS = {
    "first_name", "last_name", "title", "email", "phone", "mobile_phone",
    "preferred_contact_method", "is_primary", "notes", "lead_id", "customer_id",
}


def insert_contact(first_name, last_name=None, title=None, email=None, phone=None,
                    mobile_phone=None, preferred_contact_method="Phone", is_primary=0,
                    notes=None, lead_id=None, customer_id=None):
    """Insert a new contact and return its id."""
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO contacts (first_name, last_name, title, email, phone, mobile_phone,
               preferred_contact_method, is_primary, notes, lead_id, customer_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (first_name, last_name, title, email, phone, mobile_phone,
         preferred_contact_method, is_primary, notes, lead_id, customer_id),
    )
    conn.commit()
    contact_id = cursor.lastrowid
    conn.close()
    return contact_id


def get_contacts_by_lead(lead_id):
    """Return all contacts for a lead."""
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT * FROM contacts WHERE lead_id = ? ORDER BY is_primary DESC, id",
        conn,
        params=(lead_id,),
    )
    conn.close()
    return df


def get_contacts_by_customer(customer_id):
    """Return all contacts for a customer."""
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT * FROM contacts WHERE customer_id = ? ORDER BY is_primary DESC, id",
        conn,
        params=(customer_id,),
    )
    conn.close()
    return df


def get_all_contacts():
    """Return all contacts with associated lead/customer names."""
    conn = get_connection()
    df = pd.read_sql_query(
        """SELECT co.*, l.name as lead_name, cu.name as customer_name
           FROM contacts co
           LEFT JOIN leads l ON co.lead_id = l.id
           LEFT JOIN customers cu ON co.customer_id = cu.id""",
        conn,
    )
    conn.close()
    return df


def get_contact(contact_id):
    """Return a single contact as a dict."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_contact(contact_id, **fields):
    """Update allowlisted fields on a contact."""
    for field in fields:
        if field not in UPDATABLE_CONTACT_FIELDS:
            raise ValueError(f"Field not updatable: {field}")
    if not fields:
        return
    set_clause = ", ".join(f"{field} = ?" for field in fields)
    conn = get_connection()
    conn.execute(
        f"UPDATE contacts SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (*fields.values(), contact_id),
    )
    conn.commit()
    conn.close()


def delete_contact(contact_id):
    """Delete a contact and its activities."""
    conn = get_connection()
    conn.execute("DELETE FROM activities WHERE contact_id = ?", (contact_id,))
    conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------

def insert_activity(activity_type, subject=None, description=None, outcome=None,
                     contact_id=None, lead_id=None, customer_id=None, logged_by=None):
    """Insert a new activity and return its id."""
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO activities (activity_type, subject, description, outcome,
               contact_id, lead_id, customer_id, logged_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (activity_type, subject, description, outcome,
         contact_id, lead_id, customer_id, logged_by),
    )
    conn.commit()
    activity_id = cursor.lastrowid
    conn.close()
    return activity_id


def get_activities_by_lead(lead_id, limit=50):
    """Return recent activities for a lead, newest first."""
    conn = get_connection()
    df = pd.read_sql_query(
        """SELECT a.*, co.first_name as contact_first_name, co.last_name as contact_last_name
           FROM activities a
           LEFT JOIN contacts co ON a.contact_id = co.id
           WHERE a.lead_id = ?
           ORDER BY a.activity_date DESC
           LIMIT ?""",
        conn,
        params=(lead_id, limit),
    )
    conn.close()
    return df


def get_activities_by_contact(contact_id, limit=50):
    """Return recent activities for a contact, newest first."""
    conn = get_connection()
    df = pd.read_sql_query(
        """SELECT * FROM activities WHERE contact_id = ?
           ORDER BY activity_date DESC LIMIT ?""",
        conn,
        params=(contact_id, limit),
    )
    conn.close()
    return df


def get_recent_activities(limit=20):
    """Return the most recent activities with lead/contact display names."""
    conn = get_connection()
    df = pd.read_sql_query(
        """SELECT a.*, l.name as lead_name,
               co.first_name as contact_first_name, co.last_name as contact_last_name
           FROM activities a
           LEFT JOIN leads l ON a.lead_id = l.id
           LEFT JOIN contacts co ON a.contact_id = co.id
           ORDER BY a.activity_date DESC
           LIMIT ?""",
        conn,
        params=(limit,),
    )
    conn.close()
    return df


# ---------------------------------------------------------------------------
# Pipeline / Deals
# ---------------------------------------------------------------------------

UPDATABLE_DEAL_FIELDS = {
    "name", "expected_weekly_revenue", "expected_close_date",
    "assigned_salesperson", "loss_reason", "notes",
}


def get_pipeline_stages(active_only=True):
    """Return pipeline stages as a DataFrame ordered by display_order."""
    conn = get_connection()
    query = "SELECT * FROM pipeline_stages"
    if active_only:
        query += " WHERE is_active = 1"
    query += " ORDER BY display_order"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def insert_deal(name, stage_id, lead_id=None, customer_id=None,
                 expected_weekly_revenue=0, expected_close_date=None,
                 assigned_salesperson=None, notes=None):
    """Insert a new deal and return its id.

    If the deal is linked to a lead still in 'New' or 'Contacted' status,
    the lead is promoted to 'Qualified'. An activity is logged either way.
    """
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO deals (name, stage_id, lead_id, customer_id,
               expected_weekly_revenue, expected_close_date, assigned_salesperson, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (name, stage_id, lead_id, customer_id,
         expected_weekly_revenue, expected_close_date, assigned_salesperson, notes),
    )
    conn.commit()
    deal_id = cursor.lastrowid

    lead_status = None
    if lead_id is not None:
        row = conn.execute("SELECT status FROM leads WHERE id = ?", (lead_id,)).fetchone()
        lead_status = row["status"] if row else None
    conn.close()

    if lead_status in ("New", "Contacted"):
        update_lead_field(lead_id, "status", "Qualified")

    insert_activity(
        activity_type="Status Change",
        subject=f"Deal created: {name}",
        lead_id=lead_id,
    )
    return deal_id


def get_all_deals():
    """Return all deals with stage, lead/customer names, and days in stage."""
    conn = get_connection()
    df = pd.read_sql_query(
        """SELECT d.*, ps.name as stage_name, ps.probability_pct, ps.display_order,
               l.name as lead_name, cu.name as customer_name,
               julianday('now') - julianday(COALESCE(h.last_changed_at, d.created_at))
                   as days_in_stage
           FROM deals d
           JOIN pipeline_stages ps ON d.stage_id = ps.id
           LEFT JOIN leads l ON d.lead_id = l.id
           LEFT JOIN customers cu ON d.customer_id = cu.id
           LEFT JOIN (
               SELECT deal_id, MAX(changed_at) as last_changed_at
               FROM deal_stage_history
               GROUP BY deal_id
           ) h ON d.id = h.deal_id""",
        conn,
    )
    conn.close()
    return df


def get_deal(deal_id):
    """Return a single deal as a dict with its stage name, or None."""
    conn = get_connection()
    row = conn.execute(
        """SELECT d.*, ps.name as stage_name, ps.probability_pct, ps.display_order
           FROM deals d
           JOIN pipeline_stages ps ON d.stage_id = ps.id
           WHERE d.id = ?""",
        (deal_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_deal(deal_id, **fields):
    """Update allowlisted fields on a deal."""
    for field in fields:
        if field not in UPDATABLE_DEAL_FIELDS:
            raise ValueError(f"Field not updatable: {field}")
    if not fields:
        return
    set_clause = ", ".join(f"{field} = ?" for field in fields)
    conn = get_connection()
    conn.execute(
        f"UPDATE deals SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (*fields.values(), deal_id),
    )
    conn.commit()
    conn.close()


def update_deal_stage(deal_id, new_stage_id, changed_by=None):
    """Move a deal to a new stage, recording history and syncing lead status."""
    conn = get_connection()
    deal = conn.execute("SELECT * FROM deals WHERE id = ?", (deal_id,)).fetchone()
    if deal is None:
        conn.close()
        raise ValueError(f"Deal not found: {deal_id}")
    stage = conn.execute(
        "SELECT * FROM pipeline_stages WHERE id = ?", (new_stage_id,)
    ).fetchone()
    if stage is None:
        conn.close()
        raise ValueError(f"Pipeline stage not found: {new_stage_id}")

    stage_name = stage["name"]
    lead_id = deal["lead_id"]

    conn.execute(
        """INSERT INTO deal_stage_history (deal_id, from_stage_id, to_stage_id, changed_by)
           VALUES (?, ?, ?, ?)""",
        (deal_id, deal["stage_id"], new_stage_id, changed_by),
    )
    if stage_name in ("Closed Won", "Closed Lost"):
        conn.execute(
            """UPDATE deals SET stage_id = ?, closed_at = CURRENT_TIMESTAMP,
                   updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
            (new_stage_id, deal_id),
        )
    else:
        conn.execute(
            "UPDATE deals SET stage_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_stage_id, deal_id),
        )
    conn.commit()
    conn.close()

    if lead_id is not None:
        if stage_name == "Closed Won":
            update_lead_field(lead_id, "status", "Converted")
        elif stage_name == "Closed Lost":
            update_lead_field(lead_id, "status", "Rejected")

    insert_activity(
        activity_type="Status Change",
        subject=f"Deal moved to {stage_name}",
        lead_id=lead_id,
        logged_by=changed_by,
    )


def get_deal_stage_history(deal_id):
    """Return stage change history for a deal, oldest first, with stage names."""
    conn = get_connection()
    df = pd.read_sql_query(
        """SELECT h.*, fs.name as from_stage_name, ts.name as to_stage_name
           FROM deal_stage_history h
           LEFT JOIN pipeline_stages fs ON h.from_stage_id = fs.id
           JOIN pipeline_stages ts ON h.to_stage_id = ts.id
           WHERE h.deal_id = ?
           ORDER BY h.changed_at, h.id""",
        conn,
        params=(deal_id,),
    )
    conn.close()
    return df


def get_pipeline_summary():
    """Return per-stage deal counts and revenue totals for active stages."""
    conn = get_connection()
    df = pd.read_sql_query(
        """SELECT ps.name as stage_name, ps.display_order, ps.probability_pct,
               COUNT(d.id) as deal_count,
               COALESCE(SUM(d.expected_weekly_revenue), 0) as total_expected_weekly_revenue,
               COALESCE(SUM(d.expected_weekly_revenue), 0) * ps.probability_pct / 100.0
                   as weighted_revenue
           FROM pipeline_stages ps
           LEFT JOIN deals d ON d.stage_id = ps.id
           WHERE ps.is_active = 1
           GROUP BY ps.id
           ORDER BY ps.display_order""",
        conn,
    )
    conn.close()
    return df


def get_won_lost_stats(days=90):
    """Return win/loss stats for deals closed in the last `days` days."""
    conn = get_connection()
    row = conn.execute(
        """SELECT
               SUM(CASE WHEN ps.name = 'Closed Won' THEN 1 ELSE 0 END) as won_count,
               SUM(CASE WHEN ps.name = 'Closed Lost' THEN 1 ELSE 0 END) as lost_count,
               SUM(CASE WHEN ps.name = 'Closed Won' THEN d.expected_weekly_revenue ELSE 0 END)
                   as won_revenue
           FROM deals d
           JOIN pipeline_stages ps ON d.stage_id = ps.id
           WHERE d.closed_at IS NOT NULL
             AND ps.name IN ('Closed Won', 'Closed Lost')
             AND julianday('now') - julianday(d.closed_at) <= ?""",
        (days,),
    ).fetchone()
    conn.close()

    won_count = row["won_count"] or 0
    lost_count = row["lost_count"] or 0
    won_revenue = row["won_revenue"] or 0
    total_closed = won_count + lost_count
    return {
        "won_count": won_count,
        "lost_count": lost_count,
        "win_rate": (won_count / total_closed) if total_closed else 0,
        "won_revenue": won_revenue,
        "avg_deal_size": (won_revenue / won_count) if won_count else 0,
    }


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

UPDATABLE_TASK_FIELDS = {
    "title", "description", "task_type", "priority", "status",
    "assigned_to", "due_date",
}

_TASK_SELECT = """SELECT t.*, l.name as lead_name,
       co.first_name as contact_first_name, co.last_name as contact_last_name,
       d.name as deal_name
   FROM tasks t
   LEFT JOIN leads l ON t.lead_id = l.id
   LEFT JOIN contacts co ON t.contact_id = co.id
   LEFT JOIN deals d ON t.deal_id = d.id"""

_TASK_OPEN_FILTER = "t.status NOT IN ('Completed', 'Cancelled')"

_TASK_ORDER = """ORDER BY t.due_date IS NULL, t.due_date ASC,
       CASE t.priority
           WHEN 'Urgent' THEN 0 WHEN 'High' THEN 1
           WHEN 'Medium' THEN 2 ELSE 3
       END"""


def insert_task(title, description=None, task_type="Follow-up", priority="Medium",
                 assigned_to=None, due_date=None, lead_id=None, contact_id=None,
                 deal_id=None, created_by=None):
    """Insert a new task and return its id (due_date is 'YYYY-MM-DD' or None)."""
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO tasks (title, description, task_type, priority, assigned_to,
               due_date, lead_id, contact_id, deal_id, created_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (title, description, task_type, priority, assigned_to,
         due_date, lead_id, contact_id, deal_id, created_by),
    )
    conn.commit()
    task_id = cursor.lastrowid
    conn.close()
    return task_id


def get_task(task_id):
    """Return a single task as a dict, or None."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_tasks(include_completed=False):
    """Return all tasks with lead/contact/deal display names."""
    query = _TASK_SELECT
    if not include_completed:
        query += f" WHERE {_TASK_OPEN_FILTER}"
    query += f" {_TASK_ORDER}"
    conn = get_connection()
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def get_tasks_by_lead(lead_id, include_completed=False):
    """Return tasks for a lead."""
    query = f"{_TASK_SELECT} WHERE t.lead_id = ?"
    if not include_completed:
        query += f" AND {_TASK_OPEN_FILTER}"
    query += f" {_TASK_ORDER}"
    conn = get_connection()
    df = pd.read_sql_query(query, conn, params=(lead_id,))
    conn.close()
    return df


def get_tasks_by_deal(deal_id, include_completed=False):
    """Return tasks for a deal."""
    query = f"{_TASK_SELECT} WHERE t.deal_id = ?"
    if not include_completed:
        query += f" AND {_TASK_OPEN_FILTER}"
    query += f" {_TASK_ORDER}"
    conn = get_connection()
    df = pd.read_sql_query(query, conn, params=(deal_id,))
    conn.close()
    return df


def get_overdue_tasks():
    """Return open tasks whose due date has passed."""
    query = (f"{_TASK_SELECT} WHERE t.due_date < date('now') "
             f"AND {_TASK_OPEN_FILTER} {_TASK_ORDER}")
    conn = get_connection()
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def get_tasks_due_today():
    """Return open tasks due today."""
    query = (f"{_TASK_SELECT} WHERE t.due_date = date('now') "
             f"AND {_TASK_OPEN_FILTER} {_TASK_ORDER}")
    conn = get_connection()
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def get_tasks_due_this_week():
    """Return open tasks due within the next 7 days (including today)."""
    query = (f"{_TASK_SELECT} "
             f"WHERE t.due_date BETWEEN date('now') AND date('now', '+7 days') "
             f"AND {_TASK_OPEN_FILTER} {_TASK_ORDER}")
    conn = get_connection()
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def count_open_tasks_by_deal():
    """Return open task counts grouped by deal (for kanban badges)."""
    conn = get_connection()
    df = pd.read_sql_query(
        """SELECT deal_id, COUNT(*) as open_task_count
           FROM tasks
           WHERE deal_id IS NOT NULL
             AND status NOT IN ('Completed', 'Cancelled')
           GROUP BY deal_id""",
        conn,
    )
    conn.close()
    return df


def update_task_status(task_id, status):
    """Update a task's status, stamping/clearing completed_at as appropriate."""
    conn = get_connection()
    if status == "Completed":
        conn.execute(
            """UPDATE tasks SET status = ?, completed_at = CURRENT_TIMESTAMP,
                   updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
            (status, task_id),
        )
    else:
        conn.execute(
            """UPDATE tasks SET status = ?, completed_at = NULL,
                   updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
            (status, task_id),
        )
    conn.commit()
    conn.close()


def update_task(task_id, **fields):
    """Update allowlisted fields on a task."""
    for field in fields:
        if field not in UPDATABLE_TASK_FIELDS:
            raise ValueError(f"Field not updatable: {field}")
    if not fields:
        return
    set_clause = ", ".join(f"{field} = ?" for field in fields)
    conn = get_connection()
    conn.execute(
        f"UPDATE tasks SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (*fields.values(), task_id),
    )
    conn.commit()
    conn.close()


def delete_task(task_id):
    """Delete a task."""
    conn = get_connection()
    conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Communications
# ---------------------------------------------------------------------------

UPDATABLE_TEMPLATE_FIELDS = {"name", "template_type", "subject", "body"}


def get_all_templates():
    """Return all communication templates as a DataFrame."""
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT * FROM communication_templates ORDER BY template_type, name", conn
    )
    conn.close()
    return df


def get_template(template_id):
    """Return a single communication template as a dict, or None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM communication_templates WHERE id = ?", (template_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def insert_template(name, template_type, body, subject=None):
    """Insert a new communication template and return its id."""
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO communication_templates (name, template_type, subject, body)
           VALUES (?, ?, ?, ?)""",
        (name, template_type, subject, body),
    )
    conn.commit()
    template_id = cursor.lastrowid
    conn.close()
    return template_id


def update_template(template_id, **fields):
    """Update allowlisted fields on a communication template."""
    for field in fields:
        if field not in UPDATABLE_TEMPLATE_FIELDS:
            raise ValueError(f"Field not updatable: {field}")
    if not fields:
        return
    set_clause = ", ".join(f"{field} = ?" for field in fields)
    conn = get_connection()
    conn.execute(
        f"UPDATE communication_templates SET {set_clause}, "
        f"updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (*fields.values(), template_id),
    )
    conn.commit()
    conn.close()


def delete_template(template_id):
    """Delete a template, clearing references from any emails that used it."""
    conn = get_connection()
    conn.execute(
        "UPDATE emails SET template_id = NULL WHERE template_id = ?", (template_id,)
    )
    conn.execute("DELETE FROM communication_templates WHERE id = ?", (template_id,))
    conn.commit()
    conn.close()


def insert_email(subject, body, to_address=None, lead_id=None, contact_id=None,
                  template_id=None, status="Draft"):
    """Insert a new email record and return its id."""
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO emails (subject, body, to_address, lead_id, contact_id,
               template_id, status)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (subject, body, to_address, lead_id, contact_id, template_id, status),
    )
    conn.commit()
    email_id = cursor.lastrowid
    conn.close()
    return email_id


def get_emails_by_lead(lead_id):
    """Return all emails for a lead, newest first."""
    conn = get_connection()
    df = pd.read_sql_query(
        """SELECT e.*, co.first_name as contact_first_name,
               co.last_name as contact_last_name,
               ct.name as template_name
           FROM emails e
           LEFT JOIN contacts co ON e.contact_id = co.id
           LEFT JOIN communication_templates ct ON e.template_id = ct.id
           WHERE e.lead_id = ?
           ORDER BY e.created_at DESC, e.id DESC""",
        conn,
        params=(lead_id,),
    )
    conn.close()
    return df


def mark_email_sent(email_id):
    """Mark an email as sent, stamping sent_at."""
    conn = get_connection()
    conn.execute(
        """UPDATE emails SET status = 'Sent', sent_at = CURRENT_TIMESTAMP
           WHERE id = ?""",
        (email_id,),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def get_table_counts():
    """Return row counts for all main tables."""
    conn = get_connection()
    counts = {}
    for table in ["distribution_centers", "routes", "customers", "leads", "lead_scores",
                  "route_stops", "contacts", "activities", "pipeline_stages", "deals",
                  "deal_stage_history", "tasks", "communication_templates", "emails",
                  "core_segments", "app_settings"]:
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        counts[table] = row[0]
    conn.close()
    return counts


def clear_all_data():
    """Clear all data from all tables."""
    conn = get_connection()
    for table in ["emails", "communication_templates", "tasks", "deal_stage_history",
                  "deals", "pipeline_stages", "activities",
                  "contacts", "lead_scores", "route_stops", "leads",
                  "customers", "routes", "distribution_centers", "core_segments",
                  "app_settings"]:
        conn.execute(f"DELETE FROM {table}")
    conn.commit()
    conn.close()
