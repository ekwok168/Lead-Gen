"""Tests for the cross-cutting analytics module."""

import os
import sys
import unittest
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import config


class TestAnalytics(unittest.TestCase):
    """Test analytics computations with a temporary database."""

    @classmethod
    def setUpClass(cls):
        """Create a temp database with schema."""
        cls.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls.temp_db_path = cls.temp_db.name
        cls.temp_db.close()

        # Override DB path
        config.DB_PATH = cls.temp_db_path

        from database.connection import init_db
        init_db(cls.temp_db_path)

    @classmethod
    def tearDownClass(cls):
        """Clean up temp database."""
        try:
            os.unlink(cls.temp_db_path)
        except OSError:
            pass

    def setUp(self):
        """Start each test from a clean slate with stages, a DC and two routes."""
        from database.connection import seed_pipeline_stages
        from database.models import clear_all_data, upsert_dc, upsert_route
        clear_all_data()
        seed_pipeline_stages()
        self.dc_id = upsert_dc(
            "Denver DC", "DEN", "1 Depot Way", "Denver", "CO", "80202",
            39.74, -104.99,
        )
        self.route_a = upsert_route(self.dc_id, "R100", "Downtown", "Monday")
        self.route_b = upsert_route(self.dc_id, "R200", "Uptown", "Tuesday")

    # -- helpers ------------------------------------------------------------

    def _stage_id(self, name):
        from database.models import get_pipeline_stages
        stages = get_pipeline_stages()
        return int(stages.loc[stages["name"] == name, "id"].iloc[0])

    def _seed_lead(self, name, salesperson=None):
        from database.models import insert_lead
        return insert_lead(
            name=name, address="100 Main St", city="Denver", state="CO",
            zip_code="80202", latitude=39.74, longitude=-104.99,
            business_type="Restaurant", segment="Full-Service Restaurant",
            estimated_weekly_revenue=400, assigned_salesperson=salesperson,
        )

    def _score_lead(self, lead_id, route_id, grade="B"):
        from database.models import insert_lead_score
        insert_lead_score(
            lead_id=lead_id, nearest_route_id=route_id, nearest_dc_id=self.dc_id,
            nearest_stop_id=None, proximity_score=80, segment_score=80,
            density_score=80, revenue_score=80, total_score=80,
            score_grade=grade, is_core_segment=1,
            nearest_customer_distance_mi=0.4, nearest_route_stop_distance_mi=0.5,
        )

    def _seed_customer(self, name, route_id, weekly_revenue):
        from database.models import insert_customer
        return insert_customer(
            name=name, address="200 Oak Ave", city="Denver", state="CO",
            zip_code="80203", latitude=39.75, longitude=-104.98,
            business_type="Restaurant", segment="Full-Service Restaurant",
            weekly_revenue=weekly_revenue, route_id=route_id,
        )

    def _current_month(self):
        """Return the current 'YYYY-MM' as SQLite sees it (UTC)."""
        from database.connection import get_connection
        conn = get_connection()
        month = conn.execute("SELECT strftime('%Y-%m', 'now')").fetchone()[0]
        conn.close()
        return month

    # -- pipeline forecast --------------------------------------------------

    def test_forecast_weighted_math(self):
        from database.models import insert_deal, update_deal_stage
        from reports.analytics import compute_pipeline_forecast

        insert_deal(name="Open Deal", stage_id=self._stage_id("Proposal"),
                    expected_weekly_revenue=400)
        won = insert_deal(name="Won Deal", stage_id=self._stage_id("Prospect"),
                          expected_weekly_revenue=1000)
        update_deal_stage(won, self._stage_id("Closed Won"))

        forecast = compute_pipeline_forecast()
        # Only the open Proposal deal counts; Proposal probability is 50%
        self.assertAlmostEqual(forecast["weighted_total"], 200.0)
        self.assertAlmostEqual(forecast["best_case"], 400.0)

        by_stage = forecast["by_stage"]
        self.assertEqual(len(by_stage), 1)
        row = by_stage.iloc[0]
        self.assertEqual(row["stage_name"], "Proposal")
        self.assertEqual(row["deal_count"], 1)
        self.assertAlmostEqual(row["total_revenue"], 400.0)
        self.assertAlmostEqual(row["weighted_revenue"], 200.0)
        self.assertNotIn("Closed Won", set(by_stage["stage_name"]))

    # -- empty-DB safety ----------------------------------------------------

    def test_empty_db_all_functions_are_safe(self):
        from database.models import clear_all_data
        from reports.analytics import (
            compute_pipeline_forecast, compute_territory_performance,
            compute_salesperson_leaderboard, compute_revenue_trending,
            compute_activity_metrics,
        )
        # Truly fresh: wipe even the stages/DC/routes seeded in setUp
        clear_all_data()

        forecast = compute_pipeline_forecast()
        self.assertEqual(forecast["weighted_total"], 0.0)
        self.assertEqual(forecast["best_case"], 0.0)
        self.assertTrue(forecast["by_stage"].empty)
        self.assertListEqual(
            list(forecast["by_stage"].columns),
            ["stage_name", "deal_count", "total_revenue", "weighted_revenue"],
        )

        territory = compute_territory_performance()
        self.assertTrue(territory.empty)
        for col in ["route_code", "route_name", "customer_count",
                    "total_weekly_revenue", "lead_count", "a_b_lead_count",
                    "open_deal_count", "pipeline_revenue"]:
            self.assertIn(col, territory.columns)

        leaderboard = compute_salesperson_leaderboard()
        self.assertTrue(leaderboard.empty)
        for col in ["salesperson", "won_count", "won_revenue", "open_count",
                    "open_pipeline", "activities_logged", "win_rate"]:
            self.assertIn(col, leaderboard.columns)

        trend = compute_revenue_trending(months=6)
        self.assertEqual(len(trend), 6)
        self.assertEqual(trend["new_leads"].sum(), 0)
        self.assertEqual(trend["deals_won"].sum(), 0)
        self.assertEqual(trend["revenue_won"].sum(), 0)

        metrics = compute_activity_metrics()
        self.assertEqual(metrics["total"], 0)
        self.assertTrue(metrics["by_type"].empty)
        self.assertTrue(metrics["by_person"].empty)

    # -- territory performance ----------------------------------------------

    def test_territory_performance_counts(self):
        from database.models import insert_deal, update_deal_stage
        from reports.analytics import compute_territory_performance

        # Customers: two on route A, one on route B
        self._seed_customer("Cust A1", self.route_a, 100)
        self._seed_customer("Cust A2", self.route_a, 250)
        self._seed_customer("Cust B1", self.route_b, 500)

        # Leads: A-grade + C-grade scored to route A, B-grade to route B
        lead1 = self._seed_lead("Lead One")
        lead2 = self._seed_lead("Lead Two")
        lead3 = self._seed_lead("Lead Three")
        self._score_lead(lead1, self.route_a, grade="A")
        # lead2 first scored to route B, then re-scored to route A:
        # only the latest score should count
        self._score_lead(lead2, self.route_b, grade="A")
        self._score_lead(lead2, self.route_a, grade="C")
        self._score_lead(lead3, self.route_b, grade="B")

        # Deals: one open on lead1 (route A), one closed lost on lead2
        insert_deal(name="Open A", stage_id=self._stage_id("Qualified"),
                    lead_id=lead1, expected_weekly_revenue=300)
        lost = insert_deal(name="Lost A", stage_id=self._stage_id("Prospect"),
                           lead_id=lead2, expected_weekly_revenue=999)
        update_deal_stage(lost, self._stage_id("Closed Lost"))

        territory = compute_territory_performance()
        self.assertEqual(len(territory), 2)
        by_route = territory.set_index("route_code")

        self.assertEqual(by_route.loc["R100", "route_name"], "Downtown")
        self.assertEqual(by_route.loc["R100", "customer_count"], 2)
        self.assertAlmostEqual(by_route.loc["R100", "total_weekly_revenue"], 350.0)
        self.assertEqual(by_route.loc["R100", "lead_count"], 2)
        self.assertEqual(by_route.loc["R100", "a_b_lead_count"], 1)  # A only; lead2 is C
        self.assertEqual(by_route.loc["R100", "open_deal_count"], 1)
        self.assertAlmostEqual(by_route.loc["R100", "pipeline_revenue"], 300.0)

        self.assertEqual(by_route.loc["R200", "customer_count"], 1)
        self.assertAlmostEqual(by_route.loc["R200", "total_weekly_revenue"], 500.0)
        self.assertEqual(by_route.loc["R200", "lead_count"], 1)
        self.assertEqual(by_route.loc["R200", "a_b_lead_count"], 1)
        self.assertEqual(by_route.loc["R200", "open_deal_count"], 0)
        self.assertEqual(by_route.loc["R200", "pipeline_revenue"], 0)

    # -- salesperson leaderboard ---------------------------------------------

    def test_salesperson_leaderboard(self):
        from database.models import insert_deal, update_deal_stage, insert_activity
        from reports.analytics import compute_salesperson_leaderboard

        # alice: one won (500), one open (300)
        won = insert_deal(name="Alice Won", stage_id=self._stage_id("Prospect"),
                          expected_weekly_revenue=500, assigned_salesperson="alice")
        update_deal_stage(won, self._stage_id("Closed Won"))
        insert_deal(name="Alice Open", stage_id=self._stage_id("Proposal"),
                    expected_weekly_revenue=300, assigned_salesperson="alice")
        # bob: one open (200)
        insert_deal(name="Bob Open", stage_id=self._stage_id("Qualified"),
                    expected_weekly_revenue=200, assigned_salesperson="bob")
        # carol: one lost
        lost = insert_deal(name="Carol Lost", stage_id=self._stage_id("Prospect"),
                           expected_weekly_revenue=100, assigned_salesperson="carol")
        update_deal_stage(lost, self._stage_id("Closed Lost"))
        # Unassigned deal must be dropped
        insert_deal(name="Nobody's Deal", stage_id=self._stage_id("Prospect"),
                    expected_weekly_revenue=50)

        insert_activity(activity_type="Call", subject="c1", logged_by="alice")
        insert_activity(activity_type="Call", subject="c2", logged_by="alice")
        insert_activity(activity_type="Email", subject="e1", logged_by="bob")

        board = compute_salesperson_leaderboard(days=90)
        self.assertEqual(set(board["salesperson"]), {"alice", "bob", "carol"})
        by_person = board.set_index("salesperson")

        self.assertEqual(by_person.loc["alice", "won_count"], 1)
        self.assertAlmostEqual(by_person.loc["alice", "won_revenue"], 500.0)
        self.assertEqual(by_person.loc["alice", "open_count"], 1)
        self.assertAlmostEqual(by_person.loc["alice", "open_pipeline"], 300.0)
        self.assertEqual(by_person.loc["alice", "activities_logged"], 2)
        self.assertAlmostEqual(by_person.loc["alice", "win_rate"], 1.0)

        self.assertEqual(by_person.loc["bob", "won_count"], 0)
        self.assertEqual(by_person.loc["bob", "open_count"], 1)
        self.assertAlmostEqual(by_person.loc["bob", "open_pipeline"], 200.0)
        self.assertEqual(by_person.loc["bob", "activities_logged"], 1)
        self.assertEqual(by_person.loc["bob", "win_rate"], 0)

        self.assertEqual(by_person.loc["carol", "won_count"], 0)
        self.assertEqual(by_person.loc["carol", "open_count"], 0)
        self.assertEqual(by_person.loc["carol", "activities_logged"], 0)
        self.assertEqual(by_person.loc["carol", "win_rate"], 0)  # 0 won / 1 lost

        # alice has the top won_revenue, so she leads the board
        self.assertEqual(board.iloc[0]["salesperson"], "alice")

    def test_leaderboard_activity_only_person_included(self):
        from database.models import insert_activity
        from reports.analytics import compute_salesperson_leaderboard

        insert_activity(activity_type="Meeting", subject="m1", logged_by="dave")
        board = compute_salesperson_leaderboard()
        self.assertEqual(list(board["salesperson"]), ["dave"])
        row = board.iloc[0]
        self.assertEqual(row["won_count"], 0)
        self.assertEqual(row["open_count"], 0)
        self.assertEqual(row["activities_logged"], 1)
        self.assertEqual(row["win_rate"], 0)

    # -- revenue trending -----------------------------------------------------

    def test_revenue_trending_current_month_bucket(self):
        from database.models import insert_deal, update_deal_stage
        from reports.analytics import compute_revenue_trending

        self._seed_lead("Fresh Lead 1")
        self._seed_lead("Fresh Lead 2")
        won = insert_deal(name="Won Now", stage_id=self._stage_id("Prospect"),
                          expected_weekly_revenue=750)
        update_deal_stage(won, self._stage_id("Closed Won"))

        trend = compute_revenue_trending(months=3)
        self.assertEqual(len(trend), 3)
        self.assertEqual(trend.iloc[-1]["month"], self._current_month())

        current = trend.iloc[-1]
        self.assertEqual(current["new_leads"], 2)
        self.assertEqual(current["deals_won"], 1)
        self.assertAlmostEqual(current["revenue_won"], 750.0)

        # Prior months in the range are present as zeros
        prior = trend.iloc[:-1]
        self.assertEqual(prior["new_leads"].sum(), 0)
        self.assertEqual(prior["deals_won"].sum(), 0)
        self.assertEqual(prior["revenue_won"].sum(), 0)

    # -- activity metrics -------------------------------------------------------

    def test_activity_metrics_by_type_counts(self):
        from database.connection import get_connection
        from database.models import insert_activity
        from reports.analytics import compute_activity_metrics

        insert_activity(activity_type="Call", subject="c1", logged_by="alice")
        insert_activity(activity_type="Call", subject="c2", logged_by="alice")
        insert_activity(activity_type="Email", subject="e1", logged_by="bob")
        insert_activity(activity_type="Meeting", subject="m1")  # no logged_by
        # An old activity outside the window must not count
        old = insert_activity(activity_type="Call", subject="ancient", logged_by="alice")
        conn = get_connection()
        conn.execute("UPDATE activities SET activity_date = '2020-01-01 00:00:00' WHERE id = ?",
                     (old,))
        conn.commit()
        conn.close()

        metrics = compute_activity_metrics(days=30)
        self.assertEqual(metrics["total"], 4)

        by_type = metrics["by_type"].set_index("activity_type")["count"]
        self.assertEqual(by_type["Call"], 2)
        self.assertEqual(by_type["Email"], 1)
        self.assertEqual(by_type["Meeting"], 1)

        by_person = metrics["by_person"].set_index("logged_by")["count"]
        self.assertEqual(by_person["alice"], 2)
        self.assertEqual(by_person["bob"], 1)
        self.assertEqual(len(by_person), 2)  # null logged_by excluded


if __name__ == "__main__":
    unittest.main()
