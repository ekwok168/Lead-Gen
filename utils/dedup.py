"""Duplicate detection utilities shared across upload and entry pages."""

import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process

import config


def haversine_miles(lat1, lon1, lat2, lon2):
    """Haversine distance in miles. Accepts scalars or numpy arrays."""
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 3959.0 * 2 * np.arcsin(np.sqrt(a))


def _route_info(match):
    if "route_code" in match.index:
        return f" on route {match.get('route_code', 'N/A')}"
    return ""


def check_duplicate(name, lat, lon, existing_df, name_threshold=None, distance_threshold_mi=None):
    """Check if a record duplicates one in existing_df.

    Uses exact name match, fuzzy name match, and haversine proximity.
    Returns (is_duplicate, info_string).
    """
    if name_threshold is None:
        name_threshold = config.DUPLICATE_NAME_SIMILARITY_THRESHOLD
    if distance_threshold_mi is None:
        distance_threshold_mi = config.DUPLICATE_DISTANCE_THRESHOLD_MI

    if existing_df is None or existing_df.empty:
        return False, ""

    name_lower = str(name).lower().strip() if name is not None and not pd.isna(name) else ""

    if name_lower and "name" in existing_df.columns:
        existing_names = existing_df["name"].fillna("").astype(str).str.lower().str.strip()

        exact = existing_df[existing_names == name_lower]
        if not exact.empty:
            match = exact.iloc[0]
            return True, f"Exact name match: '{match['name']}'{_route_info(match)}"

        result = process.extractOne(
            name_lower,
            existing_names.tolist(),
            scorer=fuzz.ratio,
            score_cutoff=name_threshold,
        )
        if result is not None:
            match = existing_df.iloc[result[2]]
            return True, f"Similar name: '{match['name']}'{_route_info(match)}"

    lat = 0.0 if lat is None or pd.isna(lat) else float(lat)
    lon = 0.0 if lon is None or pd.isna(lon) else float(lon)
    if lat != 0 and lon != 0 and "latitude" in existing_df.columns and "longitude" in existing_df.columns:
        coords = existing_df[["latitude", "longitude"]].dropna()
        if not coords.empty:
            dists = haversine_miles(
                lat, lon,
                coords["latitude"].to_numpy(dtype=np.float64),
                coords["longitude"].to_numpy(dtype=np.float64),
            )
            close = np.where(dists <= distance_threshold_mi)[0]
            if len(close) > 0:
                match = existing_df.loc[coords.index[close[0]]]
                return True, f"Within {dists[close[0]]:.2f} mi of existing: '{match.get('name', 'Unknown')}'"

    return False, ""


def filter_duplicates(new_df, existing_customers_df, existing_leads_df,
                      name_col="name", lat_col="latitude", lon_col="longitude"):
    """Split new_df into (unique_df, dupes_df) by checking against customers and leads.

    dupes_df has columns: row, name, reason.
    """
    dupe_cols = ["row", "name", "reason"]
    if new_df is None or new_df.empty:
        empty = new_df if new_df is not None else pd.DataFrame()
        return empty, pd.DataFrame(columns=dupe_cols)

    unique_idx = []
    dupes = []
    for idx, row in new_df.iterrows():
        name = row.get(name_col, "")
        lat = row.get(lat_col, 0)
        lon = row.get(lon_col, 0)

        is_dup, info = check_duplicate(name, lat, lon, existing_customers_df)
        if is_dup:
            dupes.append({"row": idx + 1, "name": name, "reason": info})
            continue

        is_dup, info = check_duplicate(name, lat, lon, existing_leads_df)
        if is_dup:
            dupes.append({"row": idx + 1, "name": name, "reason": f"Already in leads: {info}"})
            continue

        unique_idx.append(idx)

    return new_df.loc[unique_idx], pd.DataFrame(dupes, columns=dupe_cols)
