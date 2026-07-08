"""Map visualizations using Folium for route stops, customers, and prospects."""

import folium
from folium.plugins import MarkerCluster
import pandas as pd
import numpy as np

from config import MAP_DEFAULT_ZOOM, MAP_TILE_STYLE

DEFAULT_CENTER = [39.7392, -104.9903]  # Denver


def _valid_coords(df):
    """Drop rows with missing or ungeocoded (0, 0) coordinates."""
    if df is None:
        return pd.DataFrame()
    if df.empty or "latitude" not in df.columns or "longitude" not in df.columns:
        return df
    lat = df["latitude"]
    lon = df["longitude"]
    mask = lat.notna() & lon.notna() & ~((lat.abs() <= 0.01) & (lon.abs() <= 0.01))
    return df[mask]


def _compute_center(*dfs):
    """Mean center of all valid coordinates, falling back to Denver."""
    all_lats = []
    all_lons = []
    for df in dfs:
        if df is not None and not df.empty and "latitude" in df.columns:
            all_lats.extend(df["latitude"].tolist())
            all_lons.extend(df["longitude"].tolist())
    if not all_lats:
        return DEFAULT_CENTER
    return [np.mean(all_lats), np.mean(all_lons)]

# Grade-based marker colors
GRADE_COLORS = {
    "A": "red",
    "B": "orange",
    "C": "beige",
    "D": "gray",
    "F": "lightgray",
}

GRADE_ICONS = {
    "A": "star",
    "B": "arrow-up",
    "C": "info-sign",
    "D": "arrow-down",
    "F": "remove",
}

# Route line colors (cycle through for multiple routes)
ROUTE_COLORS = [
    "#2196F3", "#4CAF50", "#FF9800", "#9C27B0", "#F44336",
    "#00BCD4", "#795548", "#607D8B", "#E91E63", "#3F51B5",
    "#009688", "#FF5722", "#673AB7", "#CDDC39", "#FFC107",
]


def create_route_map(route_data, customers_df, stops_df, leads_df, dc_info=None,
                     show_radius=True, show_connectors=True):
    """Create an interactive map for a single route.

    Shows route path, numbered stops, customers, and color-coded prospects
    with connector lines to nearest stops.
    """
    customers_df = _valid_coords(customers_df)
    stops_df = _valid_coords(stops_df)
    leads_df = _valid_coords(leads_df)

    center = _compute_center(stops_df, leads_df)

    m = folium.Map(location=center, zoom_start=MAP_DEFAULT_ZOOM + 2, tiles=MAP_TILE_STYLE)

    # --- DC marker ---
    if dc_info:
        folium.Marker(
            [dc_info["latitude"], dc_info["longitude"]],
            popup=f"<b>Distribution Center</b><br>{dc_info['name']}<br>{dc_info.get('address', '')}",
            tooltip=dc_info["name"],
            icon=folium.Icon(color="black", icon="home", prefix="glyphicon"),
        ).add_to(m)

    # --- Route path polyline ---
    if not stops_df.empty:
        path_coords = stops_df[["latitude", "longitude"]].values.tolist()
        folium.PolyLine(
            path_coords,
            weight=3,
            color="#2196F3",
            opacity=0.8,
            tooltip=route_data.get("route_code", "Route"),
        ).add_to(m)

    # --- Route stops with sequence numbers ---
    if not stops_df.empty:
        for _, stop in stops_df.iterrows():
            if stop.get("stop_type") == "depot":
                continue  # Already shown as DC marker

            seq = stop.get("stop_sequence", "")
            name = stop.get("stop_name", "Stop")

            popup_html = f"""
            <div style='width:200px'>
                <b>Stop #{seq}: {name}</b><br>
                Type: {stop.get('stop_type', 'customer')}
            </div>
            """

            folium.Marker(
                [stop["latitude"], stop["longitude"]],
                popup=folium.Popup(popup_html, max_width=250),
                tooltip=f"Stop #{seq}: {name}",
                icon=folium.DivIcon(
                    html=f'<div style="background:#2196F3;color:white;border-radius:50%;'
                         f'width:24px;height:24px;text-align:center;line-height:24px;'
                         f'font-size:11px;font-weight:bold;border:2px solid white;'
                         f'box-shadow:0 1px 3px rgba(0,0,0,0.3);">{seq}</div>',
                    icon_size=(24, 24),
                    icon_anchor=(12, 12),
                ),
            ).add_to(m)

            # Optional radius circles
            if show_radius:
                for radius_mi, color, fill_opacity in [(0.5, "#2196F3", 0.03), (1.0, "#2196F3", 0.02)]:
                    folium.Circle(
                        [stop["latitude"], stop["longitude"]],
                        radius=radius_mi * 1609.34,  # miles to meters
                        color=color,
                        fill=True,
                        fill_opacity=fill_opacity,
                        weight=1,
                        opacity=0.3,
                    ).add_to(m)

    # --- Lead markers ---
    if not leads_df.empty:
        for _, lead in leads_df.iterrows():
            grade = lead.get("score_grade", "F")
            color = GRADE_COLORS.get(grade, "lightgray")
            score = lead.get("total_score", 0)
            dist = lead.get("nearest_route_stop_distance_mi", 0)
            stop_name = lead.get("nearest_stop_name", "N/A")

            popup_html = f"""
            <div style='width:280px;font-family:Arial,sans-serif;'>
                <h4 style='margin:0 0 5px 0;color:#333;'>{lead.get('name', 'Unknown')}</h4>
                <div style='background:#f5f5f5;padding:8px;border-radius:4px;margin-bottom:8px;'>
                    <b>Score: {score:.0f}</b> (Grade: <span style='font-size:16px;font-weight:bold;'>{grade}</span>)
                    {'<br><span style="color:green;">&#9733; Core Segment</span>' if lead.get('is_core_segment') else ''}
                </div>
                <table style='width:100%;font-size:12px;'>
                    <tr><td>Business Type:</td><td><b>{lead.get('business_type', 'N/A')}</b></td></tr>
                    <tr><td>Segment:</td><td><b>{lead.get('segment', 'N/A')}</b></td></tr>
                    <tr><td>Est. Revenue:</td><td><b>${lead.get('estimated_weekly_revenue', 0):,.0f}/week</b></td></tr>
                    <tr><td>Nearest Stop:</td><td><b>{dist:.1f} mi - {stop_name}</b></td></tr>
                    <tr><td>Phone:</td><td>{lead.get('phone', 'N/A')}</td></tr>
                </table>
                <div style='margin-top:8px;font-size:11px;'>
                    <b>Score Breakdown:</b><br>
                    Proximity: {lead.get('proximity_score', 0):.0f} |
                    Segment: {lead.get('segment_score', 0):.0f} |
                    Density: {lead.get('density_score', 0):.0f} |
                    Revenue: {lead.get('revenue_score', 0):.0f}
                </div>
            </div>
            """

            folium.Marker(
                [lead["latitude"], lead["longitude"]],
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=f"{lead.get('name', '')} (Grade {grade}, Score {score:.0f})",
                icon=folium.Icon(color=color, icon=GRADE_ICONS.get(grade, "info-sign"), prefix="glyphicon"),
            ).add_to(m)

            # Connector line from lead to nearest stop (A and B grades only)
            if show_connectors and grade in ("A", "B") and not stops_df.empty:
                nearest_stop_id = lead.get("nearest_stop_id")
                if nearest_stop_id is not None:
                    stop_row = stops_df[stops_df["id"] == nearest_stop_id]
                    if not stop_row.empty:
                        stop = stop_row.iloc[0]
                        folium.PolyLine(
                            [[lead["latitude"], lead["longitude"]],
                             [stop["latitude"], stop["longitude"]]],
                            weight=2,
                            color=color,
                            opacity=0.6,
                            dash_array="5,10",
                            tooltip=f"{dist:.1f} mi to {stop_name}",
                        ).add_to(m)

    # Add legend
    _add_legend(m)

    return m


def create_dc_map(dc_info, routes_df, customers_df, stops_df, leads_df):
    """Create an overview map for a distribution center showing all routes."""
    customers_df = _valid_coords(customers_df)
    stops_df = _valid_coords(stops_df)
    leads_df = _valid_coords(leads_df)

    center = [dc_info["latitude"], dc_info["longitude"]]
    m = folium.Map(location=center, zoom_start=MAP_DEFAULT_ZOOM, tiles=MAP_TILE_STYLE)

    # DC marker
    folium.Marker(
        center,
        popup=f"<b>{dc_info['name']}</b><br>{dc_info.get('address', '')}",
        tooltip=dc_info["name"],
        icon=folium.Icon(color="black", icon="home", prefix="glyphicon"),
    ).add_to(m)

    # Draw each route as a colored polyline
    for i, (_, route) in enumerate(routes_df.iterrows()):
        color = ROUTE_COLORS[i % len(ROUTE_COLORS)]
        route_stops = stops_df[stops_df["route_id"] == route["id"]].sort_values("stop_sequence")

        if not route_stops.empty:
            path = route_stops[["latitude", "longitude"]].values.tolist()
            folium.PolyLine(
                path,
                weight=3,
                color=color,
                opacity=0.7,
                tooltip=f"{route['route_code']}: {route.get('route_name', '')}",
            ).add_to(m)

            # Small dots for stops
            for _, stop in route_stops.iterrows():
                if stop.get("stop_type") == "depot":
                    continue
                folium.CircleMarker(
                    [stop["latitude"], stop["longitude"]],
                    radius=4,
                    color=color,
                    fill=True,
                    fill_color=color,
                    fill_opacity=0.8,
                    tooltip=f"{route['route_code']} - {stop.get('stop_name', '')}",
                ).add_to(m)

    # Lead markers (clustered for performance)
    if not leads_df.empty and "score_grade" in leads_df.columns:
        lead_cluster = MarkerCluster(name="Prospects").add_to(m)
        for _, lead in leads_df.iterrows():
            grade = lead.get("score_grade", "F")
            color = GRADE_COLORS.get(grade, "lightgray")

            folium.Marker(
                [lead["latitude"], lead["longitude"]],
                popup=f"<b>{lead.get('name', '')}</b><br>Grade: {grade} | Score: {lead.get('total_score', 0):.0f}",
                tooltip=f"{lead.get('name', '')} ({grade})",
                icon=folium.Icon(color=color, icon="briefcase", prefix="glyphicon"),
            ).add_to(lead_cluster)

    _add_legend(m)
    folium.LayerControl().add_to(m)

    return m


def create_full_map(dcs_df, routes_df, customers_df, stops_df, leads_df):
    """Create a full overview map with all DCs, routes, and leads."""
    customers_df = _valid_coords(customers_df)
    stops_df = _valid_coords(stops_df)
    leads_df = _valid_coords(leads_df)

    center = _compute_center(dcs_df, customers_df, leads_df)

    m = folium.Map(location=center, zoom_start=MAP_DEFAULT_ZOOM - 1, tiles=MAP_TILE_STYLE)

    # DC markers
    if not dcs_df.empty:
        for _, dc in dcs_df.iterrows():
            folium.Marker(
                [dc["latitude"], dc["longitude"]],
                popup=f"<b>{dc['name']}</b><br>{dc.get('code', '')}",
                tooltip=dc["name"],
                icon=folium.Icon(color="black", icon="home", prefix="glyphicon"),
            ).add_to(m)

    # Route polylines
    if not routes_df.empty and not stops_df.empty:
        for i, (_, route) in enumerate(routes_df.iterrows()):
            color = ROUTE_COLORS[i % len(ROUTE_COLORS)]
            route_stops = stops_df[stops_df["route_id"] == route["id"]].sort_values("stop_sequence")
            if not route_stops.empty:
                path = route_stops[["latitude", "longitude"]].values.tolist()
                folium.PolyLine(
                    path, weight=2, color=color, opacity=0.5,
                    tooltip=route.get("route_code", ""),
                ).add_to(m)

    # Customer markers (clustered)
    if not customers_df.empty:
        cust_cluster = MarkerCluster(name="Existing Customers").add_to(m)
        for _, cust in customers_df.iterrows():
            folium.Marker(
                [cust["latitude"], cust["longitude"]],
                popup=f"<b>{cust['name']}</b><br>{cust.get('business_type', '')}",
                tooltip=cust["name"],
                icon=folium.Icon(color="blue", icon="user", prefix="glyphicon"),
            ).add_to(cust_cluster)

    # Lead markers (clustered)
    if not leads_df.empty:
        lead_cluster = MarkerCluster(name="Prospects").add_to(m)
        for _, lead in leads_df.iterrows():
            grade = lead.get("score_grade", "F") if "score_grade" in leads_df.columns else "F"
            color = GRADE_COLORS.get(grade, "lightgray")
            folium.Marker(
                [lead["latitude"], lead["longitude"]],
                popup=f"<b>{lead.get('name', '')}</b><br>Grade: {grade}",
                tooltip=f"{lead.get('name', '')} ({grade})",
                icon=folium.Icon(color=color, icon="briefcase", prefix="glyphicon"),
            ).add_to(lead_cluster)

    _add_legend(m)
    folium.LayerControl().add_to(m)

    return m


def _add_legend(m):
    """Add a color legend to the map."""
    legend_html = """
    <div style="position: fixed; bottom: 30px; left: 30px; z-index: 1000;
                background: white; padding: 12px 16px; border-radius: 8px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.2); font-family: Arial, sans-serif;
                font-size: 12px; line-height: 1.8;">
        <b style="font-size:13px;">Legend</b><br>
        <span style="color:#000;">&#9679;</span> Distribution Center<br>
        <span style="color:#2196F3;">&#9679;</span> Route Path / Stops<br>
        <span style="color:red;">&#9679;</span> Grade A Lead (Hot)<br>
        <span style="color:orange;">&#9679;</span> Grade B Lead (Strong)<br>
        <span style="color:#DAA520;">&#9679;</span> Grade C Lead (Moderate)<br>
        <span style="color:gray;">&#9679;</span> Grade D/F Lead (Low)<br>
        <span style="color:#2196F3;">&#9675;</span> Radius (0.5 / 1.0 mi)<br>
        <span style="color:orange;">---</span> Connector to Nearest Stop
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
