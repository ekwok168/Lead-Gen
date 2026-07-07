"""Upload Data page - Excel/CSV upload and copy-paste input."""

import streamlit as st
import pandas as pd
import numpy as np
import io
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import config
from database.connection import init_db, seed_core_segments
from database.models import (
    get_all_customers, get_all_leads, upsert_dc, upsert_route,
    insert_customer, bulk_insert_leads, rebuild_route_stops,
    get_table_counts, clear_all_data,
)
from utils.auth import require_auth
from utils.cached import invalidate
from utils.dedup import check_duplicate, filter_duplicates


def _find_col(cols, keyword):
    """Find the best matching column index for a keyword."""
    keyword_lower = keyword.lower()
    for i, col in enumerate(cols):
        if col == "-- Not Available --":
            continue
        if keyword_lower in col.lower():
            return i
    return 0


def _get_val(row, col_name, default=""):
    """Get a value from a row using a column name, with default."""
    if col_name == "-- Not Available --" or not col_name:
        return default
    val = row.get(col_name, default)
    if pd.isna(val):
        return default
    return val


def _safe_float(val):
    """Safely convert to float."""
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _safe_int(val):
    """Safely convert to int."""
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return 0


def parse_upload(uploaded_file):
    """Parse an uploaded file (CSV or Excel) into a DataFrame."""
    if uploaded_file is None:
        return None
    try:
        if uploaded_file.name.endswith(".csv"):
            return pd.read_csv(uploaded_file)
        else:
            return pd.read_excel(uploaded_file)
    except Exception as e:
        st.error(f"Could not read file: {e}")
        return None


def geocode_missing_coords(df):
    """Attempt to geocode rows missing latitude/longitude."""
    needs_geocoding = df[
        (df["latitude"].isna() | (df["latitude"] == 0))
        & df["address"].notna()
        & (df["address"] != "")
    ]

    if needs_geocoding.empty:
        return df

    st.info(f"🌍 Geocoding {len(needs_geocoding)} addresses (this may take a moment)...")

    try:
        from geopy.geocoders import Nominatim
        from geopy.exc import GeocoderTimedOut
        import time

        geolocator = Nominatim(user_agent="lead_gen_tool")
        geocoded = 0

        progress = st.progress(0)
        for i, (idx, row) in enumerate(needs_geocoding.iterrows()):
            try:
                full_address = f"{row['address']}, {row.get('city', '')}, {row.get('state', '')} {row.get('zip_code', '')}"
                location = geolocator.geocode(full_address, timeout=config.GEOCODING_TIMEOUT)
                if location:
                    df.at[idx, "latitude"] = location.latitude
                    df.at[idx, "longitude"] = location.longitude
                    geocoded += 1
                time.sleep(config.GEOCODING_RATE_LIMIT_DELAY)
            except (GeocoderTimedOut, Exception):
                pass
            progress.progress(min((i + 1) / len(needs_geocoding), 1.0))

        st.success(f"Geocoded {geocoded} of {len(needs_geocoding)} addresses")
    except ImportError:
        st.warning("Geocoding not available. Please provide latitude and longitude columns.")

    return df


init_db()
seed_core_segments()

st.set_page_config(page_title="Upload Data", page_icon="📥", layout="wide")
require_auth()
st.title("📥 Upload Data")
st.markdown("Import your data using Excel/CSV files or by pasting from a spreadsheet")

# Template download section
st.markdown("---")
st.markdown("### 📄 Download Templates")
st.markdown("Download these Excel templates, fill them out, and upload them below.")

col1, col2, col3 = st.columns(3)

with col1:
    # Customer template
    cust_template = pd.DataFrame({
        "name": ["Mario's Pizza", "City Hotel Downtown"],
        "address": ["123 Main St", "456 Broadway"],
        "city": ["Denver", "Denver"],
        "state": ["CO", "CO"],
        "zip_code": ["80202", "80203"],
        "latitude": [39.7392, 39.7450],
        "longitude": [-104.9903, -104.9870],
        "business_type": ["Restaurant", "Hotel"],
        "segment": ["Full-Service Restaurant", "Hospitality"],
        "weekly_revenue": [850, 1200],
        "route_code": ["R-101", "R-101"],
        "stop_sequence": [1, 2],
    })
    csv = cust_template.to_csv(index=False)
    st.download_button(
        "⬇️ Customer Template",
        csv, "customer_template.csv", "text/csv",
        use_container_width=True,
    )

with col2:
    # Route template
    route_template = pd.DataFrame({
        "route_code": ["R-101", "R-102"],
        "route_name": ["Downtown Route", "North Route"],
        "dc_name": ["Main DC", "Main DC"],
        "dc_code": ["DC-001", "DC-001"],
        "dc_address": ["100 Warehouse Dr", "100 Warehouse Dr"],
        "dc_city": ["Denver", "Denver"],
        "dc_state": ["CO", "CO"],
        "dc_zip": ["80216", "80216"],
        "dc_latitude": [39.7800, 39.7800],
        "dc_longitude": [-104.9700, -104.9700],
        "day_of_week": ["MON,WED,FRI", "TUE,THU"],
        "driver_name": ["John Smith", "Jane Doe"],
    })
    csv = route_template.to_csv(index=False)
    st.download_button(
        "⬇️ Route & DC Template",
        csv, "route_template.csv", "text/csv",
        use_container_width=True,
    )

with col3:
    # Lead template
    lead_template = pd.DataFrame({
        "name": ["New Cafe", "Express Mart"],
        "address": ["789 Oak Ave", "321 Pine St"],
        "city": ["Denver", "Denver"],
        "state": ["CO", "CO"],
        "zip_code": ["80204", "80205"],
        "latitude": [39.7350, 39.7500],
        "longitude": [-104.9950, -104.9800],
        "business_type": ["Restaurant", "Convenience Store"],
        "segment": ["Quick-Service Restaurant", "C-Store"],
        "estimated_weekly_revenue": [500, 400],
        "phone": ["303-555-1234", "303-555-5678"],
        "website": ["www.newcafe.com", ""],
    })
    csv = lead_template.to_csv(index=False)
    st.download_button(
        "⬇️ Prospect/Lead Template",
        csv, "lead_template.csv", "text/csv",
        use_container_width=True,
    )

st.markdown("---")

# Tabs for different upload types
tab1, tab2, tab3, tab4 = st.tabs([
    "🚛 Step 1: Routes & DCs",
    "👥 Step 2: Customers",
    "🎯 Step 3: Prospects/Leads",
    "📋 Paste from Spreadsheet",
])


# ---- Tab 1: Routes & DCs ----
with tab1:
    st.markdown("### Upload Routes and Distribution Centers")
    st.markdown("Upload a file with your route definitions and distribution center information.")

    route_file = st.file_uploader(
        "Choose a CSV or Excel file",
        type=["csv", "xlsx", "xls"],
        key="route_upload",
    )

    if route_file:
        df = parse_upload(route_file)
        if df is not None:
            st.markdown("**Preview (first 10 rows):**")
            st.dataframe(df.head(10), use_container_width=True)

            st.markdown("**Column Mapping**")
            st.markdown("Select which columns in your file match our fields:")

            cols = ["-- Not Available --"] + list(df.columns)

            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Route Fields**")
                route_code_col = st.selectbox("Route Code", cols, index=_find_col(cols, "route_code"))
                route_name_col = st.selectbox("Route Name", cols, index=_find_col(cols, "route_name"))
                day_col = st.selectbox("Day of Week", cols, index=_find_col(cols, "day"))
                driver_col = st.selectbox("Driver Name", cols, index=_find_col(cols, "driver"))

            with col2:
                st.markdown("**DC Fields**")
                dc_name_col = st.selectbox("DC Name", cols, index=_find_col(cols, "dc_name"))
                dc_code_col = st.selectbox("DC Code", cols, index=_find_col(cols, "dc_code"))
                dc_lat_col = st.selectbox("DC Latitude", cols, index=_find_col(cols, "dc_lat"))
                dc_lon_col = st.selectbox("DC Longitude", cols, index=_find_col(cols, "dc_lon"))
                dc_addr_col = st.selectbox("DC Address", cols, index=_find_col(cols, "dc_addr"))
                dc_city_col = st.selectbox("DC City", cols, index=_find_col(cols, "dc_city"))
                dc_state_col = st.selectbox("DC State", cols, index=_find_col(cols, "dc_state"))
                dc_zip_col = st.selectbox("DC Zip", cols, index=_find_col(cols, "dc_zip"))

            if st.button("✅ Import Routes & DCs", use_container_width=True, key="import_routes"):
                imported = 0
                errors = []
                dc_cache = {}

                for idx, row in df.iterrows():
                    try:
                        # Upsert DC
                        dc_code = _get_val(row, dc_code_col, f"DC-AUTO-{idx}")
                        dc_name = _get_val(row, dc_name_col, dc_code)

                        if dc_code not in dc_cache:
                            dc_lat = float(_get_val(row, dc_lat_col, 0))
                            dc_lon = float(_get_val(row, dc_lon_col, 0))
                            if dc_lat == 0 or dc_lon == 0:
                                errors.append(f"Row {idx + 1}: DC '{dc_name}' missing coordinates")
                                continue
                            dc_id = upsert_dc(
                                dc_name, dc_code,
                                _get_val(row, dc_addr_col, ""),
                                _get_val(row, dc_city_col, ""),
                                _get_val(row, dc_state_col, ""),
                                _get_val(row, dc_zip_col, ""),
                                dc_lat, dc_lon,
                            )
                            dc_cache[dc_code] = dc_id
                        else:
                            dc_id = dc_cache[dc_code]

                        # Upsert Route
                        r_code = _get_val(row, route_code_col, f"R-AUTO-{idx}")
                        upsert_route(
                            dc_id, r_code,
                            _get_val(row, route_name_col, r_code),
                            _get_val(row, day_col, ""),
                            _get_val(row, driver_col, ""),
                        )
                        imported += 1
                    except Exception as e:
                        errors.append(f"Row {idx + 1}: {str(e)}")

                st.success(f"Imported {imported} routes across {len(dc_cache)} distribution centers")
                if errors:
                    with st.expander(f"⚠️ {len(errors)} issues"):
                        for err in errors:
                            st.write(err)


# ---- Tab 2: Customers ----
with tab2:
    st.markdown("### Upload Existing Customers")
    st.markdown("Upload your complete customer list. Include route assignments to link customers to routes.")

    cust_file = st.file_uploader(
        "Choose a CSV or Excel file",
        type=["csv", "xlsx", "xls"],
        key="cust_upload",
    )

    if cust_file:
        df = parse_upload(cust_file)
        if df is not None:
            st.markdown("**Preview (first 10 rows):**")
            st.dataframe(df.head(10), use_container_width=True)

            st.markdown("**Column Mapping**")
            cols = ["-- Not Available --"] + list(df.columns)

            col1, col2 = st.columns(2)
            with col1:
                name_col = st.selectbox("Business Name", cols, index=_find_col(cols, "name"), key="c_name")
                addr_col = st.selectbox("Address", cols, index=_find_col(cols, "address"), key="c_addr")
                city_col = st.selectbox("City", cols, index=_find_col(cols, "city"), key="c_city")
                state_col = st.selectbox("State", cols, index=_find_col(cols, "state"), key="c_state")
                zip_col = st.selectbox("Zip Code", cols, index=_find_col(cols, "zip"), key="c_zip")
                lat_col = st.selectbox("Latitude", cols, index=_find_col(cols, "lat"), key="c_lat")
                lon_col = st.selectbox("Longitude", cols, index=_find_col(cols, "lon"), key="c_lon")

            with col2:
                btype_col = st.selectbox("Business Type", cols, index=_find_col(cols, "business_type"), key="c_btype")
                seg_col = st.selectbox("Segment", cols, index=_find_col(cols, "segment"), key="c_seg")
                rev_col = st.selectbox("Weekly Revenue", cols, index=_find_col(cols, "revenue"), key="c_rev")
                route_col = st.selectbox("Route Code", cols, index=_find_col(cols, "route"), key="c_route")
                seq_col = st.selectbox("Stop Sequence", cols, index=_find_col(cols, "sequence"), key="c_seq")

            if st.button("✅ Import Customers", use_container_width=True, key="import_customers"):
                imported = 0
                errors = []
                from database.connection import get_connection

                conn = get_connection()
                routes_map = {}
                route_rows = conn.execute("SELECT id, route_code FROM routes").fetchall()
                for r in route_rows:
                    routes_map[r["route_code"]] = r["id"]
                conn.close()

                records = []
                for idx, row in df.iterrows():
                    name = _get_val(row, name_col, "")
                    if not name:
                        errors.append(f"Row {idx + 1}: Missing business name")
                        continue

                    records.append({
                        "row": idx + 1,
                        "name": name,
                        "address": _get_val(row, addr_col, ""),
                        "city": _get_val(row, city_col, ""),
                        "state": _get_val(row, state_col, ""),
                        "zip_code": str(_get_val(row, zip_col, "")),
                        "latitude": _safe_float(_get_val(row, lat_col, 0)),
                        "longitude": _safe_float(_get_val(row, lon_col, 0)),
                        "business_type": _get_val(row, btype_col, ""),
                        "segment": _get_val(row, seg_col, ""),
                        "weekly_revenue": _safe_float(_get_val(row, rev_col, 0)),
                        "route_code": _get_val(row, route_col, ""),
                        "stop_sequence": _safe_int(_get_val(row, seq_col, idx + 1)),
                    })

                cust_df = pd.DataFrame(records)
                if not cust_df.empty:
                    cust_df = geocode_missing_coords(cust_df)

                for _, rec in cust_df.iterrows():
                    try:
                        route_id = routes_map.get(rec["route_code"])
                        insert_customer(
                            name=rec["name"],
                            address=rec["address"],
                            city=rec["city"],
                            state=rec["state"],
                            zip_code=rec["zip_code"],
                            latitude=rec["latitude"],
                            longitude=rec["longitude"],
                            business_type=rec["business_type"],
                            segment=rec["segment"],
                            weekly_revenue=rec["weekly_revenue"],
                            route_id=route_id,
                            stop_sequence=rec["stop_sequence"],
                        )
                        imported += 1
                    except Exception as e:
                        errors.append(f"Row {rec['row']}: {str(e)}")

                # Rebuild route stops
                for route_id in set(routes_map.values()):
                    rebuild_route_stops(route_id)

                invalidate()
                st.success(f"Imported {imported} customers")
                if errors:
                    with st.expander(f"⚠️ {len(errors)} issues"):
                        for err in errors:
                            st.write(err)


# ---- Tab 3: Prospects/Leads ----
with tab3:
    st.markdown("### Upload Prospects / Leads")
    st.markdown("""
    Upload potential customers from external sources. The system will automatically
    check for duplicates against your existing customer list.
    """)

    lead_file = st.file_uploader(
        "Choose a CSV or Excel file",
        type=["csv", "xlsx", "xls"],
        key="lead_upload",
    )

    if lead_file:
        df = parse_upload(lead_file)
        if df is not None:
            st.markdown("**Preview (first 10 rows):**")
            st.dataframe(df.head(10), use_container_width=True)

            st.markdown("**Column Mapping**")
            cols = ["-- Not Available --"] + list(df.columns)

            col1, col2 = st.columns(2)
            with col1:
                name_col = st.selectbox("Business Name", cols, index=_find_col(cols, "name"), key="l_name")
                addr_col = st.selectbox("Address", cols, index=_find_col(cols, "address"), key="l_addr")
                city_col = st.selectbox("City", cols, index=_find_col(cols, "city"), key="l_city")
                state_col = st.selectbox("State", cols, index=_find_col(cols, "state"), key="l_state")
                zip_col = st.selectbox("Zip Code", cols, index=_find_col(cols, "zip"), key="l_zip")
                lat_col = st.selectbox("Latitude", cols, index=_find_col(cols, "lat"), key="l_lat")
                lon_col = st.selectbox("Longitude", cols, index=_find_col(cols, "lon"), key="l_lon")

            with col2:
                btype_col = st.selectbox("Business Type", cols, index=_find_col(cols, "business_type"), key="l_btype")
                seg_col = st.selectbox("Segment", cols, index=_find_col(cols, "segment"), key="l_seg")
                rev_col = st.selectbox("Est. Weekly Revenue", cols, index=_find_col(cols, "revenue"), key="l_rev")
                phone_col = st.selectbox("Phone", cols, index=_find_col(cols, "phone"), key="l_phone")
                web_col = st.selectbox("Website", cols, index=_find_col(cols, "website"), key="l_web")

            if st.button("✅ Import Leads (with duplicate check)", use_container_width=True, key="import_leads"):
                records = []
                indices = []
                for idx, row in df.iterrows():
                    name = _get_val(row, name_col, "")
                    if not name:
                        continue

                    records.append({
                        "name": name,
                        "address": _get_val(row, addr_col, ""),
                        "city": _get_val(row, city_col, ""),
                        "state": _get_val(row, state_col, ""),
                        "zip_code": str(_get_val(row, zip_col, "")),
                        "latitude": _safe_float(_get_val(row, lat_col, 0)),
                        "longitude": _safe_float(_get_val(row, lon_col, 0)),
                        "business_type": _get_val(row, btype_col, ""),
                        "segment": _get_val(row, seg_col, ""),
                        "estimated_weekly_revenue": _safe_float(_get_val(row, rev_col, 0)),
                        "phone": _get_val(row, phone_col, ""),
                        "website": _get_val(row, web_col, ""),
                        "source": "File Upload",
                        "status": "New",
                    })
                    indices.append(idx)

                leads_df = pd.DataFrame(records, index=indices)
                if not leads_df.empty:
                    leads_df = geocode_missing_coords(leads_df)

                with st.spinner("Checking for duplicates against existing customers..."):
                    existing_customers = get_all_customers()
                    existing_leads = get_all_leads()

                    unique_df, dupes_df = filter_duplicates(
                        leads_df, existing_customers, existing_leads
                    )

                    if not unique_df.empty:
                        bulk_insert_leads(unique_df)
                        invalidate()

                    st.success(
                        f"**Uploaded {len(df)} prospects.** "
                        f"{len(dupes_df)} are already your customers. "
                        f"**{len(unique_df)} new leads added.**"
                    )

                    if not dupes_df.empty:
                        with st.expander(f"🔄 {len(dupes_df)} duplicates found (excluded)"):
                            st.dataframe(dupes_df, use_container_width=True)


# ---- Tab 4: Paste from Spreadsheet ----
with tab4:
    st.markdown("### Paste Data from Spreadsheet")
    st.markdown("""
    Copy rows from Excel or Google Sheets (including the header row) and paste them below.
    The data should be tab-separated (this happens automatically when you copy from a spreadsheet).
    """)

    data_type = st.selectbox(
        "What type of data are you pasting?",
        ["Prospects/Leads", "Customers", "Routes & DCs"],
    )

    pasted = st.text_area(
        "Paste your data here (include header row):",
        height=300,
        placeholder="name\taddress\tcity\tstate\tzip_code\tlatitude\tlongitude\tbusiness_type\n"
                    "Mario's Pizza\t123 Main St\tDenver\tCO\t80202\t39.7392\t-104.9903\tRestaurant",
    )

    if pasted and st.button("✅ Process Pasted Data", use_container_width=True, key="process_paste"):
        try:
            df = pd.read_csv(io.StringIO(pasted), sep="\t")
            st.markdown(f"**Parsed {len(df)} rows with columns:** {', '.join(df.columns)}")
            st.dataframe(df.head(10), use_container_width=True)

            if data_type == "Prospects/Leads":
                # Ensure required columns and bulk insert
                for col in ["latitude", "longitude"]:
                    if col not in df.columns:
                        df[col] = 0.0
                    else:
                        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
                if "name" not in df.columns:
                    st.error("Data must include a 'name' column")
                else:
                    df["source"] = "Paste Import"
                    df["status"] = "New"

                    with st.spinner("Checking for duplicates against existing customers..."):
                        existing_customers = get_all_customers()
                        existing_leads = get_all_leads()
                        unique_df, dupes_df = filter_duplicates(
                            df, existing_customers, existing_leads
                        )

                    if not unique_df.empty:
                        bulk_insert_leads(unique_df)
                        invalidate()

                    st.success(
                        f"Imported {len(unique_df)} leads! "
                        f"{len(dupes_df)} duplicates skipped."
                    )
                    if not dupes_df.empty:
                        with st.expander(f"🔄 {len(dupes_df)} duplicates found (excluded)"):
                            st.dataframe(dupes_df, use_container_width=True)

            elif data_type == "Customers":
                st.info("For customers, please use the Excel upload tab with column mapping for best results.")
                st.dataframe(df, use_container_width=True)

            elif data_type == "Routes & DCs":
                st.info("For routes & DCs, please use the Excel upload tab with column mapping for best results.")
                st.dataframe(df, use_container_width=True)

        except Exception as e:
            st.error(f"Could not parse pasted data: {e}")

# ---- Database Backup & Restore ----
st.markdown("---")
st.markdown("### 💾 Database Backup & Restore")
st.markdown("""
**Important:** This app stores data in a local database file. If the app restarts
(e.g., after updates or inactivity), your data may be reset. **Download a backup regularly**
so you can restore your data if needed.
""")

col1, col2 = st.columns(2)

with col1:
    st.markdown("#### Download Backup")
    db_path = config.DB_PATH
    if os.path.exists(db_path):
        with open(db_path, "rb") as f:
            db_bytes = f.read()
        st.download_button(
            "⬇️ Download Database Backup",
            db_bytes,
            "lead_gen_backup.db",
            "application/octet-stream",
            use_container_width=True,
        )
        file_size = os.path.getsize(db_path)
        st.caption(f"Database size: {file_size / 1024:.0f} KB")
    else:
        st.info("No database file found yet. Import data first.")

with col2:
    st.markdown("#### Restore from Backup")
    restore_file = st.file_uploader(
        "Upload a .db backup file",
        type=["db"],
        key="restore_db",
    )
    if restore_file:
        st.warning("This will replace ALL current data with the backup. Are you sure?")
        if st.button("✅ Restore Database", use_container_width=True, key="do_restore"):
            import sqlite3
            import tempfile

            data = restore_file.getvalue()
            if not data.startswith(b"SQLite format 3\x00"):
                st.error("This file is not a valid SQLite database. Restore cancelled.")
            else:
                tmp_path = None
                try:
                    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
                        tmp.write(data)
                        tmp_path = tmp.name
                    check_conn = sqlite3.connect(tmp_path)
                    try:
                        result = check_conn.execute("PRAGMA integrity_check").fetchone()
                    finally:
                        check_conn.close()

                    if result and result[0] == "ok":
                        with open(db_path, "wb") as f:
                            f.write(data)
                        invalidate()
                        st.success("Database restored from backup! The page will refresh.")
                        st.rerun()
                    else:
                        detail = result[0] if result else "unknown error"
                        st.error(f"Backup file failed integrity check: {detail}. Restore cancelled.")
                except sqlite3.Error as e:
                    st.error(f"Could not validate backup file: {e}. Restore cancelled.")
                finally:
                    if tmp_path and os.path.exists(tmp_path):
                        os.unlink(tmp_path)

# ---- Data Management ----
st.markdown("---")
st.markdown("### 🗑️ Data Management")

with st.expander("View current data counts and clear data"):
    counts = get_table_counts()
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Distribution Centers", counts.get("distribution_centers", 0))
        st.metric("Routes", counts.get("routes", 0))
    with col2:
        st.metric("Customers", counts.get("customers", 0))
        st.metric("Route Stops", counts.get("route_stops", 0))
    with col3:
        st.metric("Leads", counts.get("leads", 0))
        st.metric("Lead Scores", counts.get("lead_scores", 0))

    st.markdown("---")
    st.warning("⚠️ Clearing data cannot be undone!")
    if st.button("🗑️ Clear ALL Data", type="secondary"):
        st.session_state["confirm_clear"] = True

    if st.session_state.get("confirm_clear"):
        st.error("Are you absolutely sure? This will delete ALL data.")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Yes, clear everything", type="primary"):
                clear_all_data()
                seed_core_segments()
                invalidate()
                st.session_state["confirm_clear"] = False
                st.success("All data cleared!")
                st.rerun()
        with col2:
            if st.button("Cancel"):
                st.session_state["confirm_clear"] = False
                st.rerun()
