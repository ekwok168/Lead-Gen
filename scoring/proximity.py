"""Proximity scoring - measures distance from lead to nearest route stop."""

import numpy as np
from sklearn.neighbors import BallTree

import config


def score_proximity(distance_miles):
    """Score a single distance value using stepped tiers.

    Returns a score 0-100 where higher = closer to a route stop.
    """
    for max_dist, score in config.PROXIMITY_TIERS:
        if distance_miles <= max_dist:
            return score
    return config.PROXIMITY_DEFAULT_SCORE


def compute_nearest_stops(lead_coords, stop_coords, stop_ids, stop_route_ids, stop_names):
    """Find the nearest route stop for each lead using BallTree.

    Args:
        lead_coords: array of (lat, lon) for each lead
        stop_coords: array of (lat, lon) for each route stop
        stop_ids: array of stop IDs
        stop_route_ids: array of route IDs for each stop
        stop_names: array of stop names

    Returns:
        List of dicts with nearest stop info per lead:
        - nearest_stop_id, nearest_route_id, distance_miles,
          proximity_score, nearest_stop_name
    """
    if len(lead_coords) == 0 or len(stop_coords) == 0:
        return []

    # Convert to radians for haversine
    lead_rad = np.radians(np.array(lead_coords, dtype=np.float64))
    stop_rad = np.radians(np.array(stop_coords, dtype=np.float64))

    tree = BallTree(stop_rad, metric="haversine")
    distances, indices = tree.query(lead_rad, k=1)

    # Convert radians to miles (Earth radius ~3959 miles)
    distances_miles = distances.flatten() * 3959.0
    indices = indices.flatten()

    results = []
    for i, (dist, idx) in enumerate(zip(distances_miles, indices)):
        results.append({
            "nearest_stop_id": int(stop_ids[idx]),
            "nearest_route_id": int(stop_route_ids[idx]),
            "nearest_stop_name": stop_names[idx],
            "nearest_route_stop_distance_mi": round(dist, 3),
            "proximity_score": score_proximity(dist),
        })

    return results


def compute_nearest_customers(lead_coords, cust_coords):
    """Find distance to nearest existing customer for each lead.

    Returns array of distances in miles.
    """
    if len(lead_coords) == 0 or len(cust_coords) == 0:
        return np.full(len(lead_coords), 999.0)

    lead_rad = np.radians(np.array(lead_coords, dtype=np.float64))
    cust_rad = np.radians(np.array(cust_coords, dtype=np.float64))

    tree = BallTree(cust_rad, metric="haversine")
    distances, _ = tree.query(lead_rad, k=1)

    return (distances.flatten() * 3959.0).round(3)


def find_insertion_point(lead_lat, lead_lon, route_stop_coords, route_stop_sequences):
    """Find the best insertion point in a route for a new stop.

    Returns the stop_sequence after which the lead should be inserted.
    """
    if len(route_stop_coords) < 2:
        return 1

    min_detour = float("inf")
    best_pos = 1

    lead = np.array([lead_lat, lead_lon])

    for i in range(len(route_stop_coords) - 1):
        a = np.array(route_stop_coords[i])
        b = np.array(route_stop_coords[i + 1])

        # Detour = dist(a, lead) + dist(lead, b) - dist(a, b)
        d_a_lead = _haversine_miles(a[0], a[1], lead[0], lead[1])
        d_lead_b = _haversine_miles(lead[0], lead[1], b[0], b[1])
        d_a_b = _haversine_miles(a[0], a[1], b[0], b[1])
        detour = d_a_lead + d_lead_b - d_a_b

        if detour < min_detour:
            min_detour = detour
            best_pos = route_stop_sequences[i]

    return best_pos


def _haversine_miles(lat1, lon1, lat2, lon2):
    """Haversine distance between two points in miles."""
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 3959.0 * 2 * np.arcsin(np.sqrt(a))
