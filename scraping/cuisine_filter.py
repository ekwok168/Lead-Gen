"""Cuisine classification for filtering Asian/Chinese restaurants."""

import re

import config


def get_keywords_for_categories(selected_categories):
    """Build a keyword list from selected cuisine categories.

    Args:
        selected_categories: List of category names (e.g., ["Chinese", "Japanese"]).
                             If empty or None, returns all keywords.

    Returns:
        List of lowercase keyword strings.
    """
    if not selected_categories:
        return list(config.ASIAN_CUISINE_KEYWORDS)

    keywords = []
    for cat in selected_categories:
        keywords.extend(config.CUISINE_CATEGORIES.get(cat, []))
    return keywords


def get_yelp_categories(selected_categories):
    """Get Yelp category codes for selected cuisine categories.

    Args:
        selected_categories: List of category names.

    Returns:
        Comma-separated string of Yelp category codes.
    """
    if not selected_categories:
        codes = []
        for cats in config.YELP_CUISINE_CATEGORIES.values():
            codes.extend(cats)
        return ",".join(codes)

    codes = []
    for cat in selected_categories:
        codes.extend(config.YELP_CUISINE_CATEGORIES.get(cat, []))
    return ",".join(codes)


def classify_cuisine(name, cuisine_tags=None, categories=None, keywords=None):
    """Classify whether a restaurant matches target cuisines.

    Checks restaurant name, cuisine tags, and category labels against keywords.

    Args:
        name: Restaurant name.
        cuisine_tags: List of cuisine tags (e.g., from OSM or Google).
        categories: List of category strings (e.g., from Yelp).
        keywords: Target keywords to match against. Defaults to all Asian keywords.

    Returns:
        Dict with:
        - match: bool
        - confidence: "high", "medium", or "low"
        - matched_keywords: list of matched keywords
        - source: which field matched ("tags", "categories", "name")
    """
    if keywords is None:
        keywords = config.ASIAN_CUISINE_KEYWORDS
    if cuisine_tags is None:
        cuisine_tags = []
    if categories is None:
        categories = []

    matched = []
    source = None

    # Normalize inputs to lowercase
    name_lower = (name or "").lower()
    tags_lower = [t.lower() for t in cuisine_tags if t]
    cats_lower = [c.lower() for c in categories if c]

    # Check cuisine tags first (most reliable)
    for kw in keywords:
        kw_lower = kw.lower()
        for tag in tags_lower:
            if kw_lower in tag:
                if kw_lower not in matched:
                    matched.append(kw_lower)
                source = source or "tags"

    # Check categories
    for kw in keywords:
        kw_lower = kw.lower()
        for cat in cats_lower:
            if kw_lower in cat:
                if kw_lower not in matched:
                    matched.append(kw_lower)
                source = source or "categories"

    # Check restaurant name
    for kw in keywords:
        kw_lower = kw.lower()
        if kw_lower in name_lower:
            if kw_lower not in matched:
                matched.append(kw_lower)
            source = source or "name"

    if not matched:
        return {"match": False, "confidence": "none", "matched_keywords": [], "source": None}

    # Determine confidence
    if source == "tags" or source == "categories":
        confidence = "high" if len(matched) >= 1 else "medium"
    elif source == "name" and len(matched) >= 2:
        confidence = "high"
    elif source == "name":
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "match": True,
        "confidence": confidence,
        "matched_keywords": matched,
        "source": source,
    }
