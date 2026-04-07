"""Route gap analysis - identifies gaps between stops and generates search points."""

import math

import numpy as np

import config
from database.models import get_stops_by_route, get_all_routes
from scoring.proximity import _haversine_miles


def find_route_gaps(route_id, gap_threshold_miles=None):
    """Find gaps (long stretches) between consecutive route stops.

    Args:
        route_id: ID of the route to analyze.
        gap_threshold_miles: Minimum distance to consider a gap (default from config).

    Returns:
        List of gap dicts: {stop_a, stop_b, distance_miles, midpoint_lat, midpoint_lon,
                            stop_a_seq, stop_b_seq}
    """
    if gap_threshold_miles is None:
        gap_threshold_miles = config.ROUTE_GAP_THRESHOLD_MILES

    stops_df = get_stops_by_route(route_id)
    if stops_df.empty or len(stops_df) < 2:
        return []

    gaps = []
    for i in range(len(stops_df) - 1):
        a = stops_df.iloc[i]
        b = stops_df.iloc[i + 1]

        dist = _haversine_miles(a["latitude"], a["longitude"],
                                b["latitude"], b["longitude"])

        if dist >= gap_threshold_miles:
            gaps.append({
                "stop_a_id": int(a["id"]),
                "stop_b_id": int(b["id"]),
                "stop_a_name": a.get("stop_name", f"Stop {a['stop_sequence']}"),
                "stop_b_name": b.get("stop_name", f"Stop {b['stop_sequence']}"),
                "stop_a_seq": int(a["stop_sequence"]),
                "stop_b_seq": int(b["stop_sequence"]),
                "stop_a_lat": float(a["latitude"]),
                "stop_a_lon": float(a["longitude"]),
                "stop_b_lat": float(b["latitude"]),
                "stop_b_lon": float(b["longitude"]),
                "distance_miles": round(dist, 2),
                "midpoint_lat": (a["latitude"] + b["latitude"]) / 2,
                "midpoint_lon": (a["longitude"] + b["longitude"]) / 2,
            })

    return gaps


def generate_search_points(gaps, spacing_miles=None):
    """Generate search points along gaps for restaurant discovery.

    Places points every `spacing_miles` along each gap segment.

    Args:
        gaps: List of gap dicts from find_route_gaps().
        spacing_miles: Distance between search points (default from config).

    Returns:
        List of (lat, lon) tuples for search centers.
    """
    if spacing_miles is None:
        spacing_miles = config.SEARCH_POINT_SPACING_MILES

    points = []
    for gap in gaps:
        lat_a, lon_a = gap["stop_a_lat"], gap["stop_a_lon"]
        lat_b, lon_b = gap["stop_b_lat"], gap["stop_b_lon"]
        dist = gap["distance_miles"]

        num_points = max(1, int(dist / spacing_miles))

        for j in range(1, num_points + 1):
            frac = j / (num_points + 1)
            lat = lat_a + frac * (lat_b - lat_a)
            lon = lon_a + frac * (lon_b - lon_a)
            points.append((round(lat, 6), round(lon, 6)))

    return points


def deduplicate_search_points(points, min_distance_miles=0.25):
    """Remove search points that are too close to each other.

    Args:
        points: List of (lat, lon) tuples.
        min_distance_miles: Minimum distance between kept points.

    Returns:
        Deduplicated list of (lat, lon) tuples.
    """
    if not points:
        return []

    kept = [points[0]]
    for lat, lon in points[1:]:
        too_close = False
        for klat, klon in kept:
            if _haversine_miles(lat, lon, klat, klon) < min_distance_miles:
                too_close = True
                break
        if not too_close:
            kept.append((lat, lon))

    return kept


def compute_route_stats(route_id):
    """Compute statistics about a route's stop spacing.

    Returns:
        Dict with avg_spacing_mi, max_spacing_mi, min_spacing_mi, stop_count, total_distance_mi.
        Returns None if route has < 2 stops.
    """
    stops_df = get_stops_by_route(route_id)
    if stops_df.empty or len(stops_df) < 2:
        return None

    distances = []
    for i in range(len(stops_df) - 1):
        a = stops_df.iloc[i]
        b = stops_df.iloc[i + 1]
        d = _haversine_miles(a["latitude"], a["longitude"],
                             b["latitude"], b["longitude"])
        distances.append(d)

    return {
        "stop_count": len(stops_df),
        "total_distance_mi": round(sum(distances), 2),
        "avg_spacing_mi": round(np.mean(distances), 2),
        "max_spacing_mi": round(max(distances), 2),
        "min_spacing_mi": round(min(distances), 2),
        "segment_count": len(distances),
    }


def analyze_routes(route_ids=None, gap_threshold_miles=None):
    """Analyze one or more routes for gaps and search opportunities.

    Args:
        route_ids: List of route IDs to analyze. If None, analyzes all routes.
        gap_threshold_miles: Gap threshold override.

    Returns:
        Dict mapping route_id -> {route_info, gaps, search_points, stats}
    """
    if route_ids is None:
        routes_df = get_all_routes()
        route_ids = routes_df["id"].tolist()

    results = {}
    for rid in route_ids:
        gaps = find_route_gaps(rid, gap_threshold_miles)
        raw_points = generate_search_points(gaps)
        search_points = deduplicate_search_points(raw_points)
        stats = compute_route_stats(rid)

        results[rid] = {
            "gaps": gaps,
            "search_points": search_points,
            "stats": stats,
            "gap_count": len(gaps),
            "search_point_count": len(search_points),
            "total_gap_distance_mi": round(sum(g["distance_miles"] for g in gaps), 2),
        }

    return results
