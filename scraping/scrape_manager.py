"""Scrape manager - orchestrates the full route optimization pipeline.

Pipeline: analyze routes -> generate search points -> scrape sources ->
          filter cuisine -> deduplicate -> import leads -> score.
"""

import logging
from datetime import datetime

from thefuzz import fuzz

import config
from database.models import (
    get_all_leads, get_all_customers, insert_lead,
    get_route, get_all_routes,
)
from scraping.route_analyzer import (
    find_route_gaps, generate_search_points, deduplicate_search_points,
)
from scraping.cuisine_filter import (
    classify_cuisine, get_keywords_for_categories, get_yelp_categories,
)
from scraping.sources import search_all_sources

logger = logging.getLogger(__name__)


def _is_duplicate_of_existing(name, lat, lon, existing_df):
    """Check if a restaurant is a duplicate of an existing customer or lead.

    Uses distance threshold + fuzzy name matching (same logic as upload page).
    """
    if existing_df.empty:
        return False

    from scoring.proximity import _haversine_miles

    for _, row in existing_df.iterrows():
        dist = _haversine_miles(lat, lon, row["latitude"], row["longitude"])
        if dist <= config.DUPLICATE_DISTANCE_THRESHOLD_MI:
            name_score = fuzz.token_sort_ratio(
                (name or "").lower(), (row.get("name", "") or "").lower()
            )
            if name_score >= config.DUPLICATE_NAME_SIMILARITY_THRESHOLD:
                return True
    return False


def _deduplicate_raw_results(raw_leads):
    """Remove duplicate restaurants from raw scraping results.

    Same restaurant may appear from multiple sources.
    """
    seen = []
    unique = []

    from scoring.proximity import _haversine_miles

    for lead in raw_leads:
        is_dup = False
        for seen_lead in seen:
            dist = _haversine_miles(
                lead["latitude"], lead["longitude"],
                seen_lead["latitude"], seen_lead["longitude"],
            )
            if dist <= config.DUPLICATE_DISTANCE_THRESHOLD_MI:
                name_score = fuzz.token_sort_ratio(
                    lead["name"].lower(), seen_lead["name"].lower()
                )
                if name_score >= config.DUPLICATE_NAME_SIMILARITY_THRESHOLD:
                    is_dup = True
                    break
        if not is_dup:
            unique.append(lead)
            seen.append(lead)

    return unique


def run_route_optimization(route_ids, enabled_sources=None,
                           selected_cuisines=None, gap_threshold_miles=None,
                           search_radius_miles=None, google_api_key=None,
                           yelp_api_key=None, progress_callback=None):
    """Run the full route optimization scraping pipeline.

    Args:
        route_ids: List of route IDs to optimize.
        enabled_sources: List of source names (e.g., ["OpenStreetMap", "Yelp"]).
        selected_cuisines: List of cuisine category names (e.g., ["Chinese", "Japanese"]).
        gap_threshold_miles: Minimum gap distance to search.
        search_radius_miles: Radius around each search point.
        google_api_key: Google Places API key override.
        yelp_api_key: Yelp API key override.
        progress_callback: Optional callable(percent, message) for progress updates.

    Returns:
        Dict with summary stats and list of created leads.
    """
    if gap_threshold_miles is None:
        gap_threshold_miles = config.ROUTE_GAP_THRESHOLD_MILES
    if search_radius_miles is None:
        search_radius_miles = config.ROUTE_SEARCH_RADIUS_MILES
    if enabled_sources is None:
        enabled_sources = ["OpenStreetMap"]

    def progress(pct, msg):
        if progress_callback:
            progress_callback(pct, msg)

    started_at = datetime.now()

    # Build keyword lists from selected cuisines
    cuisine_keywords = get_keywords_for_categories(selected_cuisines)
    yelp_cats = get_yelp_categories(selected_cuisines)

    progress(5, "Analyzing routes for gaps...")

    # Step 1: Find gaps across all selected routes
    all_gaps = []
    all_search_points = []
    route_gap_counts = {}

    for rid in route_ids:
        gaps = find_route_gaps(rid, gap_threshold_miles)
        all_gaps.extend(gaps)
        route_gap_counts[rid] = len(gaps)

        points = generate_search_points(gaps)
        all_search_points.extend(points)

    # Deduplicate search points across routes
    all_search_points = deduplicate_search_points(all_search_points)

    if not all_search_points:
        progress(100, "No gaps found matching threshold.")
        return {
            "started_at": started_at,
            "completed_at": datetime.now(),
            "route_ids": route_ids,
            "gaps_found": 0,
            "search_points": 0,
            "results_found": 0,
            "cuisine_matched": 0,
            "duplicates_skipped": 0,
            "leads_created": 0,
            "new_leads": [],
        }

    progress(15, f"Found {len(all_gaps)} gaps, {len(all_search_points)} search points.")

    # Step 2: Load existing data for deduplication
    progress(20, "Loading existing customers and leads for dedup...")
    existing_customers = get_all_customers()
    existing_leads = get_all_leads()

    # Step 3: Scrape each search point
    all_raw_results = []
    total_points = len(all_search_points)

    for i, (lat, lon) in enumerate(all_search_points):
        pct = 25 + int(50 * (i / total_points))
        progress(pct, f"Searching point {i+1}/{total_points}...")

        results = search_all_sources(
            lat, lon, search_radius_miles, cuisine_keywords,
            yelp_categories=yelp_cats, enabled_sources=enabled_sources,
            google_api_key=google_api_key, yelp_api_key=yelp_api_key,
        )
        all_raw_results.extend(results)

    progress(75, f"Found {len(all_raw_results)} raw results. Filtering...")

    # Step 4: Deduplicate raw results across sources
    unique_results = _deduplicate_raw_results(all_raw_results)

    # Step 5: Apply cuisine filter
    cuisine_matched = []
    for lead in unique_results:
        classification = classify_cuisine(
            lead["name"], lead["cuisine_tags"], lead["categories"],
            keywords=cuisine_keywords,
        )
        if classification["match"]:
            lead["cuisine_confidence"] = classification["confidence"]
            lead["cuisine_matched_keywords"] = classification["matched_keywords"]
            cuisine_matched.append(lead)

    progress(80, f"{len(cuisine_matched)} matched cuisine filter. Checking duplicates...")

    # Step 6: Deduplicate against existing customers and leads
    new_leads = []
    duplicates_skipped = 0

    for lead in cuisine_matched:
        # Check against existing customers
        if _is_duplicate_of_existing(lead["name"], lead["latitude"], lead["longitude"],
                                     existing_customers):
            duplicates_skipped += 1
            continue

        # Check against existing leads
        if _is_duplicate_of_existing(lead["name"], lead["latitude"], lead["longitude"],
                                     existing_leads):
            duplicates_skipped += 1
            continue

        new_leads.append(lead)

    progress(85, f"{len(new_leads)} new leads after dedup. Importing...")

    # Step 7: Insert new leads into database
    created_lead_ids = []
    for lead in new_leads:
        lead_id = insert_lead(
            name=lead["name"],
            address=lead["address"],
            city=lead["city"],
            state=lead["state"],
            zip_code=lead["zip_code"],
            latitude=lead["latitude"],
            longitude=lead["longitude"],
            business_type="Restaurant",
            segment="Full-Service Restaurant",
            estimated_weekly_revenue=0,
            phone=lead["phone"],
            website=lead["website"],
            source=f"Route Optimizer - {lead['source']}",
        )
        created_lead_ids.append(lead_id)

    progress(90, f"Imported {len(created_lead_ids)} leads. Scoring...")

    # Step 8: Re-score all leads
    if created_lead_ids:
        from scoring.engine import score_all_leads
        score_all_leads()

    progress(100, "Route optimization complete!")

    # Step 9: Log scrape run
    completed_at = datetime.now()
    from database.models import insert_scrape_history
    for rid in route_ids:
        insert_scrape_history(
            route_id=rid,
            source=", ".join(enabled_sources),
            search_points_count=len(all_search_points),
            results_found=len(all_raw_results),
            leads_created=len(created_lead_ids),
            duplicates_skipped=duplicates_skipped,
            cuisine_filtered=len(all_raw_results) - len(cuisine_matched),
            completed_at=completed_at,
            status="completed",
        )

    return {
        "started_at": started_at,
        "completed_at": completed_at,
        "route_ids": route_ids,
        "gaps_found": len(all_gaps),
        "search_points": len(all_search_points),
        "results_found": len(all_raw_results),
        "cuisine_matched": len(cuisine_matched),
        "duplicates_skipped": duplicates_skipped,
        "leads_created": len(created_lead_ids),
        "new_lead_ids": created_lead_ids,
        "new_leads": new_leads,
    }
