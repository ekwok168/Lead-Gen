"""Route level report generation."""

import pandas as pd

from database.models import (
    get_route, get_customers_by_route, get_stops_by_route,
    get_leads_with_scores, get_dc,
)
from scoring.engine import generate_why_text


def generate_route_report(route_id):
    """Generate a comprehensive route-level report.

    Returns:
        dict with:
        - summary: route overview
        - customers: ordered customer list
        - stops: route stops in sequence
        - leads: nearby leads with scores and explanations
        - dc_info: distribution center details
    """
    route = get_route(route_id)
    if not route:
        return None

    customers = get_customers_by_route(route_id)
    stops = get_stops_by_route(route_id)
    dc = get_dc(route["dc_id"])
    all_scored = get_leads_with_scores()

    # Filter leads to this route
    route_leads = pd.DataFrame()
    if not all_scored.empty and "nearest_route_id" in all_scored.columns:
        route_leads = all_scored[all_scored["nearest_route_id"] == route_id].copy()
        if not route_leads.empty and "total_score" in route_leads.columns:
            route_leads = route_leads.sort_values("total_score", ascending=False)

    # Summary
    summary = {
        "route_code": route["route_code"],
        "route_name": route["route_name"],
        "dc_name": route["dc_name"],
        "day_of_week": route["day_of_week"],
        "driver_name": route.get("driver_name", ""),
        "customer_count": len(customers),
        "stop_count": len(stops),
        "total_weekly_revenue": customers["weekly_revenue"].sum() if not customers.empty else 0,
        "lead_count": len(route_leads),
    }

    # Grade stats
    if not route_leads.empty and "score_grade" in route_leads.columns:
        summary["a_leads"] = int((route_leads["score_grade"] == "A").sum())
        summary["b_leads"] = int((route_leads["score_grade"] == "B").sum())
        summary["c_leads"] = int((route_leads["score_grade"] == "C").sum())
        summary["avg_lead_score"] = round(route_leads["total_score"].mean(), 1)
        summary["lead_revenue_opportunity"] = route_leads["estimated_weekly_revenue"].sum()
    else:
        summary.update({"a_leads": 0, "b_leads": 0, "c_leads": 0,
                        "avg_lead_score": 0, "lead_revenue_opportunity": 0})

    # Add "Why This Lead?" explanation to each lead
    if not route_leads.empty:
        route_leads["why_this_lead"] = route_leads.apply(generate_why_text, axis=1)

        # Add nearest stop info text
        route_leads["nearest_stop_info"] = route_leads.apply(
            lambda r: _format_stop_info(r), axis=1
        )

    # Customer list with stop sequence
    customer_list = pd.DataFrame()
    if not customers.empty:
        customer_list = customers[
            ["name", "address", "business_type", "segment", "weekly_revenue", "stop_sequence"]
        ].copy()
        customer_list = customer_list.sort_values("stop_sequence")

    return {
        "summary": summary,
        "customers": customer_list,
        "stops": stops,
        "leads": route_leads,
        "dc_info": dc,
    }


def _format_stop_info(row):
    """Format the nearest stop distance into a readable string."""
    dist = row.get("nearest_route_stop_distance_mi")
    stop_name = row.get("nearest_stop_name", "")
    insertion = row.get("suggested_insertion_sequence")

    if dist is None:
        return "No route data available"

    parts = [f"{dist:.1f} mi from {stop_name}" if stop_name else f"{dist:.1f} mi from nearest stop"]

    if insertion:
        parts.append(f"Suggested insertion: after stop #{insertion}")

    return " | ".join(parts)
