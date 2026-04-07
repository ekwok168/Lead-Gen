"""Density scoring - measures how many existing customers are near a lead."""

import numpy as np
from sklearn.neighbors import BallTree

import config


def score_density(customer_count):
    """Score based on number of nearby customers.

    Returns a score 0-100 where higher = more customers nearby.
    """
    for min_count, score in config.DENSITY_TIERS:
        if customer_count >= min_count:
            return score
    return config.DENSITY_DEFAULT_SCORE


def compute_density_scores(lead_coords, customer_coords, radius_miles=None):
    """Count nearby customers for each lead and return density scores.

    Args:
        lead_coords: array of (lat, lon) for each lead
        customer_coords: array of (lat, lon) for each customer
        radius_miles: search radius in miles (default from config)

    Returns:
        List of dicts with:
        - nearby_customer_count: int
        - density_score: 0-100
    """
    if radius_miles is None:
        radius_miles = config.DENSITY_RADIUS_MILES

    if len(lead_coords) == 0 or len(customer_coords) == 0:
        return [{"nearby_customer_count": 0, "density_score": config.DENSITY_DEFAULT_SCORE}
                for _ in range(len(lead_coords))]

    # Convert to radians
    lead_rad = np.radians(np.array(lead_coords, dtype=np.float64))
    cust_rad = np.radians(np.array(customer_coords, dtype=np.float64))

    # Convert radius to radians (miles / earth_radius)
    radius_rad = radius_miles / 3959.0

    tree = BallTree(cust_rad, metric="haversine")
    counts = tree.query_radius(lead_rad, r=radius_rad, count_only=True)

    results = []
    for count in counts:
        results.append({
            "nearby_customer_count": int(count),
            "density_score": score_density(int(count)),
        })

    return results
