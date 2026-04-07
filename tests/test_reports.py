"""Tests for report generation."""

import os
import sys
import unittest
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import config


class TestReportGeneration(unittest.TestCase):
    """Test DC and route report generation with a temporary database."""

    @classmethod
    def setUpClass(cls):
        """Create a temp database and seed it."""
        cls.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls.temp_db_path = cls.temp_db.name
        cls.temp_db.close()

        # Override DB path
        config.DB_PATH = cls.temp_db_path

        from database.connection import init_db, seed_core_segments
        init_db(cls.temp_db_path)
        seed_core_segments(cls.temp_db_path)

        from database.models import (
            upsert_dc, upsert_route, insert_customer, rebuild_route_stops,
            insert_lead,
        )

        # Create test DC
        cls.dc_id = upsert_dc("Test DC", "DC-TEST", "100 Test St", "Denver", "CO", "80202", 39.74, -104.99)

        # Create test route
        cls.route_id = upsert_route(cls.dc_id, "R-TEST", "Test Route", "MON,WED")

        # Create test customers
        for i in range(5):
            insert_customer(
                name=f"Customer {i}",
                address=f"{100 + i} Main St",
                city="Denver", state="CO", zip_code="80202",
                latitude=39.74 + i * 0.002,
                longitude=-104.99 + i * 0.002,
                business_type="Restaurant",
                segment="Full-Service Restaurant",
                weekly_revenue=500 + i * 100,
                route_id=cls.route_id,
                stop_sequence=i + 1,
            )

        rebuild_route_stops(cls.route_id)

        # Create test leads
        for i in range(10):
            insert_lead(
                name=f"Lead {i}",
                address=f"{200 + i} Oak Ave",
                city="Denver", state="CO", zip_code="80203",
                latitude=39.74 + i * 0.003,
                longitude=-104.99 + i * 0.003,
                business_type="Restaurant" if i < 7 else "Hotel",
                segment="Full-Service Restaurant" if i < 5 else "Hospitality",
                estimated_weekly_revenue=300 + i * 50,
            )

        # Score all leads
        from scoring.engine import score_all_leads
        score_all_leads()

    @classmethod
    def tearDownClass(cls):
        """Clean up temp database."""
        try:
            os.unlink(cls.temp_db_path)
        except OSError:
            pass

    def test_dc_report_generation(self):
        from reports.dc_report import generate_dc_report
        report = generate_dc_report(self.dc_id)

        self.assertIsNotNone(report)
        self.assertIn("summary", report)
        self.assertIn("route_comparison", report)
        self.assertIn("top_leads", report)
        self.assertIn("segment_analysis", report)

        summary = report["summary"]
        self.assertEqual(summary["dc_name"], "Test DC")
        self.assertEqual(summary["total_routes"], 1)
        self.assertEqual(summary["total_customers"], 5)
        self.assertGreater(summary["total_leads"], 0)

    def test_dc_report_grade_distribution(self):
        from reports.dc_report import generate_dc_report
        report = generate_dc_report(self.dc_id)
        grades = report["summary"]["grade_distribution"]
        total = sum(grades.values())
        self.assertGreater(total, 0)

    def test_route_report_generation(self):
        from reports.route_report import generate_route_report
        report = generate_route_report(self.route_id)

        self.assertIsNotNone(report)
        self.assertIn("summary", report)
        self.assertIn("customers", report)
        self.assertIn("stops", report)
        self.assertIn("leads", report)

        summary = report["summary"]
        self.assertEqual(summary["route_code"], "R-TEST")
        self.assertEqual(summary["customer_count"], 5)

    def test_route_report_has_why_text(self):
        from reports.route_report import generate_route_report
        report = generate_route_report(self.route_id)
        leads = report["leads"]
        if not leads.empty and "why_this_lead" in leads.columns:
            self.assertTrue(all(leads["why_this_lead"].str.len() > 0))

    def test_export_dc_report_excel(self):
        from reports.dc_report import generate_dc_report
        from reports.export import export_dc_report_excel
        report = generate_dc_report(self.dc_id)
        excel_bytes = export_dc_report_excel(report)
        self.assertGreater(len(excel_bytes), 100)

    def test_export_route_report_excel(self):
        from reports.route_report import generate_route_report
        from reports.export import export_route_report_excel
        report = generate_route_report(self.route_id)
        excel_bytes = export_route_report_excel(report)
        self.assertGreater(len(excel_bytes), 100)

    def test_leads_csv_export(self):
        from database.models import get_leads_with_scores
        from reports.export import generate_leads_csv
        scored = get_leads_with_scores()
        csv_bytes = generate_leads_csv(scored)
        self.assertGreater(len(csv_bytes), 0)


if __name__ == "__main__":
    unittest.main()
