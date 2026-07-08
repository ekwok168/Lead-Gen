"""Segment scoring - measures how well a lead matches core customer segments."""

import pandas as pd

import config


def _normalize(value):
    """Return a lowercase string, treating None/NaN as empty."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).lower()


def score_segment(lead_business_type, lead_segment, core_segments_df):
    """Score a lead's segment match against core segments.

    Args:
        lead_business_type: The lead's business type (e.g., "Restaurant")
        lead_segment: The lead's segment (e.g., "Full-Service Restaurant")
        core_segments_df: DataFrame of core segments from the database

    Returns:
        dict with:
        - segment_score: 0-100
        - is_core_segment: bool
        - matched_segment: name of matched segment or None
    """
    if core_segments_df.empty:
        return {
            "segment_score": config.SEGMENT_NO_MATCH,
            "is_core_segment": False,
            "matched_segment": None,
        }

    # Check for exact segment match
    exact = core_segments_df[
        core_segments_df["segment_name"].str.lower() == _normalize(lead_segment)
    ]
    if not exact.empty:
        return {
            "segment_score": config.SEGMENT_EXACT_MATCH,
            "is_core_segment": True,
            "matched_segment": exact.iloc[0]["segment_name"],
        }

    # Check for business type match (segment differs but type matches)
    type_match = core_segments_df[
        core_segments_df["business_type"].str.lower() == _normalize(lead_business_type)
    ]
    if not type_match.empty:
        return {
            "segment_score": config.SEGMENT_TYPE_MATCH,
            "is_core_segment": False,
            "matched_segment": type_match.iloc[0]["segment_name"],
        }

    # Check for adjacent business type
    adjacent_types = config.ADJACENT_TYPES.get(lead_business_type, [])
    for adj_type in adjacent_types:
        adj_match = core_segments_df[
            core_segments_df["business_type"].str.lower() == adj_type.lower()
        ]
        if not adj_match.empty:
            return {
                "segment_score": config.SEGMENT_ADJACENT_MATCH,
                "is_core_segment": False,
                "matched_segment": adj_match.iloc[0]["segment_name"],
            }

    return {
        "segment_score": config.SEGMENT_NO_MATCH,
        "is_core_segment": False,
        "matched_segment": None,
    }


def check_core_segment_revenue(lead_segment, estimated_revenue, core_segments_df):
    """Check if a lead meets the revenue threshold for its core segment.

    Only called when segment already matches. Returns True if revenue
    meets or exceeds the minimum for that segment.
    """
    lead_segment = _normalize(lead_segment)
    if core_segments_df.empty or not lead_segment:
        return False

    match = core_segments_df[
        core_segments_df["segment_name"].str.lower() == lead_segment
    ]
    if match.empty:
        return False

    min_rev = match.iloc[0]["min_estimated_revenue"]
    return (estimated_revenue or 0) >= min_rev
