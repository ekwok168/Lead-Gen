"""Tests for the restaurant discovery module (Overpass API)."""

import os
import sys
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import config
from discovery.overpass import (
    PARSED_COLUMNS,
    build_overpass_query,
    cluster_coordinates,
    discover_restaurants,
    parse_overpass_elements,
)
from utils.dedup import haversine_miles


class TestClusterCoordinates(unittest.TestCase):
    """Test DBSCAN-based coordinate clustering."""

    def test_close_points_one_cluster(self):
        # ~0.1 mi apart (0.1 mi latitude ~= 0.00145 degrees)
        coords = [(39.7392, -104.9903), (39.74065, -104.9903)]
        clusters = cluster_coordinates(coords, radius_miles=1.0)
        self.assertEqual(len(clusters), 1)

    def test_far_points_two_clusters(self):
        # ~50 mi apart
        coords = [(39.7392, -104.9903), (40.4636, -104.9903)]
        clusters = cluster_coordinates(coords, radius_miles=1.0)
        self.assertEqual(len(clusters), 2)

    def test_effective_radius_covers_members(self):
        coords = [(39.7392, -104.9903), (39.74065, -104.9903)]
        radius = 1.0
        clusters = cluster_coordinates(coords, radius_miles=radius)
        self.assertEqual(len(clusters), 1)
        clat, clon, eff_radius = clusters[0]
        for lat, lon in coords:
            dist = float(haversine_miles(clat, clon, lat, lon))
            # Enlarged circle must cover each member's original radius
            self.assertLessEqual(dist + radius, eff_radius + 1e-6)
        self.assertGreaterEqual(eff_radius, radius)

    def test_empty_input(self):
        self.assertEqual(cluster_coordinates([], radius_miles=1.0), [])

    def test_invalid_coords_filtered(self):
        coords = [(0.0, 0.0), (float("nan"), -104.99), (39.7392, -104.9903)]
        clusters = cluster_coordinates(coords, radius_miles=1.0)
        self.assertEqual(len(clusters), 1)
        self.assertAlmostEqual(clusters[0][0], 39.7392, places=4)

    def test_all_invalid_returns_empty(self):
        coords = [(0.0, 0.0), (float("nan"), float("nan"))]
        self.assertEqual(cluster_coordinates(coords, radius_miles=1.0), [])

    def test_chained_line_split_into_bounded_clusters(self):
        # 30 stops in a north-south line, 0.8 mi apart: DBSCAN chains them
        # into one cluster spanning ~23 miles, which must be split so no
        # query circle exceeds 2.5x the requested radius.
        radius = 1.0
        coords = [(39.7392 + i * 0.8 / 69.0, -104.9903) for i in range(30)]
        clusters = cluster_coordinates(coords, radius_miles=radius)
        self.assertGreater(len(clusters), 1)
        for _, _, eff_radius in clusters:
            self.assertLessEqual(eff_radius, radius * 2.5)
        # Every original point must be covered by some cluster circle
        for lat, lon in coords:
            covered = any(
                float(haversine_miles(clat, clon, lat, lon)) <= eff_radius + 1e-6
                for clat, clon, eff_radius in clusters
            )
            self.assertTrue(covered, f"point ({lat}, {lon}) not covered")


class TestBuildOverpassQuery(unittest.TestCase):
    """Test Overpass QL query construction."""

    def test_contains_node_and_way_per_amenity(self):
        query = build_overpass_query(39.7392, -104.9903, 1609, ["restaurant", "cafe"])
        for amenity in ("restaurant", "cafe"):
            self.assertIn(f'node["amenity"="{amenity}"]', query)
            self.assertIn(f'way["amenity"="{amenity}"]', query)

    def test_around_radius_and_coords(self):
        query = build_overpass_query(39.7392, -104.9903, 1609, ["restaurant"])
        self.assertIn("around:1609,39.739200,-104.990300", query)

    def test_header_and_output(self):
        query = build_overpass_query(39.7392, -104.9903, 500, ["bar"])
        self.assertIn("[out:json]", query)
        self.assertIn(f"[timeout:{config.OVERPASS_TIMEOUT}]", query)
        self.assertEqual(query.splitlines()[-1], "out center;")


class TestParseOverpassElements(unittest.TestCase):
    """Test normalization of raw Overpass elements."""

    def _node(self, **tag_overrides):
        tags = {
            "name": "Pho Denver",
            "amenity": "restaurant",
            "cuisine": "vietnamese",
            "phone": "+1-303-555-0100",
            "website": "https://phodenver.example.com",
            "addr:housenumber": "123",
            "addr:street": "Main St",
            "addr:city": "Denver",
            "addr:postcode": "80202",
        }
        tags.update(tag_overrides)
        return {"type": "node", "id": 111, "lat": 39.74, "lon": -104.99, "tags": tags}

    def test_node_parsing(self):
        df = parse_overpass_elements([self._node()])
        self.assertEqual(len(df), 1)
        row = df.iloc[0]
        self.assertEqual(row["osm_id"], "node/111")
        self.assertEqual(row["name"], "Pho Denver")
        self.assertAlmostEqual(row["latitude"], 39.74)
        self.assertAlmostEqual(row["longitude"], -104.99)
        self.assertEqual(row["cuisine"], "vietnamese")
        self.assertEqual(row["phone"], "+1-303-555-0100")

    def test_way_uses_center(self):
        element = {
            "type": "way",
            "id": 222,
            "center": {"lat": 39.75, "lon": -104.98},
            "tags": {"name": "Big Diner", "amenity": "restaurant"},
        }
        df = parse_overpass_elements([element])
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["osm_id"], "way/222")
        self.assertAlmostEqual(df.iloc[0]["latitude"], 39.75)
        self.assertAlmostEqual(df.iloc[0]["longitude"], -104.98)

    def test_unnamed_elements_skipped(self):
        unnamed = {"type": "node", "id": 333, "lat": 39.7, "lon": -104.9,
                   "tags": {"amenity": "restaurant"}}
        df = parse_overpass_elements([unnamed, self._node()])
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["osm_id"], "node/111")

    def test_missing_coords_skipped(self):
        no_coords = {"type": "way", "id": 444,
                     "tags": {"name": "Ghost Cafe", "amenity": "cafe"}}
        df = parse_overpass_elements([no_coords])
        self.assertEqual(len(df), 0)

    def test_address_assembly_full(self):
        df = parse_overpass_elements([self._node()])
        self.assertEqual(df.iloc[0]["address"], "123 Main St, Denver, 80202")

    def test_address_assembly_partial(self):
        element = self._node()
        del element["tags"]["addr:housenumber"]
        del element["tags"]["addr:postcode"]
        df = parse_overpass_elements([element])
        self.assertEqual(df.iloc[0]["address"], "Main St, Denver")

    def test_business_type_segment_mapping(self):
        for amenity, (btype, segment) in config.AMENITY_BUSINESS_TYPE_MAP.items():
            df = parse_overpass_elements([self._node(amenity=amenity)])
            self.assertEqual(df.iloc[0]["business_type"], btype)
            self.assertEqual(df.iloc[0]["segment"], segment)

    def test_empty_input(self):
        df = parse_overpass_elements([])
        self.assertEqual(len(df), 0)
        self.assertEqual(list(df.columns), PARSED_COLUMNS)


class TestDiscoverRestaurants(unittest.TestCase):
    """Test the discovery orchestrator with query_overpass mocked."""

    def _element(self, osm_id, lat, lon, name, amenity="restaurant"):
        return {"type": "node", "id": osm_id, "lat": lat, "lon": lon,
                "tags": {"name": name, "amenity": amenity}}

    @patch("discovery.overpass.time.sleep")
    @patch("discovery.overpass.query_overpass")
    def test_returns_dataframe_with_distance(self, mock_query, _mock_sleep):
        mock_query.return_value = {"elements": [
            self._element(1, 39.7392, -104.9903, "At The Search Point"),
            self._element(2, 39.7537, -104.9903, "One Mile North"),
        ]}
        df = discover_restaurants([(39.7392, -104.9903)], radius_miles=2.0)
        self.assertEqual(len(df), 2)
        self.assertIn("distance_mi", df.columns)
        at_point = df[df["name"] == "At The Search Point"].iloc[0]
        far = df[df["name"] == "One Mile North"].iloc[0]
        self.assertAlmostEqual(at_point["distance_mi"], 0.0, places=2)
        self.assertAlmostEqual(far["distance_mi"], 1.0, places=1)

    @patch("discovery.overpass.time.sleep")
    @patch("discovery.overpass.query_overpass")
    def test_results_filtered_to_requested_radius(self, mock_query, _mock_sleep):
        mock_query.return_value = {"elements": [
            self._element(1, 39.7392, -104.9903, "At The Search Point"),
            self._element(2, 39.8117, -104.9903, "Five Miles North"),
        ]}
        df = discover_restaurants([(39.7392, -104.9903)], radius_miles=1.0)
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["name"], "At The Search Point")

    @patch("discovery.overpass.time.sleep")
    @patch("discovery.overpass.query_overpass")
    def test_dedups_same_osm_id_across_clusters(self, mock_query, _mock_sleep):
        # Two clusters (points ~50 mi apart), both return the same element
        mock_query.return_value = {"elements": [
            self._element(1, 39.7392, -104.9903, "Duplicated Diner"),
        ]}
        df = discover_restaurants(
            [(39.7392, -104.9903), (40.4636, -104.9903)], radius_miles=1.0
        )
        self.assertEqual(mock_query.call_count, 2)
        self.assertEqual(len(df), 1)

    @patch("discovery.overpass.time.sleep")
    @patch("discovery.overpass.query_overpass")
    def test_progress_callback_called(self, mock_query, _mock_sleep):
        mock_query.return_value = {"elements": [
            self._element(1, 39.7392, -104.9903, "Cafe One"),
        ]}
        calls = []
        discover_restaurants(
            [(39.7392, -104.9903)],
            radius_miles=1.0,
            progress_callback=lambda pct, msg: calls.append((pct, msg)),
        )
        self.assertGreater(len(calls), 0)
        pcts = [pct for pct, _ in calls]
        self.assertEqual(pcts, sorted(pcts))
        self.assertEqual(pcts[-1], 100)
        for pct, msg in calls:
            self.assertIsInstance(pct, int)
            self.assertTrue(0 <= pct <= 100)
            self.assertIsInstance(msg, str)

    @patch("discovery.overpass.time.sleep")
    @patch("discovery.overpass.query_overpass")
    def test_partial_failure_continues(self, mock_query, _mock_sleep):
        mock_query.side_effect = [
            RuntimeError("boom"),
            {"elements": [self._element(1, 40.4636, -104.9903, "Survivor Grill")]},
        ]
        df = discover_restaurants(
            [(39.7392, -104.9903), (40.4636, -104.9903)], radius_miles=1.0
        )
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["name"], "Survivor Grill")

    @patch("discovery.overpass.time.sleep")
    @patch("discovery.overpass.query_overpass")
    def test_all_failures_raises(self, mock_query, _mock_sleep):
        mock_query.side_effect = RuntimeError("boom")
        with self.assertRaises(RuntimeError):
            discover_restaurants(
                [(39.7392, -104.9903), (40.4636, -104.9903)], radius_miles=1.0
            )

    @patch("discovery.overpass.query_overpass")
    def test_empty_coords_returns_empty(self, mock_query):
        df = discover_restaurants([])
        self.assertTrue(df.empty)
        self.assertIn("distance_mi", df.columns)
        mock_query.assert_not_called()

    @patch("discovery.overpass.time.sleep")
    @patch("discovery.overpass.query_overpass")
    def test_defaults_used(self, mock_query, _mock_sleep):
        mock_query.return_value = {"elements": []}
        discover_restaurants([(39.7392, -104.9903)])
        query = mock_query.call_args[0][0]
        for amenity in config.DISCOVERY_AMENITY_TYPES:
            self.assertIn(f'"amenity"="{amenity}"', query)


class TestQueryOverpassRetries(unittest.TestCase):
    """Test retry/backoff behavior of query_overpass."""

    @patch("discovery.overpass.time.sleep")
    @patch("discovery.overpass.urllib.request.urlopen")
    def test_url_error_retries_then_raises(self, mock_urlopen, mock_sleep):
        import urllib.error
        from discovery.overpass import query_overpass
        mock_urlopen.side_effect = urllib.error.URLError("network down")
        with self.assertRaises(RuntimeError):
            query_overpass("[out:json];")
        self.assertEqual(mock_urlopen.call_count, config.OVERPASS_MAX_RETRIES + 1)
        sleeps = [call.args[0] for call in mock_sleep.call_args_list]
        self.assertEqual(sleeps, [2, 4, 8])

    @patch("discovery.overpass.time.sleep")
    @patch("discovery.overpass.urllib.request.urlopen")
    def test_non_retryable_http_error_raises_immediately(self, mock_urlopen, _mock_sleep):
        import urllib.error
        from discovery.overpass import query_overpass
        mock_urlopen.side_effect = urllib.error.HTTPError(
            config.OVERPASS_API_URL, 400, "Bad Request", {}, None
        )
        with self.assertRaises(RuntimeError):
            query_overpass("[out:json];")
        self.assertEqual(mock_urlopen.call_count, 1)


if __name__ == "__main__":
    unittest.main()
