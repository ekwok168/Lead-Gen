"""Restaurant discovery via the OpenStreetMap Overpass API.

Clusters search coordinates to minimize API calls, queries Overpass for
food-service amenities, and normalizes results into a DataFrame ready for
lead review.
"""

import json
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN

import config
from utils.dedup import haversine_miles

EARTH_RADIUS_MI = 3959.0
METERS_PER_MILE = 1609.34

# Output schema for parse_overpass_elements / discover_restaurants
PARSED_COLUMNS = [
    "osm_id",
    "name",
    "latitude",
    "longitude",
    "amenity",
    "cuisine",
    "phone",
    "website",
    "address",
    "business_type",
    "segment",
]


def cluster_coordinates(coords, radius_miles):
    """Group nearby search points into clusters to minimize API calls.

    Args:
        coords: list of (lat, lon) tuples.
        radius_miles: desired search radius around each point.

    Returns:
        List of (centroid_lat, centroid_lon, effective_radius_miles) tuples.
        The effective radius is enlarged so the cluster circle covers every
        member point's original search radius.
    """
    valid = []
    for lat, lon in coords:
        if lat is None or lon is None:
            continue
        lat, lon = float(lat), float(lon)
        if np.isnan(lat) or np.isnan(lon):
            continue
        if abs(lat) < 1e-6 and abs(lon) < 1e-6:
            continue
        valid.append((lat, lon))

    if not valid:
        return []

    points = np.array(valid, dtype=np.float64)
    points_rad = np.radians(points)

    eps = radius_miles / EARTH_RADIUS_MI
    labels = DBSCAN(eps=eps, min_samples=1, metric="haversine").fit_predict(points_rad)

    clusters = []
    for label in sorted(set(labels)):
        members = points[labels == label]
        centroid, effective_radius = _emit_cluster(members, radius_miles)
        if effective_radius <= radius_miles * 2.5:
            clusters.append((centroid[0], centroid[1], effective_radius))
            continue
        # DBSCAN chains points transitively (e.g. stops strung along a route),
        # which can balloon one cluster to an area Overpass cannot serve.
        # Split oversized clusters on a grid of ~radius-sized cells; the cell
        # diagonal bounds each subgroup's effective radius at ~1.71x radius.
        lat_cell = radius_miles / 69.0
        lon_cell = radius_miles / (69.0 * max(np.cos(np.radians(members[:, 0].mean())), 0.01))
        cells = {}
        for lat, lon in members:
            key = (int(np.floor(lat / lat_cell)), int(np.floor(lon / lon_cell)))
            cells.setdefault(key, []).append((lat, lon))
        for cell_members in cells.values():
            centroid, effective_radius = _emit_cluster(
                np.array(cell_members, dtype=np.float64), radius_miles
            )
            clusters.append((centroid[0], centroid[1], effective_radius))

    return clusters


def _emit_cluster(members, radius_miles):
    """Return ((centroid_lat, centroid_lon), effective_radius) for member points."""
    centroid_lat = float(members[:, 0].mean())
    centroid_lon = float(members[:, 1].mean())
    dists = haversine_miles(centroid_lat, centroid_lon, members[:, 0], members[:, 1])
    return (centroid_lat, centroid_lon), radius_miles + float(np.max(dists))


def build_overpass_query(lat, lon, radius_m, amenities):
    """Build an Overpass QL query for the given amenities around a point."""
    lines = [f"[out:json][timeout:{config.OVERPASS_TIMEOUT}];", "("]
    for amenity in amenities:
        lines.append(f'  node["amenity"="{amenity}"](around:{radius_m:.0f},{lat:.6f},{lon:.6f});')
        lines.append(f'  way["amenity"="{amenity}"](around:{radius_m:.0f},{lat:.6f},{lon:.6f});')
    lines.append(");")
    lines.append("out center;")
    return "\n".join(lines)


def query_overpass(query):
    """POST a query to the Overpass API and return the parsed JSON dict.

    Retries on rate limiting (429), gateway timeout (504), and network
    errors with exponential backoff. Raises RuntimeError once retries
    are exhausted.
    """
    data = urlencode({"data": query}).encode()
    last_error = None

    for attempt in range(config.OVERPASS_MAX_RETRIES + 1):
        if attempt > 0:
            time.sleep(2 ** attempt)  # 2s, 4s, 8s
        try:
            request = urllib.request.Request(
                config.OVERPASS_API_URL,
                data=data,
                headers={"User-Agent": "LeadGenTool/1.0"},
            )
            with urllib.request.urlopen(request, timeout=config.OVERPASS_TIMEOUT) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_error = e
            if e.code in (429, 504):
                continue
            raise RuntimeError(f"Overpass API returned HTTP {e.code}: {e.reason}") from e
        except urllib.error.URLError as e:
            last_error = e
            continue

    raise RuntimeError(
        f"Overpass API request failed after {config.OVERPASS_MAX_RETRIES} retries: {last_error}"
    )


def _build_address(tags):
    """Assemble a display address from OSM addr:* tags, skipping missing parts."""
    housenumber = tags.get("addr:housenumber", "").strip()
    street = tags.get("addr:street", "").strip()
    city = tags.get("addr:city", "").strip()
    postcode = tags.get("addr:postcode", "").strip()

    street_part = " ".join(p for p in (housenumber, street) if p)
    return ", ".join(p for p in (street_part, city, postcode) if p)


def parse_overpass_elements(elements):
    """Normalize Overpass elements into a DataFrame.

    Nodes carry lat/lon directly; ways carry a center dict. Elements with
    no name tag or no resolvable coordinates are skipped.
    """
    rows = []
    for element in elements or []:
        tags = element.get("tags", {}) or {}
        name = tags.get("name")
        if not name:
            continue

        if "lat" in element and "lon" in element:
            lat, lon = element["lat"], element["lon"]
        elif "center" in element:
            center = element["center"] or {}
            lat, lon = center.get("lat"), center.get("lon")
        else:
            lat, lon = None, None
        if lat is None or lon is None:
            continue

        amenity = tags.get("amenity", "")
        business_type, segment = config.AMENITY_BUSINESS_TYPE_MAP.get(amenity, ("", ""))

        rows.append({
            "osm_id": f"{element.get('type', 'node')}/{element.get('id', '')}",
            "name": name,
            "latitude": float(lat),
            "longitude": float(lon),
            "amenity": amenity,
            "cuisine": tags.get("cuisine", ""),
            "phone": tags.get("phone", tags.get("contact:phone", "")),
            "website": tags.get("website", tags.get("contact:website", "")),
            "address": _build_address(tags),
            "business_type": business_type,
            "segment": segment,
        })

    if not rows:
        return pd.DataFrame(columns=PARSED_COLUMNS)
    return pd.DataFrame(rows, columns=PARSED_COLUMNS)


def discover_restaurants(search_coords, radius_miles=None, amenities=None,
                         progress_callback=None):
    """Discover restaurants near a set of search coordinates.

    Args:
        search_coords: list of (lat, lon) tuples to search around.
        radius_miles: search radius per point (default from config).
        amenities: amenity types to query (default from config).
        progress_callback: optional callable(pct: int, msg: str).

    Returns:
        DataFrame with PARSED_COLUMNS plus a distance_mi column giving the
        haversine distance to the nearest original search coordinate.
    """
    if radius_miles is None:
        radius_miles = config.OVERPASS_DEFAULT_RADIUS_MI
    if amenities is None:
        amenities = list(config.DISCOVERY_AMENITY_TYPES)

    def report(pct, msg):
        if progress_callback is not None:
            progress_callback(int(pct), msg)

    empty = pd.DataFrame(columns=PARSED_COLUMNS + ["distance_mi"])

    report(0, "Clustering search locations...")
    clusters = cluster_coordinates(list(search_coords), radius_miles)
    if not clusters:
        report(100, "No valid search coordinates.")
        return empty

    all_elements = []
    errors = []
    n = len(clusters)
    for i, (lat, lon, eff_radius) in enumerate(clusters):
        if i > 0:
            time.sleep(config.OVERPASS_RATE_LIMIT_DELAY)
        report(int(5 + 75 * i / n), f"Querying area {i + 1} of {n}...")
        query = build_overpass_query(lat, lon, eff_radius * METERS_PER_MILE, amenities)
        try:
            result = query_overpass(query)
            all_elements.extend(result.get("elements", []))
        except RuntimeError as e:
            errors.append(str(e))
            report(int(5 + 75 * (i + 1) / n),
                   f"Warning: area {i + 1} of {n} failed ({e}); continuing...")

    if errors and len(errors) == n:
        raise RuntimeError(
            f"All {n} Overpass queries failed. First error: {errors[0]}"
        )

    report(80, "Processing results...")

    # Dedup overlapping cluster results by OSM id
    seen = set()
    unique_elements = []
    for element in all_elements:
        key = f"{element.get('type', 'node')}/{element.get('id', '')}"
        if key in seen:
            continue
        seen.add(key)
        unique_elements.append(element)

    df = parse_overpass_elements(unique_elements)
    if df.empty:
        report(100, "No restaurants found.")
        return empty

    report(90, "Computing distances...")
    search_arr = np.array(
        [(float(lat), float(lon)) for lat, lon in search_coords
         if lat is not None and lon is not None
         and not (np.isnan(float(lat)) or np.isnan(float(lon)))
         and not (abs(float(lat)) < 1e-6 and abs(float(lon)) < 1e-6)],
        dtype=np.float64,
    )
    search_lats = search_arr[:, 0]
    search_lons = search_arr[:, 1]
    distances = [
        float(np.min(haversine_miles(row_lat, row_lon, search_lats, search_lons)))
        for row_lat, row_lon in zip(df["latitude"].to_numpy(), df["longitude"].to_numpy())
    ]
    df["distance_mi"] = np.round(distances, 3)
    df = df[df["distance_mi"] <= radius_miles].reset_index(drop=True)

    report(100, f"Found {len(df)} restaurants.")
    return df
