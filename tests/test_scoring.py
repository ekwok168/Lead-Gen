"""Tests for the scoring engine components."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import config
from scoring.proximity import score_proximity, compute_nearest_stops, find_insertion_point
from scoring.density import score_density, compute_density_scores
from scoring.segment import score_segment


class TestProximityScoring(unittest.TestCase):
    """Test proximity score calculations."""

    def test_very_close(self):
        self.assertEqual(score_proximity(0.3), 100)

    def test_half_mile(self):
        self.assertEqual(score_proximity(0.7), 85)

    def test_one_mile(self):
        self.assertEqual(score_proximity(1.5), 70)

    def test_five_miles(self):
        self.assertEqual(score_proximity(3.0), 50)

    def test_ten_miles(self):
        self.assertEqual(score_proximity(8.0), 30)

    def test_twenty_miles(self):
        self.assertEqual(score_proximity(15.0), 15)

    def test_far_away(self):
        self.assertEqual(score_proximity(25.0), config.PROXIMITY_DEFAULT_SCORE)

    def test_zero_distance(self):
        self.assertEqual(score_proximity(0.0), 100)

    def test_boundary_half_mile(self):
        self.assertEqual(score_proximity(0.5), 100)

    def test_compute_nearest_stops(self):
        # Lead at (39.74, -104.99)
        lead_coords = [(39.74, -104.99)]
        # Two stops
        stop_coords = [(39.74, -104.99), (39.80, -105.05)]
        stop_ids = np.array([1, 2])
        stop_route_ids = np.array([10, 20])
        stop_names = np.array(["Stop A", "Stop B"])

        results = compute_nearest_stops(lead_coords, stop_coords, stop_ids, stop_route_ids, stop_names)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["nearest_stop_id"], 1)
        self.assertEqual(results[0]["nearest_route_id"], 10)
        self.assertAlmostEqual(results[0]["nearest_route_stop_distance_mi"], 0.0, places=1)

    def test_find_insertion_point(self):
        # Route goes from (0,0) to (0,1) to (0,2)
        coords = [(39.70, -105.00), (39.72, -105.00), (39.74, -105.00)]
        seqs = [1, 2, 3]

        # Lead near the middle
        pos = find_insertion_point(39.71, -105.00, coords, seqs)
        self.assertEqual(pos, 1)  # After stop 1


class TestDensityScoring(unittest.TestCase):
    """Test density score calculations."""

    def test_high_density(self):
        self.assertEqual(score_density(12), 100)

    def test_medium_density(self):
        self.assertEqual(score_density(5), 70)

    def test_low_density(self):
        self.assertEqual(score_density(1), 30)

    def test_no_density(self):
        self.assertEqual(score_density(0), config.DENSITY_DEFAULT_SCORE)

    def test_compute_density_scores(self):
        # Lead at center, customers clustered nearby
        lead_coords = [(39.74, -104.99)]
        cust_coords = [
            (39.74, -104.99),
            (39.741, -104.991),
            (39.739, -104.989),
        ]
        results = compute_density_scores(lead_coords, cust_coords, radius_miles=1.0)
        self.assertEqual(len(results), 1)
        self.assertGreaterEqual(results[0]["nearby_customer_count"], 3)

    def test_empty_leads(self):
        results = compute_density_scores([], [(39.74, -104.99)])
        self.assertEqual(len(results), 0)

    def test_empty_customers(self):
        results = compute_density_scores([(39.74, -104.99)], [])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["density_score"], config.DENSITY_DEFAULT_SCORE)


class TestSegmentScoring(unittest.TestCase):
    """Test segment match scoring."""

    def setUp(self):
        import pandas as pd
        self.core_segments = pd.DataFrame([
            {"segment_name": "Full-Service Restaurant", "business_type": "Restaurant",
             "min_estimated_revenue": 500, "priority": 1},
            {"segment_name": "C-Store", "business_type": "Convenience Store",
             "min_estimated_revenue": 400, "priority": 2},
        ])

    def test_exact_match(self):
        result = score_segment("Restaurant", "Full-Service Restaurant", self.core_segments)
        self.assertEqual(result["segment_score"], config.SEGMENT_EXACT_MATCH)
        self.assertTrue(result["is_core_segment"])

    def test_type_match(self):
        result = score_segment("Restaurant", "Quick-Service Restaurant", self.core_segments)
        self.assertEqual(result["segment_score"], config.SEGMENT_TYPE_MATCH)
        self.assertFalse(result["is_core_segment"])

    def test_adjacent_match(self):
        result = score_segment("Bar/Tavern", "Entertainment", self.core_segments)
        self.assertEqual(result["segment_score"], config.SEGMENT_ADJACENT_MATCH)

    def test_no_match(self):
        result = score_segment("Fitness Center", "Other", self.core_segments)
        self.assertEqual(result["segment_score"], config.SEGMENT_NO_MATCH)

    def test_empty_core_segments(self):
        import pandas as pd
        result = score_segment("Restaurant", "Full-Service Restaurant", pd.DataFrame())
        self.assertEqual(result["segment_score"], config.SEGMENT_NO_MATCH)

    def test_case_insensitive(self):
        result = score_segment("restaurant", "full-service restaurant", self.core_segments)
        self.assertEqual(result["segment_score"], config.SEGMENT_EXACT_MATCH)


if __name__ == "__main__":
    unittest.main()
