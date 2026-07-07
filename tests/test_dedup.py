"""Tests for duplicate detection utilities."""

import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import config
from utils.dedup import check_duplicate, filter_duplicates, haversine_miles


class TestHaversineMiles(unittest.TestCase):
    """Test the haversine distance helper."""

    def test_zero_distance(self):
        self.assertAlmostEqual(haversine_miles(39.74, -104.99, 39.74, -104.99), 0.0)

    def test_known_distance(self):
        # Denver to Colorado Springs is roughly 60-70 miles
        dist = haversine_miles(39.7392, -104.9903, 38.8339, -104.8214)
        self.assertGreater(dist, 55)
        self.assertLess(dist, 75)


class TestCheckDuplicate(unittest.TestCase):
    """Test single-record duplicate detection."""

    def setUp(self):
        self.existing = pd.DataFrame([
            {"name": "Blue Moon Diner", "latitude": 39.7400, "longitude": -104.9900},
            {"name": "Golden Dragon", "latitude": 39.7500, "longitude": -104.9800},
        ])

    def test_exact_name_match(self):
        is_dup, info = check_duplicate("Blue Moon Diner", 45.0, -100.0, self.existing)
        self.assertTrue(is_dup)
        self.assertIn("Exact name match", info)

    def test_exact_name_match_case_insensitive(self):
        is_dup, info = check_duplicate("  blue moon DINER ", 45.0, -100.0, self.existing)
        self.assertTrue(is_dup)
        self.assertIn("Exact name match", info)

    def test_fuzzy_match_above_threshold(self):
        # One-character typo scores well above the 85 threshold
        is_dup, info = check_duplicate("Blue Moon Dinner", 45.0, -100.0, self.existing)
        self.assertTrue(is_dup)
        self.assertIn("Similar name", info)

    def test_fuzzy_match_below_threshold(self):
        # Unrelated name, far-away coords: not a duplicate
        is_dup, _ = check_duplicate("Taco Palace", 45.0, -100.0, self.existing)
        self.assertFalse(is_dup)

    def test_proximity_duplicate_30_feet(self):
        # ~30 ft north of Blue Moon Diner (1 degree lat ~= 69 miles)
        lat_offset = (30.0 / 5280.0) / 69.0
        is_dup, info = check_duplicate(
            "Completely Different Name", 39.7400 + lat_offset, -104.9900, self.existing
        )
        self.assertTrue(is_dup)
        self.assertIn("Within", info)

    def test_proximity_not_duplicate_tenth_mile(self):
        # 0.1 mi north is beyond the 0.05 mi threshold
        lat_offset = 0.1 / 69.0
        is_dup, _ = check_duplicate(
            "Completely Different Name", 39.7400 + lat_offset, -104.9900, self.existing
        )
        self.assertFalse(is_dup)

    def test_empty_existing_df(self):
        is_dup, info = check_duplicate("Blue Moon Diner", 39.74, -104.99, pd.DataFrame())
        self.assertFalse(is_dup)
        self.assertEqual(info, "")

    def test_none_existing_df(self):
        is_dup, _ = check_duplicate("Blue Moon Diner", 39.74, -104.99, None)
        self.assertFalse(is_dup)


class TestFilterDuplicates(unittest.TestCase):
    """Test batch duplicate splitting."""

    def setUp(self):
        self.customers = pd.DataFrame([
            {"name": "Blue Moon Diner", "latitude": 39.7400, "longitude": -104.9900},
        ])
        self.leads = pd.DataFrame([
            {"name": "Golden Dragon", "latitude": 39.7500, "longitude": -104.9800},
        ])

    def test_splits_correctly(self):
        new_df = pd.DataFrame([
            {"name": "Blue Moon Diner", "latitude": 41.0, "longitude": -100.0},   # dup of customer
            {"name": "Golden Dragon", "latitude": 42.0, "longitude": -101.0},     # dup of lead
            {"name": "Fresh New Bistro", "latitude": 43.0, "longitude": -102.0},  # unique
        ])
        unique_df, dupes_df = filter_duplicates(new_df, self.customers, self.leads)
        self.assertEqual(len(unique_df), 1)
        self.assertEqual(unique_df.iloc[0]["name"], "Fresh New Bistro")
        self.assertEqual(len(dupes_df), 2)
        self.assertEqual(list(dupes_df.columns), ["row", "name", "reason"])
        lead_dup = dupes_df[dupes_df["name"] == "Golden Dragon"].iloc[0]
        self.assertIn("Already in leads", lead_dup["reason"])

    def test_empty_new_df(self):
        unique_df, dupes_df = filter_duplicates(
            pd.DataFrame(), self.customers, self.leads
        )
        self.assertTrue(unique_df.empty)
        self.assertTrue(dupes_df.empty)
        self.assertEqual(list(dupes_df.columns), ["row", "name", "reason"])

    def test_no_duplicates(self):
        new_df = pd.DataFrame([
            {"name": "Fresh New Bistro", "latitude": 43.0, "longitude": -102.0},
        ])
        unique_df, dupes_df = filter_duplicates(new_df, self.customers, self.leads)
        self.assertEqual(len(unique_df), 1)
        self.assertEqual(len(dupes_df), 0)


if __name__ == "__main__":
    unittest.main()
