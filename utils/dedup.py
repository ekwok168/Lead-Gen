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


def check_duplicate(name, lat, lon, existing_df, name_threshold=None, distance_threshold_mi=None,
                    name_match_radius_mi=None):
    """Check if a record duplicates one in existing_df.

    A record is a duplicate when it sits within distance_threshold_mi of an
    existing record (same location), or when its name matches (exact or fuzzy)
    an existing record within name_match_radius_mi. Name matching alone never
    flags records that are far apart — chains legitimately repeat names across
    locations. Records missing coordinates on either side fall back to
    name-only matching. Returns (is_duplicate, info_string).
    """
    if name_threshold is None:
        name_threshold = config.DUPLICATE_NAME_SIMILARITY_THRESHOLD
    if distance_threshold_mi is None:
        distance_threshold_mi = config.DUPLICATE_DISTANCE_THRESHOLD_MI
    if name_match_radius_mi is None:
        name_match_radius_mi = config.DUPLICATE_NAME_MATCH_RADIUS_MI

    if existing_df is None or existing_df.empty:
        return False, ""

    lat = 0.0 if lat is None or pd.isna(lat) else float(lat)
    lon = 0.0 if lon is None or pd.isna(lon) else float(lon)
    has_coords = not (abs(lat) < 1e-6 and abs(lon) < 1e-6)

    dists = None
    valid_mask = np.zeros(len(existing_df), dtype=bool)
    if "latitude" in existing_df.columns and "longitude" in existing_df.columns:
        ex_lat = pd.to_numeric(existing_df["latitude"], errors="coerce").to_numpy(dtype=np.float64)
        ex_lon = pd.to_numeric(existing_df["longitude"], errors="coerce").to_numpy(dtype=np.float64)
        valid_mask = ~(np.isnan(ex_lat) | np.isnan(ex_lon)) & ~(
            (np.abs(ex_lat) < 1e-6) & (np.abs(ex_lon) < 1e-6)
        )
        if has_coords and valid_mask.any():
            dists = np.full(len(existing_df), np.inf)
            dists[valid_mask] = haversine_miles(lat, lon, ex_lat[valid_mask], ex_lon[valid_mask])

            close = np.where(dists <= distance_threshold_mi)[0]
            if len(close) > 0:
                match = existing_df.iloc[close[0]]
                return True, f"Within {dists[close[0]]:.2f} mi of existing: '{match.get('name', 'Unknown')}'"

    name_lower = str(name).lower().strip() if name is not None and not pd.isna(name) else ""
    if name_lower and "name" in existing_df.columns:
        # Name matches only count near the candidate; records without usable
        # coordinates on either side are compared by name alone.
        if not has_coords:
            candidate_mask = np.ones(len(existing_df), dtype=bool)
        elif dists is not None:
            candidate_mask = (dists <= name_match_radius_mi) | ~valid_mask
        else:
            candidate_mask = ~valid_mask

        if candidate_mask.any():
            subset = existing_df.iloc[np.where(candidate_mask)[0]]
            subset_names = subset["name"].fillna("").astype(str).str.lower().str.strip()

            exact = subset[subset_names == name_lower]
            if not exact.empty:
                match = exact.iloc[0]
                return True, f"Exact name match: '{match['name']}'{_route_info(match)}"

            result = process.extractOne(
                name_lower,
                subset_names.tolist(),
                scorer=fuzz.ratio,
                score_cutoff=name_threshold,
            )
            if result is not None:
                match = subset.iloc[result[2]]
                return True, f"Similar name: '{match['name']}'{_route_info(match)}"

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
