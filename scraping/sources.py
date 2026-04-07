"""Data source clients for restaurant discovery.

Three-tier strategy:
  1. Google Places API (most accurate, paid)
  2. Yelp Fusion API (good data, free tier)
  3. OpenStreetMap Overpass API (free, no key needed)
"""

import logging
import time

import requests

import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Normalized result format
# ---------------------------------------------------------------------------

def _make_raw_lead(name, address="", city="", state="", zip_code="",
                   latitude=0.0, longitude=0.0, phone="", website="",
                   source="", cuisine_tags=None, rating=None, categories=None):
    """Create a normalized raw lead dict from any source."""
    return {
        "name": name or "Unknown",
        "address": address or "",
        "city": city or "",
        "state": state or "",
        "zip_code": zip_code or "",
        "latitude": float(latitude),
        "longitude": float(longitude),
        "phone": phone or "",
        "website": website or "",
        "source": source,
        "cuisine_tags": cuisine_tags or [],
        "categories": categories or [],
        "rating": rating,
    }


# ---------------------------------------------------------------------------
# Google Places API (Nearby Search)
# ---------------------------------------------------------------------------

def search_google_places(lat, lon, radius_m, cuisine_keywords, api_key=None):
    """Search Google Places API for restaurants near a point.

    Args:
        lat, lon: Search center coordinates.
        radius_m: Search radius in meters (max 50000).
        cuisine_keywords: List of cuisine keywords to include in the search.
        api_key: Google Places API key (falls back to config).

    Returns:
        List of raw lead dicts.
    """
    api_key = api_key or config.GOOGLE_PLACES_API_KEY
    if not api_key:
        logger.warning("Google Places API key not configured, skipping")
        return []

    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    keyword = "|".join(cuisine_keywords[:5])  # API works best with fewer keywords

    params = {
        "location": f"{lat},{lon}",
        "radius": min(int(radius_m), 50000),
        "type": "restaurant",
        "keyword": keyword,
        "key": api_key,
    }

    results = []
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") not in ("OK", "ZERO_RESULTS"):
            logger.warning("Google Places API error: %s", data.get("status"))
            return []

        for place in data.get("results", []):
            loc = place.get("geometry", {}).get("location", {})
            addr_parts = place.get("vicinity", "").split(", ")

            results.append(_make_raw_lead(
                name=place.get("name"),
                address=addr_parts[0] if addr_parts else "",
                city=addr_parts[-1] if len(addr_parts) > 1 else "",
                latitude=loc.get("lat", 0),
                longitude=loc.get("lng", 0),
                source="Google Places",
                cuisine_tags=place.get("types", []),
                rating=place.get("rating"),
            ))

        time.sleep(config.GOOGLE_PLACES_RATE_LIMIT)

    except requests.RequestException as e:
        logger.error("Google Places request failed: %s", e)

    return results


# ---------------------------------------------------------------------------
# Yelp Fusion API
# ---------------------------------------------------------------------------

def search_yelp(lat, lon, radius_m, yelp_categories, api_key=None):
    """Search Yelp Fusion API for restaurants near a point.

    Args:
        lat, lon: Search center coordinates.
        radius_m: Search radius in meters (max 40000).
        yelp_categories: Comma-separated Yelp category codes.
        api_key: Yelp API key (falls back to config).

    Returns:
        List of raw lead dicts.
    """
    api_key = api_key or config.YELP_API_KEY
    if not api_key:
        logger.warning("Yelp API key not configured, skipping")
        return []

    url = "https://api.yelp.com/v3/businesses/search"
    headers = {"Authorization": f"Bearer {api_key}"}

    params = {
        "latitude": lat,
        "longitude": lon,
        "radius": min(int(radius_m), 40000),
        "categories": yelp_categories,
        "limit": 50,
        "sort_by": "distance",
    }

    results = []
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        for biz in data.get("businesses", []):
            loc = biz.get("coordinates", {})
            addr = biz.get("location", {})
            cat_titles = [c.get("title", "") for c in biz.get("categories", [])]
            cat_aliases = [c.get("alias", "") for c in biz.get("categories", [])]

            results.append(_make_raw_lead(
                name=biz.get("name"),
                address=addr.get("address1", ""),
                city=addr.get("city", ""),
                state=addr.get("state", ""),
                zip_code=addr.get("zip_code", ""),
                latitude=loc.get("latitude", 0),
                longitude=loc.get("longitude", 0),
                phone=biz.get("display_phone", ""),
                website=biz.get("url", ""),
                source="Yelp",
                cuisine_tags=cat_aliases,
                categories=cat_titles,
                rating=biz.get("rating"),
            ))

        time.sleep(config.YELP_RATE_LIMIT)

    except requests.RequestException as e:
        logger.error("Yelp request failed: %s", e)

    return results


# ---------------------------------------------------------------------------
# OpenStreetMap Overpass API (free, no key)
# ---------------------------------------------------------------------------

def _build_overpass_query(bbox, cuisine_keywords):
    """Build an Overpass QL query for restaurants with matching cuisine tags.

    Args:
        bbox: (south, west, north, east) bounding box.
        cuisine_keywords: List of cuisine keywords.

    Returns:
        Overpass QL query string.
    """
    s, w, n, e = bbox
    cuisine_regex = "|".join(cuisine_keywords)

    return f"""
    [out:json][timeout:30];
    (
      node["amenity"="restaurant"]["cuisine"~"{cuisine_regex}",i]({s},{w},{n},{e});
      way["amenity"="restaurant"]["cuisine"~"{cuisine_regex}",i]({s},{w},{n},{e});
      node["amenity"="restaurant"]["name"~"{cuisine_regex}",i]({s},{w},{n},{e});
    );
    out center body;
    """


def _bbox_from_point(lat, lon, radius_miles):
    """Compute a bounding box around a point.

    Returns (south, west, north, east).
    """
    # Approximate degrees per mile
    lat_deg_per_mi = 1 / 69.0
    lon_deg_per_mi = 1 / (69.0 * max(0.01, abs(__import__("math").cos(__import__("math").radians(lat)))))

    d_lat = radius_miles * lat_deg_per_mi
    d_lon = radius_miles * lon_deg_per_mi

    return (
        round(lat - d_lat, 6),
        round(lon - d_lon, 6),
        round(lat + d_lat, 6),
        round(lon + d_lon, 6),
    )


def search_overpass(lat, lon, radius_miles, cuisine_keywords):
    """Search OpenStreetMap via Overpass API for restaurants near a point.

    Args:
        lat, lon: Search center coordinates.
        radius_miles: Search radius in miles.
        cuisine_keywords: List of cuisine keywords for filtering.

    Returns:
        List of raw lead dicts.
    """
    bbox = _bbox_from_point(lat, lon, radius_miles)
    query = _build_overpass_query(bbox, cuisine_keywords)

    url = "https://overpass-api.de/api/interpreter"

    results = []
    try:
        resp = requests.post(url, data={"data": query}, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        for element in data.get("elements", []):
            tags = element.get("tags", {})

            # Get coordinates (center for ways)
            e_lat = element.get("lat") or element.get("center", {}).get("lat")
            e_lon = element.get("lon") or element.get("center", {}).get("lon")

            if not e_lat or not e_lon:
                continue

            name = tags.get("name", "")
            if not name:
                continue

            cuisine_tag = tags.get("cuisine", "")
            cuisine_list = [c.strip() for c in cuisine_tag.split(";") if c.strip()]

            # Parse address from OSM tags
            addr_parts = []
            if tags.get("addr:housenumber"):
                addr_parts.append(tags["addr:housenumber"])
            if tags.get("addr:street"):
                addr_parts.append(tags["addr:street"])

            results.append(_make_raw_lead(
                name=name,
                address=" ".join(addr_parts),
                city=tags.get("addr:city", ""),
                state=tags.get("addr:state", ""),
                zip_code=tags.get("addr:postcode", ""),
                latitude=e_lat,
                longitude=e_lon,
                phone=tags.get("phone", tags.get("contact:phone", "")),
                website=tags.get("website", tags.get("contact:website", "")),
                source="OpenStreetMap",
                cuisine_tags=cuisine_list,
                categories=[],
            ))

        time.sleep(config.OVERPASS_RATE_LIMIT)

    except requests.RequestException as e:
        logger.error("Overpass request failed: %s", e)

    return results


# ---------------------------------------------------------------------------
# Unified search dispatcher
# ---------------------------------------------------------------------------

def search_all_sources(lat, lon, radius_miles, cuisine_keywords,
                       yelp_categories="", enabled_sources=None,
                       google_api_key=None, yelp_api_key=None):
    """Search all enabled sources for restaurants near a point.

    Args:
        lat, lon: Search center.
        radius_miles: Search radius.
        cuisine_keywords: Keywords for cuisine matching.
        yelp_categories: Yelp category string.
        enabled_sources: List of source names to query. Default: all available.
        google_api_key: Override Google API key.
        yelp_api_key: Override Yelp API key.

    Returns:
        List of raw lead dicts from all sources.
    """
    if enabled_sources is None:
        enabled_sources = ["Google Places", "Yelp", "OpenStreetMap"]

    radius_m = radius_miles * 1609.34
    all_results = []

    if "Google Places" in enabled_sources:
        results = search_google_places(lat, lon, radius_m, cuisine_keywords,
                                       api_key=google_api_key)
        all_results.extend(results)

    if "Yelp" in enabled_sources:
        results = search_yelp(lat, lon, radius_m, yelp_categories or "",
                              api_key=yelp_api_key)
        all_results.extend(results)

    if "OpenStreetMap" in enabled_sources:
        results = search_overpass(lat, lon, radius_miles, cuisine_keywords)
        all_results.extend(results)

    return all_results
