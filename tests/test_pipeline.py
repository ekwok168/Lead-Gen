"""Tests for the sales pipeline / deals data layer."""

import os
import sys
import unittest
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import config


class TestPipeline(unittest.TestCase):
    """Test pipeline stages and deal CRUD with a temporary database."""

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
        """Start each test from a clean slate with seeded stages, a lead and a customer."""
        from database.connection import seed_pipeline_stages
        from database.models import clear_all_data, insert_lead, insert_customer
        clear_all_data()
        seed_pipeline_stages()
        self.lead_id = insert_lead(
            name="Test Lead", address="100 Main St", city="Denver", state="CO",
            zip_code="80202", latitude=39.74, longitude=-104.99,
            business_type="Restaurant", segment="Full-Service Restaurant",
        )
        self.customer_id = insert_customer(
            name="Test Customer", address="200 Oak Ave", city="Denver", state="CO",
            zip_code="80203", latitude=39.75, longitude=-104.98,
            business_type="Restaurant", segment="Full-Service Restaurant",
        )

    def _stage_id(self, name):
        """Return the id of a seeded stage by name."""
        from database.models import get_pipeline_stages
        stages = get_pipeline_stages()
        return int(stages.loc[stages["name"] == name, "id"].iloc[0])

    def _lead_status(self):
        from database.connection import get_connection
        conn = get_connection()
        row = conn.execute("SELECT status FROM leads WHERE id = ?", (self.lead_id,)).fetchone()
        conn.close()
        return row["status"]

    def test_seed_pipeline_stages_idempotent(self):
        from database.connection import seed_pipeline_stages
        from database.models import get_pipeline_stages

        stages = get_pipeline_stages()
        self.assertEqual(len(stages), len(config.DEFAULT_PIPELINE_STAGES))

        # Re-seeding does not duplicate rows
        seed_pipeline_stages()
        seed_pipeline_stages()
        stages = get_pipeline_stages()
        self.assertEqual(len(stages), len(config.DEFAULT_PIPELINE_STAGES))

        # Ordered by display_order
        self.assertEqual(list(stages["display_order"]), sorted(stages["display_order"]))
        self.assertEqual(stages.iloc[0]["name"], "Prospect")
        self.assertEqual(stages.iloc[-1]["name"], "Closed Lost")

    def test_insert_deal_returns_id_and_syncs_lead(self):
        from database.models import insert_deal, get_deal, get_activities_by_lead

        self.assertEqual(self._lead_status(), "New")
        deal_id = insert_deal(
            name="Test Deal", stage_id=self._stage_id("Prospect"),
            lead_id=self.lead_id, expected_weekly_revenue=500,
            assigned_salesperson="alice", notes="hot lead",
        )
        self.assertIsInstance(deal_id, int)

        deal = get_deal(deal_id)
        self.assertIsNotNone(deal)
        self.assertEqual(deal["name"], "Test Deal")
        self.assertEqual(deal["stage_name"], "Prospect")
        self.assertEqual(deal["expected_weekly_revenue"], 500)
        self.assertEqual(deal["lead_id"], self.lead_id)
        self.assertIsNone(deal["closed_at"])

        # Lead promoted New -> Qualified
        self.assertEqual(self._lead_status(), "Qualified")

        # Activity logged
        activities = get_activities_by_lead(self.lead_id)
        self.assertEqual(len(activities), 1)
        self.assertEqual(activities.iloc[0]["activity_type"], "Status Change")
        self.assertEqual(activities.iloc[0]["subject"], "Deal created: Test Deal")

    def test_insert_deal_leaves_advanced_lead_status_alone(self):
        from database.models import insert_deal, update_lead_status

        update_lead_status(self.lead_id, "Converted")
        insert_deal(name="Second Deal", stage_id=self._stage_id("Prospect"),
                    lead_id=self.lead_id)
        self.assertEqual(self._lead_status(), "Converted")

    def test_get_deal_missing_returns_none(self):
        from database.models import get_deal
        self.assertIsNone(get_deal(999999))

    def test_get_all_deals_join_columns(self):
        from database.models import insert_deal, get_all_deals

        insert_deal(name="Lead Deal", stage_id=self._stage_id("Prospect"),
                    lead_id=self.lead_id, expected_weekly_revenue=300)
        insert_deal(name="Customer Deal", stage_id=self._stage_id("Qualified"),
                    customer_id=self.customer_id, expected_weekly_revenue=700)

        deals = get_all_deals()
        self.assertEqual(len(deals), 2)
        for col in ["stage_name", "probability_pct", "display_order",
                    "lead_name", "customer_name", "days_in_stage"]:
            self.assertIn(col, deals.columns)

        by_name = deals.set_index("name")
        self.assertEqual(by_name.loc["Lead Deal", "lead_name"], "Test Lead")
        self.assertEqual(by_name.loc["Lead Deal", "stage_name"], "Prospect")
        self.assertEqual(by_name.loc["Customer Deal", "customer_name"], "Test Customer")
        self.assertEqual(by_name.loc["Customer Deal", "probability_pct"], 25)
        # Just created: days in stage should be ~0
        self.assertGreaterEqual(by_name.loc["Lead Deal", "days_in_stage"], 0)
        self.assertLess(by_name.loc["Lead Deal", "days_in_stage"], 1)

    def test_update_deal_allowlist(self):
        from database.models import insert_deal, get_deal, update_deal

        deal_id = insert_deal(name="Deal", stage_id=self._stage_id("Prospect"))
        update_deal(deal_id, name="Renamed Deal", expected_weekly_revenue=900,
                    loss_reason="price", notes="updated")
        deal = get_deal(deal_id)
        self.assertEqual(deal["name"], "Renamed Deal")
        self.assertEqual(deal["expected_weekly_revenue"], 900)
        self.assertEqual(deal["loss_reason"], "price")
        self.assertEqual(deal["notes"], "updated")

        with self.assertRaises(ValueError):
            update_deal(deal_id, stage_id=self._stage_id("Qualified"))
        with self.assertRaises(ValueError):
            update_deal(deal_id, bogus_column="x")

    def test_update_deal_stage_records_history(self):
        from database.models import (
            insert_deal, update_deal_stage, get_deal_stage_history,
            get_deal, get_activities_by_lead,
        )
        prospect = self._stage_id("Prospect")
        qualified = self._stage_id("Qualified")
        proposal = self._stage_id("Proposal")

        deal_id = insert_deal(name="Deal", stage_id=prospect, lead_id=self.lead_id)
        update_deal_stage(deal_id, qualified, changed_by="alice")
        update_deal_stage(deal_id, proposal, changed_by="bob")

        deal = get_deal(deal_id)
        self.assertEqual(deal["stage_id"], proposal)
        self.assertEqual(deal["stage_name"], "Proposal")
        self.assertIsNone(deal["closed_at"])

        history = get_deal_stage_history(deal_id)
        self.assertEqual(len(history), 2)
        self.assertEqual(history.iloc[0]["from_stage_id"], prospect)
        self.assertEqual(history.iloc[0]["to_stage_id"], qualified)
        self.assertEqual(history.iloc[0]["from_stage_name"], "Prospect")
        self.assertEqual(history.iloc[0]["to_stage_name"], "Qualified")
        self.assertEqual(history.iloc[0]["changed_by"], "alice")
        self.assertEqual(history.iloc[1]["from_stage_name"], "Qualified")
        self.assertEqual(history.iloc[1]["to_stage_name"], "Proposal")
        self.assertEqual(history.iloc[1]["changed_by"], "bob")

        # Activities: 1 from insert_deal + 2 from stage moves
        activities = get_activities_by_lead(self.lead_id)
        self.assertEqual(len(activities), 3)
        subjects = set(activities["subject"])
        self.assertIn("Deal moved to Qualified", subjects)
        self.assertIn("Deal moved to Proposal", subjects)

    def test_update_deal_stage_closed_won(self):
        from database.models import insert_deal, update_deal_stage, get_deal

        deal_id = insert_deal(name="Deal", stage_id=self._stage_id("Prospect"),
                              lead_id=self.lead_id)
        update_deal_stage(deal_id, self._stage_id("Closed Won"))

        deal = get_deal(deal_id)
        self.assertEqual(deal["stage_name"], "Closed Won")
        self.assertIsNotNone(deal["closed_at"])
        self.assertEqual(self._lead_status(), "Converted")

    def test_update_deal_stage_closed_lost(self):
        from database.models import insert_deal, update_deal_stage, get_deal

        deal_id = insert_deal(name="Deal", stage_id=self._stage_id("Prospect"),
                              lead_id=self.lead_id)
        update_deal_stage(deal_id, self._stage_id("Closed Lost"))

        deal = get_deal(deal_id)
        self.assertEqual(deal["stage_name"], "Closed Lost")
        self.assertIsNotNone(deal["closed_at"])
        self.assertEqual(self._lead_status(), "Rejected")

    def test_update_deal_stage_missing_deal(self):
        from database.models import update_deal_stage
        with self.assertRaises(ValueError):
            update_deal_stage(999999, self._stage_id("Qualified"))

    def test_get_pipeline_summary(self):
        from database.models import insert_deal, get_pipeline_summary

        insert_deal(name="Deal A", stage_id=self._stage_id("Proposal"),
                    expected_weekly_revenue=400)
        insert_deal(name="Deal B", stage_id=self._stage_id("Proposal"),
                    expected_weekly_revenue=600)

        summary = get_pipeline_summary()
        # All active stages present, including empty ones
        self.assertEqual(len(summary), len(config.DEFAULT_PIPELINE_STAGES))
        self.assertEqual(list(summary["display_order"]), sorted(summary["display_order"]))

        by_stage = summary.set_index("stage_name")
        self.assertEqual(by_stage.loc["Proposal", "deal_count"], 2)
        self.assertEqual(by_stage.loc["Proposal", "total_expected_weekly_revenue"], 1000)
        # Proposal probability is 50% -> weighted = 1000 * 0.5
        self.assertAlmostEqual(by_stage.loc["Proposal", "weighted_revenue"], 500.0)
        # Empty stage rows have zero counts and revenue
        self.assertEqual(by_stage.loc["Prospect", "deal_count"], 0)
        self.assertEqual(by_stage.loc["Prospect", "total_expected_weekly_revenue"], 0)
        self.assertEqual(by_stage.loc["Prospect", "weighted_revenue"], 0)

    def test_get_won_lost_stats(self):
        from database.models import insert_deal, update_deal_stage, get_won_lost_stats

        # No closed deals yet
        stats = get_won_lost_stats()
        self.assertEqual(stats["won_count"], 0)
        self.assertEqual(stats["lost_count"], 0)
        self.assertEqual(stats["win_rate"], 0)
        self.assertEqual(stats["won_revenue"], 0)
        self.assertEqual(stats["avg_deal_size"], 0)

        won_a = insert_deal(name="Won A", stage_id=self._stage_id("Prospect"),
                            expected_weekly_revenue=400)
        won_b = insert_deal(name="Won B", stage_id=self._stage_id("Prospect"),
                            expected_weekly_revenue=800)
        lost = insert_deal(name="Lost", stage_id=self._stage_id("Prospect"),
                           expected_weekly_revenue=999)
        insert_deal(name="Still Open", stage_id=self._stage_id("Proposal"),
                    expected_weekly_revenue=123)
        update_deal_stage(won_a, self._stage_id("Closed Won"))
        update_deal_stage(won_b, self._stage_id("Closed Won"))
        update_deal_stage(lost, self._stage_id("Closed Lost"))

        stats = get_won_lost_stats(days=90)
        self.assertEqual(stats["won_count"], 2)
        self.assertEqual(stats["lost_count"], 1)
        self.assertAlmostEqual(stats["win_rate"], 2 / 3)
        self.assertEqual(stats["won_revenue"], 1200)
        self.assertEqual(stats["avg_deal_size"], 600)

        # Deals closed long ago fall outside the window
        from database.connection import get_connection
        conn = get_connection()
        conn.execute("UPDATE deals SET closed_at = '2020-01-01 00:00:00' WHERE id = ?", (won_b,))
        conn.commit()
        conn.close()
        stats = get_won_lost_stats(days=90)
        self.assertEqual(stats["won_count"], 1)
        self.assertEqual(stats["won_revenue"], 400)

    def test_clear_all_data_covers_pipeline_tables(self):
        from database.models import (
            insert_deal, update_deal_stage, clear_all_data, get_table_counts,
        )
        deal_id = insert_deal(name="Deal", stage_id=self._stage_id("Prospect"),
                              lead_id=self.lead_id)
        update_deal_stage(deal_id, self._stage_id("Qualified"))

        counts = get_table_counts()
        for table in ["pipeline_stages", "deals", "deal_stage_history"]:
            self.assertIn(table, counts)
        self.assertEqual(counts["deals"], 1)
        self.assertEqual(counts["deal_stage_history"], 1)
        self.assertEqual(counts["pipeline_stages"], len(config.DEFAULT_PIPELINE_STAGES))

        clear_all_data()
        counts = get_table_counts()
        self.assertEqual(counts["deals"], 0)
        self.assertEqual(counts["deal_stage_history"], 0)
        self.assertEqual(counts["pipeline_stages"], 0)


if __name__ == "__main__":
    unittest.main()
