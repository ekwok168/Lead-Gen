"""Lead scoring engine - orchestrates all scoring components."""

import numpy as np
import pandas as pd

import config
from database.models import (
    get_all_leads, get_all_customers, get_all_stops, get_core_segments,
    get_stops_by_route, insert_lead_score, clear_scores,
)
from scoring.proximity import compute_nearest_stops, compute_nearest_customers, find_insertion_point
from scoring.segment import score_segment, check_core_segment_revenue
from scoring.density import compute_density_scores


def compute_grade(total_score):
    """Convert numeric score to letter grade."""
    for grade, threshold in config.GRADE_THRESHOLDS.items():
        if total_score >= threshold:
            return grade
    return "F"


def score_revenue(estimated_revenues):
    """Score leads by revenue percentile rank.

    Returns array of scores 0-100.
    """
    if len(estimated_revenues) == 0:
        return np.array([])

    revenues = np.array(estimated_revenues, dtype=np.float64)
    revenues = np.nan_to_num(revenues, nan=0.0)

    if revenues.max() == revenues.min():
        return np.full(len(revenues), 50.0)

    # Percentile rank
    ranks = np.zeros(len(revenues))
    for i, rev in enumerate(revenues):
        ranks[i] = np.sum(revenues <= rev) / len(revenues) * 100

    return np.round(ranks, 1)


def score_all_leads(weights=None, progress_callback=None):
    """Score all leads in the database.

    Args:
        weights: dict with keys proximity, segment, density, revenue (must sum to 1.0)
        progress_callback: optional callable(percent, message) for progress updates

    Returns:
        DataFrame of leads with all scores
    """
    if weights is None:
        weights = config.DEFAULT_WEIGHTS

    def progress(pct, msg):
        if progress_callback:
            progress_callback(pct, msg)

    progress(5, "Loading data...")

    leads_df = get_all_leads()
    if leads_df.empty:
        return pd.DataFrame()

    customers_df = get_all_customers()
    stops_df = get_all_stops()
    core_segments_df = get_core_segments()

    progress(10, "Clearing old scores...")
    clear_scores()

    # Prepare coordinate arrays
    lead_coords = leads_df[["latitude", "longitude"]].values.tolist()

    progress(20, "Computing proximity to route stops...")

    # --- Proximity scoring ---
    if not stops_df.empty:
        stop_coords = stops_df[["latitude", "longitude"]].values.tolist()
        stop_ids = stops_df["id"].values
        stop_route_ids = stops_df["route_id"].values
        stop_names = stops_df["stop_name"].fillna("Unknown Stop").values

        proximity_results = compute_nearest_stops(
            lead_coords, stop_coords, stop_ids, stop_route_ids, stop_names
        )
    else:
        proximity_results = [
            {"nearest_stop_id": None, "nearest_route_id": None,
             "nearest_stop_name": None, "nearest_route_stop_distance_mi": 999,
             "proximity_score": config.PROXIMITY_DEFAULT_SCORE}
            for _ in range(len(leads_df))
        ]

    progress(35, "Computing distance to nearest customer...")

    # --- Nearest customer distance ---
    if not customers_df.empty:
        cust_coords = customers_df[["latitude", "longitude"]].values.tolist()
        nearest_cust_distances = compute_nearest_customers(lead_coords, cust_coords)
    else:
        nearest_cust_distances = np.full(len(leads_df), 999.0)

    progress(50, "Computing route density scores...")

    # --- Density scoring ---
    if not customers_df.empty:
        density_results = compute_density_scores(lead_coords, cust_coords)
    else:
        density_results = [{"nearby_customer_count": 0, "density_score": config.DENSITY_DEFAULT_SCORE}
                          for _ in range(len(leads_df))]

    progress(65, "Scoring segment matches...")

    # --- Segment scoring ---
    segment_results = []
    for _, lead in leads_df.iterrows():
        seg_result = score_segment(lead["business_type"], lead["segment"], core_segments_df)

        # Check revenue threshold for core segment
        if seg_result["is_core_segment"]:
            meets_revenue = check_core_segment_revenue(
                lead["segment"], lead.get("estimated_weekly_revenue", 0), core_segments_df
            )
            seg_result["is_core_segment"] = meets_revenue

        segment_results.append(seg_result)

    progress(75, "Computing revenue scores...")

    # --- Revenue scoring ---
    revenue_scores = score_revenue(leads_df["estimated_weekly_revenue"].values)

    progress(85, "Computing composite scores and finding insertion points...")

    # --- Composite scoring and insertion points ---
    for i, (_, lead) in enumerate(leads_df.iterrows()):
        prox = proximity_results[i]
        seg = segment_results[i]
        dens = density_results[i]
        rev_score = revenue_scores[i]

        total = (
            weights["proximity"] * prox["proximity_score"]
            + weights["segment"] * seg["segment_score"]
            + weights["density"] * dens["density_score"]
            + weights["revenue"] * rev_score
        )
        total = round(total, 1)
        grade = compute_grade(total)

        # Find insertion point for the nearest route
        insertion_seq = None
        route_id = prox["nearest_route_id"]
        if route_id is not None:
            route_stops = get_stops_by_route(route_id)
            if not route_stops.empty:
                rs_coords = route_stops[["latitude", "longitude"]].values.tolist()
                rs_seqs = route_stops["stop_sequence"].values.tolist()
                insertion_seq = find_insertion_point(
                    lead["latitude"], lead["longitude"], rs_coords, rs_seqs
                )

        # Get DC ID from route
        nearest_dc_id = None
        if route_id is not None and not stops_df.empty:
            dc_rows = stops_df[stops_df["route_id"] == route_id]
            if not dc_rows.empty and "dc_id" in dc_rows.columns:
                nearest_dc_id = int(dc_rows.iloc[0]["dc_id"])

        insert_lead_score(
            lead_id=int(lead["id"]),
            nearest_route_id=int(route_id) if route_id is not None else None,
            nearest_dc_id=nearest_dc_id,
            nearest_stop_id=int(prox["nearest_stop_id"]) if prox["nearest_stop_id"] is not None else None,
            proximity_score=round(prox["proximity_score"], 1),
            segment_score=round(seg["segment_score"], 1),
            density_score=round(dens["density_score"], 1),
            revenue_score=round(rev_score, 1),
            total_score=total,
            score_grade=grade,
            is_core_segment=seg["is_core_segment"],
            nearest_customer_distance_mi=round(nearest_cust_distances[i], 3),
            nearest_route_stop_distance_mi=round(prox["nearest_route_stop_distance_mi"], 3),
            suggested_insertion_sequence=insertion_seq,
        )

    progress(100, "Scoring complete!")

    # Return scored leads
    from database.models import get_leads_with_scores
    return get_leads_with_scores()


def generate_why_text(row):
    """Generate a plain-English explanation of why a lead scored the way it did.

    Args:
        row: a dict or Series with lead score fields

    Returns:
        str explanation
    """
    parts = []

    # Proximity
    dist = row.get("nearest_route_stop_distance_mi")
    stop_name = row.get("nearest_stop_name", "a route stop")
    route_code = row.get("nearest_route_code", "a route")
    if dist is not None:
        if dist < 0.5:
            parts.append(f"Very close ({dist:.1f} mi) to {stop_name} on {route_code}")
        elif dist < 2:
            parts.append(f"Near ({dist:.1f} mi) to {stop_name} on {route_code}")
        elif dist < 5:
            parts.append(f"Moderate distance ({dist:.1f} mi) from nearest stop on {route_code}")
        else:
            parts.append(f"Far ({dist:.1f} mi) from nearest delivery stop")

    # Segment
    is_core = row.get("is_core_segment")
    segment = row.get("segment", "")
    if is_core:
        parts.append(f"Core segment match: {segment}")
    elif row.get("segment_score", 0) >= 60:
        parts.append(f"Business type aligns with core segments")
    elif row.get("segment_score", 0) >= 40:
        parts.append(f"Related business type")

    # Density
    density = row.get("density_score", 0)
    if density >= 85:
        parts.append("High delivery density area - many existing customers nearby")
    elif density >= 50:
        parts.append("Moderate delivery activity in this area")
    elif density >= 30:
        parts.append("Low delivery density - few existing customers nearby")

    # Revenue
    rev = row.get("estimated_weekly_revenue", 0)
    if rev and rev > 0:
        parts.append(f"Estimated ${rev:,.0f}/week revenue potential")

    # Overall grade
    grade = row.get("score_grade", "F")
    total = row.get("total_score", 0)
    grade_text = {
        "A": "Hot lead - strongly recommended for outreach",
        "B": "Strong lead - good fit for your routes",
        "C": "Moderate lead - worth considering",
        "D": "Lower priority - may require more effort",
        "F": "Poor fit at this time",
    }
    parts.append(grade_text.get(grade, ""))

    return ". ".join(p for p in parts if p) + "."
