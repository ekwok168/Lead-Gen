"""Distribution Center level report generation."""

import pandas as pd

from database.models import (
    get_dc, get_routes_by_dc, get_customers_by_dc,
    get_leads_with_scores,
)


def generate_dc_report(dc_id):
    """Generate a comprehensive DC-level report.

    Returns:
        dict with:
        - summary: overall DC stats
        - route_comparison: per-route breakdown
        - top_leads: top 20 leads ranked by score
        - segment_analysis: segment distribution comparison
        - grade_distribution: lead count by grade
    """
    dc = get_dc(dc_id)
    if not dc:
        return None

    routes = get_routes_by_dc(dc_id)
    customers = get_customers_by_dc(dc_id)
    all_scored = get_leads_with_scores()

    # Filter leads to this DC
    dc_leads = all_scored[all_scored["nearest_dc_id"] == dc_id] if not all_scored.empty else pd.DataFrame()

    # Summary
    summary = {
        "dc_name": dc["name"],
        "dc_code": dc["code"],
        "dc_address": f"{dc.get('address', '')}, {dc.get('city', '')}, {dc.get('state', '')} {dc.get('zip_code', '')}",
        "total_routes": len(routes),
        "total_customers": len(customers),
        "total_leads": len(dc_leads),
        "total_revenue": customers["weekly_revenue"].sum() if not customers.empty else 0,
    }

    # Grade distribution
    grade_dist = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
    if not dc_leads.empty and "score_grade" in dc_leads.columns:
        counts = dc_leads["score_grade"].value_counts().to_dict()
        grade_dist.update(counts)
    summary["grade_distribution"] = grade_dist
    if not dc_leads.empty and "is_core_segment" in dc_leads.columns:
        summary["core_segment_leads"] = int(dc_leads["is_core_segment"].astype(int).sum())
    else:
        summary["core_segment_leads"] = 0

    # Estimated revenue opportunity (A+B leads)
    if not dc_leads.empty and "score_grade" in dc_leads.columns:
        ab_leads = dc_leads[dc_leads["score_grade"].isin(["A", "B"])]
        summary["estimated_revenue_opportunity"] = ab_leads["estimated_weekly_revenue"].sum()
    else:
        summary["estimated_revenue_opportunity"] = 0

    # Route comparison
    route_comparison = []
    for _, route in routes.iterrows():
        route_customers = customers[customers["route_id"] == route["id"]] if not customers.empty else pd.DataFrame()
        route_leads = dc_leads[dc_leads["nearest_route_id"] == route["id"]] if not dc_leads.empty else pd.DataFrame()

        route_info = {
            "route_code": route["route_code"],
            "route_name": route["route_name"],
            "day_of_week": route["day_of_week"],
            "customer_count": len(route_customers),
            "customer_revenue": route_customers["weekly_revenue"].sum() if not route_customers.empty else 0,
            "lead_count": len(route_leads),
            "avg_lead_score": round(route_leads["total_score"].mean(), 1) if not route_leads.empty and "total_score" in route_leads.columns else 0,
            "a_leads": int((route_leads["score_grade"] == "A").sum()) if not route_leads.empty and "score_grade" in route_leads.columns else 0,
            "b_leads": int((route_leads["score_grade"] == "B").sum()) if not route_leads.empty and "score_grade" in route_leads.columns else 0,
            "lead_revenue_opportunity": route_leads["estimated_weekly_revenue"].sum() if not route_leads.empty else 0,
        }
        route_comparison.append(route_info)

    route_comparison_df = pd.DataFrame(route_comparison)

    # Top 20 leads
    top_leads = pd.DataFrame()
    if not dc_leads.empty and "total_score" in dc_leads.columns:
        top_leads = dc_leads.nlargest(20, "total_score")[
            ["name", "business_type", "segment", "total_score", "score_grade",
             "is_core_segment", "proximity_score", "segment_score", "density_score",
             "revenue_score", "nearest_route_stop_distance_mi", "nearest_route_code",
             "nearest_stop_name", "estimated_weekly_revenue"]
        ].copy()

    # Segment analysis
    segment_analysis = _build_segment_analysis(customers, dc_leads)

    return {
        "summary": summary,
        "route_comparison": route_comparison_df,
        "top_leads": top_leads,
        "segment_analysis": segment_analysis,
    }


def _build_segment_analysis(customers, leads):
    """Compare segment distribution between existing customers and leads."""
    analysis = {}

    if not customers.empty:
        cust_segments = customers["segment"].value_counts().to_dict()
    else:
        cust_segments = {}

    if not leads.empty:
        lead_segments = leads["segment"].value_counts().to_dict()
    else:
        lead_segments = {}

    all_segments = set(list(cust_segments.keys()) + list(lead_segments.keys()))

    rows = []
    for seg in sorted(all_segments):
        if seg is None or (isinstance(seg, float) and pd.isna(seg)):
            continue
        rows.append({
            "segment": seg,
            "existing_customers": cust_segments.get(seg, 0),
            "available_leads": lead_segments.get(seg, 0),
            "growth_opportunity": lead_segments.get(seg, 0) - cust_segments.get(seg, 0),
        })

    return pd.DataFrame(rows) if rows else pd.DataFrame()
