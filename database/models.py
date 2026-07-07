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
# Utility
# ---------------------------------------------------------------------------

def get_table_counts():
    """Return row counts for all main tables."""
    conn = get_connection()
    counts = {}
    for table in ["distribution_centers", "routes", "customers", "leads", "lead_scores", "route_stops"]:
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        counts[table] = row[0]
    conn.close()
    return counts


def clear_all_data():
    """Clear all data from all tables."""
    conn = get_connection()
    for table in ["lead_scores", "route_stops", "leads", "customers", "routes", "distribution_centers", "core_segments"]:
        conn.execute(f"DELETE FROM {table}")
    conn.commit()
    conn.close()
