"""Restaurant Finder page - Discover nearby restaurants via OpenStreetMap."""

import streamlit as st
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database.connection import init_db
from database.models import (
    get_all_dcs, get_routes_by_dc, get_all_routes,
    get_all_customers, get_all_leads, get_all_stops,
    bulk_insert_leads,
)
from discovery.overpass import discover_restaurants
from utils.auth import require_auth
from utils.dedup import filter_duplicates
from utils.cached import invalidate
import config

init_db()

st.set_page_config(page_title="Restaurant Finder", page_icon="🍽️", layout="wide")
require_auth()
st.title("🍽️ Restaurant Finder")
st.markdown("Discover restaurants, cafes, and bars near your delivery routes using free OpenStreetMap data")

dcs = get_all_dcs()
if dcs.empty:
    st.info("No data found. Go to **Upload Data** to import your customers and routes first.")
    st.stop()

# ---------------------------------------------------------------------------
# Search scope
# ---------------------------------------------------------------------------

st.markdown("### 1️⃣ Choose where to search")

col1, col2 = st.columns(2)

with col1:
    dc_options = {"all": "All Distribution Centers"}
    dc_options.update({int(row["id"]): f"{row['code']} - {row['name']}" for _, row in dcs.iterrows()})
    selected_dc = st.selectbox("Distribution Center", options=list(dc_options.keys()),
                               format_func=lambda x: dc_options[x])

with col2:
    if selected_dc == "all":
        routes = get_all_routes()
    else:
        routes = get_routes_by_dc(selected_dc)

    route_options = {int(row["id"]): f"{row['route_code']} - {row.get('route_name', '')}" for _, row in routes.iterrows()}
    selected_routes = st.multiselect(
        "Routes (leave empty for all routes)",
        options=list(route_options.keys()),
        format_func=lambda x: route_options[x],
    )

route_ids = selected_routes if selected_routes else list(route_options.keys())

col1, col2, col3 = st.columns(3)

with col1:
    use_stops = st.checkbox("Search around route stops", value=True)
    use_customers = st.checkbox("Search around customer locations", value=True)

with col2:
    radius = st.slider(
        "Search radius (miles)",
        min_value=0.25, max_value=5.0,
        value=float(config.OVERPASS_DEFAULT_RADIUS_MI), step=0.25,
    )

with col3:
    amenity_keys = list(config.DISCOVERY_AMENITY_TYPES.keys())
    selected_amenities = st.multiselect(
        "Business types to find",
        options=amenity_keys,
        default=amenity_keys,
        format_func=lambda k: config.DISCOVERY_AMENITY_TYPES[k],
    )


def _valid_points(df):
    if df is None or df.empty or "latitude" not in df.columns or "longitude" not in df.columns:
        return []
    lat = pd.to_numeric(df["latitude"], errors="coerce")
    lon = pd.to_numeric(df["longitude"], errors="coerce")
    mask = lat.notna() & lon.notna() & ~((lat.abs() <= 0.01) & (lon.abs() <= 0.01))
    return list(zip(lat[mask].tolist(), lon[mask].tolist()))


search_coords = []

if route_ids:
    if use_stops:
        stops = get_all_stops()
        if not stops.empty:
            search_coords.extend(_valid_points(stops[stops["route_id"].isin(route_ids)]))
    if use_customers:
        customers = get_all_customers()
        if not customers.empty:
            search_coords.extend(_valid_points(customers[customers["route_id"].isin(route_ids)]))

# Remove near-duplicate points so we don't query the same spot twice
search_coords = list(dict.fromkeys((round(lat, 4), round(lon, 4)) for lat, lon in search_coords))

if not search_coords:
    st.info("No route stops or customer locations found for this selection. "
            "Go to **Upload Data** to import your customers and routes first.")
else:
    st.markdown(f"**📍 {len(search_coords)} search points selected**")
    st.caption("Searches use the free OpenStreetMap service. Larger areas and more "
               "search points take longer — expect up to a minute or two for big searches.")

# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

st.markdown("---")
st.markdown("### 2️⃣ Run the search")

can_search = bool(search_coords) and bool(selected_amenities)
if search_coords and not selected_amenities:
    st.warning("Pick at least one business type to search for.")

if st.button("🔍 Search for Restaurants", type="primary", disabled=not can_search):
    progress_bar = st.progress(0)
    status_text = st.empty()

    def update_progress(pct, msg):
        progress_bar.progress(min(max(int(pct), 0), 100) / 100)
        status_text.text(msg)

    try:
        results = discover_restaurants(
            search_coords, radius, selected_amenities,
            progress_callback=update_progress,
        )
        progress_bar.progress(100)
        status_text.empty()

        if results is None or results.empty:
            st.session_state.pop("discovered_restaurants", None)
            st.warning("No restaurants found in this area. Try a larger radius or more business types.")
        else:
            st.session_state["discovered_restaurants"] = results
            st.session_state["rf_editor_ver"] = st.session_state.get("rf_editor_ver", 0) + 1
    except RuntimeError as e:
        st.error(f"Search failed: {e}. The OpenStreetMap service may be busy — please try again in a minute.")

# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

imported_count = st.session_state.pop("rf_import_flash", None)
if imported_count:
    st.success(f"Imported {imported_count} new leads! 💡 Run **Score All Leads** "
               "from the home page sidebar to score and grade them.")

results = st.session_state.get("discovered_restaurants")

if results is not None and not results.empty:
    st.markdown("---")
    st.markdown("### 3️⃣ Review results")

    new_df, dupes_info = filter_duplicates(results, get_all_customers(), get_all_leads())
    dup_rows = results.loc[results.index.difference(new_df.index)]

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Found", len(results))
    with col2:
        st.metric("Already customers or leads", len(dup_rows))
    with col3:
        st.metric("New prospects", len(new_df))

    tab_map, tab_table = st.tabs(["🗺️ Map", "📋 Table"])

    with tab_map:
        try:
            import folium
            from streamlit_folium import st_folium

            center = [results["latitude"].mean(), results["longitude"].mean()]
            m = folium.Map(location=center, zoom_start=config.MAP_DEFAULT_ZOOM + 1,
                           tiles=config.MAP_TILE_STYLE)

            for _, row in dup_rows.iterrows():
                folium.CircleMarker(
                    [row["latitude"], row["longitude"]],
                    radius=5, color="gray", fill=True, fill_color="gray", fill_opacity=0.6,
                    tooltip=f"{row.get('name', 'Unknown')} | {row.get('amenity', '')} | "
                            f"{row.get('distance_mi', 0):.2f} mi (already known)",
                ).add_to(m)

            for _, row in new_df.iterrows():
                folium.CircleMarker(
                    [row["latitude"], row["longitude"]],
                    radius=6, color="green", fill=True, fill_color="green", fill_opacity=0.8,
                    tooltip=f"{row.get('name', 'Unknown')} | {row.get('amenity', '')} | "
                            f"{row.get('distance_mi', 0):.2f} mi",
                ).add_to(m)

            st.markdown("**Green** = new prospects | **Gray** = already in your customers or leads")
            st_folium(m, width=None, height=550, use_container_width=True)
        except ImportError:
            st.warning("Install streamlit-folium for interactive maps: `pip install streamlit-folium`")

    with tab_table:
        if new_df.empty:
            st.info("Everything found here is already in your customers or leads.")
        else:
            table_cols = {
                "name": "Business Name",
                "amenity": "Type",
                "cuisine": "Cuisine",
                "address": "Address",
                "phone": "Phone",
                "website": "Website",
                "distance_mi": "Distance (mi)",
            }
            available = {k: v for k, v in table_cols.items() if k in new_df.columns}
            display = new_df.sort_values("distance_mi")[list(available.keys())].copy()
            display.columns = list(available.values())
            st.dataframe(display, use_container_width=True, hide_index=True)

        if not dupes_info.empty:
            with st.expander(f"Already known ({len(dupes_info)}) - skipped as duplicates"):
                dupe_display = dupes_info[["name", "reason"]].copy()
                dupe_display.columns = ["Business Name", "Why it was skipped"]
                st.dataframe(dupe_display, use_container_width=True, hide_index=True)

    # -----------------------------------------------------------------------
    # Import
    # -----------------------------------------------------------------------

    if not new_df.empty:
        st.markdown("---")
        st.markdown("### 4️⃣ Import new prospects as leads")
        st.markdown("Uncheck any businesses you don't want, then click Import.")

        editor_df = new_df.sort_values("distance_mi").copy()
        editor_df.insert(0, "import", True)

        edited = st.data_editor(
            editor_df,
            column_order=["import", "name", "amenity", "cuisine", "address",
                          "phone", "website", "distance_mi"],
            column_config={
                "import": st.column_config.CheckboxColumn("Import?", default=True),
                "name": st.column_config.TextColumn("Business Name"),
                "amenity": st.column_config.TextColumn("Type"),
                "cuisine": st.column_config.TextColumn("Cuisine"),
                "address": st.column_config.TextColumn("Address"),
                "phone": st.column_config.TextColumn("Phone"),
                "website": st.column_config.TextColumn("Website"),
                "distance_mi": st.column_config.NumberColumn("Distance (mi)", format="%.2f"),
            },
            disabled=[c for c in editor_df.columns if c != "import"],
            hide_index=True,
            use_container_width=True,
            key=f"rf_import_editor_{st.session_state.get('rf_editor_ver', 0)}",
        )

        to_import = edited[edited["import"] == True]  # noqa: E712
        st.markdown(f"**{len(to_import)} of {len(edited)} prospects selected for import**")

        if st.button("➕ Import Selected as Leads", type="primary", disabled=to_import.empty):
            leads_df = pd.DataFrame({
                "name": to_import["name"].values,
                "latitude": to_import["latitude"].values,
                "longitude": to_import["longitude"].values,
                "address": to_import["address"].values,
                "business_type": to_import["business_type"].values,
                "segment": to_import["segment"].values,
                "estimated_weekly_revenue": 0,
                "phone": to_import["phone"].values,
                "website": to_import["website"].values,
                "source": "Restaurant Finder (OSM)",
                "status": "New",
            })
            bulk_insert_leads(leads_df)
            invalidate()

            st.session_state["discovered_restaurants"] = results.drop(index=to_import.index)
            st.session_state["rf_editor_ver"] = st.session_state.get("rf_editor_ver", 0) + 1
            st.session_state["rf_import_flash"] = len(leads_df)
            st.rerun()
