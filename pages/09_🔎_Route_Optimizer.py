"""Route Optimizer - Scrape online sources for Asian restaurant leads along delivery routes."""

import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium

import config
from database.connection import init_db
from database.models import (
    get_all_routes, get_stops_by_route, get_leads_with_scores,
    get_scrape_history, get_table_counts,
)
from scraping.route_analyzer import analyze_routes, compute_route_stats
from scraping.scrape_manager import run_route_optimization
from maps.visualizations import ROUTE_COLORS

st.set_page_config(page_title="Route Optimizer", page_icon="🔎", layout="wide")

# Ensure DB is initialized
init_db()

st.title("🔎 Route Optimizer")
st.markdown(
    "Discover new **Asian restaurant** leads along your existing delivery routes. "
    "Find gaps in route coverage and fill them with nearby prospects to **improve "
    "route density** and **reduce drive time**."
)

# Check we have data
counts = get_table_counts()
if counts.get("routes", 0) == 0:
    st.warning("No routes loaded yet. Upload route data on the **Upload Data** page first.")
    st.stop()

routes_df = get_all_routes()

# ============================================================================
# SIDEBAR: Configuration
# ============================================================================
st.sidebar.header("Optimization Settings")

# Route selection
route_options = {f"{r['route_code']} - {r.get('route_name', '')}": int(r["id"])
                 for _, r in routes_df.iterrows()}
selected_route_labels = st.sidebar.multiselect(
    "Select Routes",
    options=list(route_options.keys()),
    default=list(route_options.keys()),
    help="Choose which routes to optimize. Leave all selected for full analysis.",
)
selected_route_ids = [route_options[label] for label in selected_route_labels]

if not selected_route_ids:
    st.info("Select at least one route from the sidebar.")
    st.stop()

# Gap threshold
gap_threshold = st.sidebar.slider(
    "Gap Threshold (miles)",
    min_value=1.0, max_value=10.0, value=2.0, step=0.5,
    help="Flag stretches between stops longer than this distance.",
)

# Search radius
search_radius = st.sidebar.slider(
    "Search Radius (miles)",
    min_value=0.5, max_value=5.0, value=1.0, step=0.5,
    help="How far around each search point to look for restaurants.",
)

# Cuisine selection
st.sidebar.subheader("Cuisine Filter")
cuisine_categories = list(config.CUISINE_CATEGORIES.keys())
selected_cuisines = []
for cat in cuisine_categories:
    if st.sidebar.checkbox(cat, value=True, key=f"cuisine_{cat}"):
        selected_cuisines.append(cat)

# Data sources
st.sidebar.subheader("Data Sources")
use_osm = st.sidebar.checkbox("OpenStreetMap (free)", value=True)
use_yelp = st.sidebar.checkbox("Yelp Fusion", value=False)
use_google = st.sidebar.checkbox("Google Places", value=False)

enabled_sources = []
if use_osm:
    enabled_sources.append("OpenStreetMap")
if use_yelp:
    enabled_sources.append("Yelp")
if use_google:
    enabled_sources.append("Google Places")

# API key inputs
google_api_key = ""
yelp_api_key = ""
if use_google:
    google_api_key = st.sidebar.text_input(
        "Google Places API Key",
        value=config.GOOGLE_PLACES_API_KEY,
        type="password",
        help="Set GOOGLE_PLACES_API_KEY env var or enter here.",
    )
if use_yelp:
    yelp_api_key = st.sidebar.text_input(
        "Yelp API Key",
        value=config.YELP_API_KEY,
        type="password",
        help="Set YELP_API_KEY env var or enter here.",
    )

# ============================================================================
# SECTION 1: Gap Analysis Preview
# ============================================================================
st.header("1. Route Gap Analysis")

with st.spinner("Analyzing routes..."):
    analysis = analyze_routes(selected_route_ids, gap_threshold)

# Summary metrics
total_gaps = sum(a["gap_count"] for a in analysis.values())
total_search_pts = sum(a["search_point_count"] for a in analysis.values())
total_gap_dist = sum(a["total_gap_distance_mi"] for a in analysis.values())

col1, col2, col3, col4 = st.columns(4)
col1.metric("Routes Selected", len(selected_route_ids))
col2.metric("Gaps Found", total_gaps)
col3.metric("Search Points", total_search_pts)
col4.metric("Total Gap Distance", f"{total_gap_dist:.1f} mi")

if total_gaps == 0:
    st.success(
        f"No gaps larger than {gap_threshold} miles found on selected routes. "
        "Try lowering the gap threshold or selecting different routes."
    )
    # Still show stats table
    stats_rows = []
    for rid in selected_route_ids:
        route_info = routes_df[routes_df["id"] == rid].iloc[0]
        stats = analysis[rid]["stats"]
        if stats:
            stats_rows.append({
                "Route": f"{route_info['route_code']} - {route_info.get('route_name', '')}",
                "Stops": stats["stop_count"],
                "Avg Spacing (mi)": stats["avg_spacing_mi"],
                "Max Spacing (mi)": stats["max_spacing_mi"],
                "Total Distance (mi)": stats["total_distance_mi"],
                "Gaps": 0,
            })
    if stats_rows:
        st.dataframe(pd.DataFrame(stats_rows), use_container_width=True, hide_index=True)

# Route stats table
if total_gaps > 0:
    stats_rows = []
    for rid in selected_route_ids:
        route_info = routes_df[routes_df["id"] == rid].iloc[0]
        a = analysis[rid]
        stats = a["stats"]
        if stats:
            stats_rows.append({
                "Route": f"{route_info['route_code']} - {route_info.get('route_name', '')}",
                "Stops": stats["stop_count"],
                "Avg Spacing (mi)": stats["avg_spacing_mi"],
                "Max Spacing (mi)": stats["max_spacing_mi"],
                "Total Distance (mi)": stats["total_distance_mi"],
                "Gaps": a["gap_count"],
                "Gap Distance (mi)": a["total_gap_distance_mi"],
                "Search Points": a["search_point_count"],
            })
    if stats_rows:
        st.dataframe(pd.DataFrame(stats_rows), use_container_width=True, hide_index=True)

    # Gap details expander
    with st.expander("Gap Details", expanded=False):
        gap_rows = []
        for rid in selected_route_ids:
            route_info = routes_df[routes_df["id"] == rid].iloc[0]
            for gap in analysis[rid]["gaps"]:
                gap_rows.append({
                    "Route": route_info["route_code"],
                    "From": gap["stop_a_name"],
                    "To": gap["stop_b_name"],
                    "Distance (mi)": gap["distance_miles"],
                })
        if gap_rows:
            st.dataframe(pd.DataFrame(gap_rows), use_container_width=True, hide_index=True)

    # Gap analysis map
    st.subheader("Gap Analysis Map")

    # Center map on all search points
    all_points = []
    for a in analysis.values():
        all_points.extend(a["search_points"])
        for gap in a["gaps"]:
            all_points.append((gap["midpoint_lat"], gap["midpoint_lon"]))

    if all_points:
        center = [np.mean([p[0] for p in all_points]), np.mean([p[1] for p in all_points])]
    else:
        center = [39.7392, -104.9903]

    m = folium.Map(location=center, zoom_start=11, tiles="OpenStreetMap")

    for i, rid in enumerate(selected_route_ids):
        route_info = routes_df[routes_df["id"] == rid].iloc[0]
        color = ROUTE_COLORS[i % len(ROUTE_COLORS)]
        stops_df = get_stops_by_route(rid)

        if not stops_df.empty:
            # Route polyline
            path = stops_df[["latitude", "longitude"]].values.tolist()
            folium.PolyLine(path, weight=3, color=color, opacity=0.7,
                            tooltip=route_info["route_code"]).add_to(m)

            # Stop markers
            for _, stop in stops_df.iterrows():
                if stop.get("stop_type") == "depot":
                    continue
                folium.CircleMarker(
                    [stop["latitude"], stop["longitude"]],
                    radius=5, color=color, fill=True, fill_color=color,
                    fill_opacity=0.8,
                    tooltip=f"{route_info['route_code']} - {stop.get('stop_name', '')}",
                ).add_to(m)

        # Gap lines (red dashed)
        for gap in analysis[rid]["gaps"]:
            folium.PolyLine(
                [[gap["stop_a_lat"], gap["stop_a_lon"]],
                 [gap["stop_b_lat"], gap["stop_b_lon"]]],
                weight=4, color="red", opacity=0.7, dash_array="10,8",
                tooltip=f"GAP: {gap['distance_miles']:.1f} mi",
            ).add_to(m)

        # Search points (yellow dots)
        for lat, lon in analysis[rid]["search_points"]:
            folium.CircleMarker(
                [lat, lon], radius=6, color="#FFC107", fill=True,
                fill_color="#FFC107", fill_opacity=0.9,
                tooltip=f"Search point ({lat:.4f}, {lon:.4f})",
            ).add_to(m)

    # Legend
    legend_html = """
    <div style="position:fixed;bottom:30px;left:30px;z-index:1000;background:white;
                padding:12px 16px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,0.2);
                font-family:Arial,sans-serif;font-size:12px;line-height:1.8;">
        <b>Gap Analysis</b><br>
        <span style="color:#2196F3;">&#9679;</span> Route Stops<br>
        <span style="color:red;">---</span> Gap (needs coverage)<br>
        <span style="color:#FFC107;">&#9679;</span> Search Points
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    st_folium(m, use_container_width=True, height=500)

# ============================================================================
# SECTION 2: Run Scrape
# ============================================================================
st.header("2. Discover Restaurants")

if total_gaps == 0 and total_search_pts == 0:
    st.info("No search points to scrape. Adjust the gap threshold above.")
else:
    if not enabled_sources:
        st.warning("Select at least one data source in the sidebar.")
    elif not selected_cuisines:
        st.warning("Select at least one cuisine category in the sidebar.")
    else:
        # Validation warnings
        if use_google and not google_api_key:
            st.warning("Google Places selected but no API key provided. It will be skipped.")
        if use_yelp and not yelp_api_key:
            st.warning("Yelp selected but no API key provided. It will be skipped.")

        st.markdown(
            f"Ready to search **{total_search_pts} points** using "
            f"**{', '.join(enabled_sources)}** for "
            f"**{', '.join(selected_cuisines)}** restaurants."
        )

        if st.button("🔍 Start Discovery", type="primary", use_container_width=True):
            progress_bar = st.progress(0)
            status_text = st.empty()

            def update_progress(pct, msg):
                progress_bar.progress(min(pct, 100))
                status_text.text(msg)

            result = run_route_optimization(
                route_ids=selected_route_ids,
                enabled_sources=enabled_sources,
                selected_cuisines=selected_cuisines,
                gap_threshold_miles=gap_threshold,
                search_radius_miles=search_radius,
                google_api_key=google_api_key if use_google else None,
                yelp_api_key=yelp_api_key if use_yelp else None,
                progress_callback=update_progress,
            )

            # Store results in session state for display
            st.session_state["optimizer_result"] = result

            progress_bar.progress(100)
            status_text.text("Complete!")

# ============================================================================
# SECTION 3: Results
# ============================================================================
if "optimizer_result" in st.session_state:
    result = st.session_state["optimizer_result"]

    st.header("3. Results")

    # Summary metrics
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Raw Results", result["results_found"])
    col2.metric("Cuisine Matched", result["cuisine_matched"])
    col3.metric("Duplicates Skipped", result["duplicates_skipped"])
    col4.metric("New Leads Created", result["leads_created"],
                delta=f"+{result['leads_created']}" if result["leads_created"] > 0 else None)
    col5.metric("Search Points", result["search_points"])

    if result["leads_created"] > 0:
        st.success(f"Added **{result['leads_created']}** new restaurant leads to your pipeline!")

        # Show new leads table
        leads_df = get_leads_with_scores()
        new_leads_df = leads_df[leads_df["source"].str.startswith("Route Optimizer", na=False)]

        if not new_leads_df.empty:
            # Sort by score
            new_leads_df = new_leads_df.sort_values("total_score", ascending=False)

            display_cols = ["name", "address", "city", "total_score", "score_grade",
                           "nearest_route_stop_distance_mi", "source", "phone"]
            available_cols = [c for c in display_cols if c in new_leads_df.columns]

            st.subheader("New Leads (Scored)")
            st.dataframe(
                new_leads_df[available_cols].rename(columns={
                    "name": "Restaurant",
                    "address": "Address",
                    "city": "City",
                    "total_score": "Score",
                    "score_grade": "Grade",
                    "nearest_route_stop_distance_mi": "Distance to Route (mi)",
                    "source": "Source",
                    "phone": "Phone",
                }),
                use_container_width=True,
                hide_index=True,
            )

            # Before/after density comparison
            st.subheader("Route Density Impact")
            impact_rows = []
            for rid in selected_route_ids:
                route_info = routes_df[routes_df["id"] == rid].iloc[0]
                before_stats = analysis.get(rid, {}).get("stats")
                after_stats = compute_route_stats(rid)

                if before_stats and after_stats:
                    # Count new leads assigned to this route
                    route_new = new_leads_df[
                        new_leads_df.get("nearest_route_id", pd.Series()) == rid
                    ] if "nearest_route_id" in new_leads_df.columns else pd.DataFrame()

                    impact_rows.append({
                        "Route": route_info["route_code"],
                        "Before: Gaps": analysis[rid]["gap_count"],
                        "Before: Avg Spacing (mi)": before_stats["avg_spacing_mi"],
                        "Before: Max Spacing (mi)": before_stats["max_spacing_mi"],
                        "New Leads Found": len(route_new),
                        "Potential Density Gain": f"+{len(route_new)} stops",
                    })

            if impact_rows:
                st.dataframe(pd.DataFrame(impact_rows), use_container_width=True, hide_index=True)

            # Results map
            st.subheader("Results Map")
            all_lats = new_leads_df["latitude"].tolist()
            all_lons = new_leads_df["longitude"].tolist()

            for rid in selected_route_ids:
                stops_df = get_stops_by_route(rid)
                if not stops_df.empty:
                    all_lats.extend(stops_df["latitude"].tolist())
                    all_lons.extend(stops_df["longitude"].tolist())

            if all_lats:
                center = [np.mean(all_lats), np.mean(all_lons)]
            else:
                center = [39.7392, -104.9903]

            rm = folium.Map(location=center, zoom_start=12, tiles="OpenStreetMap")

            # Draw routes
            for i, rid in enumerate(selected_route_ids):
                route_info = routes_df[routes_df["id"] == rid].iloc[0]
                color = ROUTE_COLORS[i % len(ROUTE_COLORS)]
                stops_df = get_stops_by_route(rid)

                if not stops_df.empty:
                    path = stops_df[["latitude", "longitude"]].values.tolist()
                    folium.PolyLine(path, weight=3, color=color, opacity=0.7,
                                    tooltip=route_info["route_code"]).add_to(rm)

                    for _, stop in stops_df.iterrows():
                        if stop.get("stop_type") == "depot":
                            continue
                        folium.CircleMarker(
                            [stop["latitude"], stop["longitude"]],
                            radius=5, color=color, fill=True, fill_color=color,
                            fill_opacity=0.8,
                            tooltip=f"{route_info['route_code']} - {stop.get('stop_name', '')}",
                        ).add_to(rm)

            # New lead markers (green)
            for _, lead in new_leads_df.iterrows():
                grade = lead.get("score_grade", "F")
                score = lead.get("total_score", 0)
                dist = lead.get("nearest_route_stop_distance_mi", 0)

                popup_html = f"""
                <div style='width:250px;font-family:Arial;'>
                    <h4 style='margin:0 0 5px;color:#333;'>{lead.get('name', '')}</h4>
                    <div style='background:#e8f5e9;padding:6px;border-radius:4px;margin-bottom:6px;'>
                        <b>Score: {score:.0f}</b> (Grade: {grade})
                    </div>
                    <table style='font-size:12px;width:100%;'>
                        <tr><td>Address:</td><td>{lead.get('address', '')}</td></tr>
                        <tr><td>City:</td><td>{lead.get('city', '')}</td></tr>
                        <tr><td>Distance:</td><td>{dist:.1f} mi to nearest stop</td></tr>
                        <tr><td>Phone:</td><td>{lead.get('phone', 'N/A')}</td></tr>
                        <tr><td>Source:</td><td>{lead.get('source', '')}</td></tr>
                    </table>
                </div>
                """

                folium.Marker(
                    [lead["latitude"], lead["longitude"]],
                    popup=folium.Popup(popup_html, max_width=280),
                    tooltip=f"NEW: {lead.get('name', '')} (Grade {grade})",
                    icon=folium.Icon(color="green", icon="cutlery", prefix="glyphicon"),
                ).add_to(rm)

            # Legend
            results_legend = """
            <div style="position:fixed;bottom:30px;left:30px;z-index:1000;background:white;
                        padding:12px 16px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,0.2);
                        font-family:Arial,sans-serif;font-size:12px;line-height:1.8;">
                <b>Route Optimizer Results</b><br>
                <span style="color:#2196F3;">&#9679;</span> Existing Stops<br>
                <span style="color:green;">&#9679;</span> New Restaurant Leads
            </div>
            """
            rm.get_root().html.add_child(folium.Element(results_legend))

            st_folium(rm, use_container_width=True, height=500)

    elif result["results_found"] == 0:
        st.info("No restaurants found in the search area. Try increasing the search radius or gap threshold.")
    else:
        st.info(
            f"Found {result['results_found']} restaurants but all were filtered "
            f"({result['duplicates_skipped']} duplicates, "
            f"{result['results_found'] - result['cuisine_matched']} didn't match cuisine filter)."
        )

# ============================================================================
# SECTION 4: Scrape History
# ============================================================================
st.header("4. Scrape History")
history_df = get_scrape_history()

if history_df.empty:
    st.info("No scrape runs yet. Run a discovery above to get started.")
else:
    display_cols = ["route_code", "source", "search_points_count", "results_found",
                    "leads_created", "duplicates_skipped", "cuisine_filtered",
                    "status", "started_at"]
    available = [c for c in display_cols if c in history_df.columns]

    st.dataframe(
        history_df[available].rename(columns={
            "route_code": "Route",
            "source": "Sources",
            "search_points_count": "Search Points",
            "results_found": "Found",
            "leads_created": "Leads Created",
            "duplicates_skipped": "Duplicates",
            "cuisine_filtered": "Cuisine Filtered",
            "status": "Status",
            "started_at": "Date",
        }),
        use_container_width=True,
        hide_index=True,
    )
