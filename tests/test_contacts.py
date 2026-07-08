"""Tests for the contacts and activities data layer."""

import os
import sys
import unittest
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import config


class TestContactsAndActivities(unittest.TestCase):
    """Test contact and activity CRUD with a temporary database."""

    @classmethod
    def setUpClass(cls):
        """Create a temp database and seed a lead and a customer."""
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
        """Start each test from a clean slate with one lead and one customer."""
        from database.models import clear_all_data, insert_lead, insert_customer
        clear_all_data()
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

    def test_contact_round_trip(self):
        from database.models import insert_contact, get_contact, update_contact, delete_contact

        contact_id = insert_contact(
            first_name="Jane", last_name="Doe", title="Owner",
            email="jane@example.com", phone="303-555-0100",
            mobile_phone="303-555-0101", preferred_contact_method="Email",
            is_primary=1, notes="Met at trade show", lead_id=self.lead_id,
        )
        self.assertIsInstance(contact_id, int)

        contact = get_contact(contact_id)
        self.assertIsNotNone(contact)
        self.assertEqual(contact["first_name"], "Jane")
        self.assertEqual(contact["last_name"], "Doe")
        self.assertEqual(contact["email"], "jane@example.com")
        self.assertEqual(contact["preferred_contact_method"], "Email")
        self.assertEqual(contact["is_primary"], 1)
        self.assertEqual(contact["lead_id"], self.lead_id)

        update_contact(contact_id, title="General Manager", phone="303-555-0199")
        contact = get_contact(contact_id)
        self.assertEqual(contact["title"], "General Manager")
        self.assertEqual(contact["phone"], "303-555-0199")
        # Unchanged fields survive the update
        self.assertEqual(contact["first_name"], "Jane")

        delete_contact(contact_id)
        self.assertIsNone(get_contact(contact_id))

    def test_get_contact_missing_returns_none(self):
        from database.models import get_contact
        self.assertIsNone(get_contact(999999))

    def test_update_contact_rejects_unknown_field(self):
        from database.models import insert_contact, update_contact
        contact_id = insert_contact(first_name="Bob", lead_id=self.lead_id)
        with self.assertRaises(ValueError):
            update_contact(contact_id, created_at="2020-01-01")
        with self.assertRaises(ValueError):
            update_contact(contact_id, bogus_column="x")

    def test_update_contact_can_relink(self):
        from database.models import insert_contact, update_contact, get_contact
        contact_id = insert_contact(first_name="Bob")
        update_contact(contact_id, lead_id=self.lead_id, customer_id=None)
        self.assertEqual(get_contact(contact_id)["lead_id"], self.lead_id)

    def test_contacts_by_lead_vs_customer(self):
        from database.models import (
            insert_contact, get_contacts_by_lead, get_contacts_by_customer, get_all_contacts,
        )
        insert_contact(first_name="LeadContact", lead_id=self.lead_id)
        insert_contact(first_name="CustContact", customer_id=self.customer_id)

        lead_contacts = get_contacts_by_lead(self.lead_id)
        self.assertEqual(len(lead_contacts), 1)
        self.assertEqual(lead_contacts.iloc[0]["first_name"], "LeadContact")

        cust_contacts = get_contacts_by_customer(self.customer_id)
        self.assertEqual(len(cust_contacts), 1)
        self.assertEqual(cust_contacts.iloc[0]["first_name"], "CustContact")

        all_contacts = get_all_contacts()
        self.assertEqual(len(all_contacts), 2)
        self.assertIn("lead_name", all_contacts.columns)
        self.assertIn("customer_name", all_contacts.columns)
        by_name = all_contacts.set_index("first_name")
        self.assertEqual(by_name.loc["LeadContact", "lead_name"], "Test Lead")
        self.assertEqual(by_name.loc["CustContact", "customer_name"], "Test Customer")

    def test_delete_contact_removes_activities(self):
        from database.models import (
            insert_contact, insert_activity, delete_contact,
            get_activities_by_contact, get_activities_by_lead,
        )
        contact_id = insert_contact(first_name="Jane", lead_id=self.lead_id)
        insert_activity("Call", subject="Intro call", contact_id=contact_id, lead_id=self.lead_id)
        insert_activity("Email", subject="Follow-up", contact_id=contact_id, lead_id=self.lead_id)
        self.assertEqual(len(get_activities_by_contact(contact_id)), 2)

        delete_contact(contact_id)
        self.assertEqual(len(get_activities_by_contact(contact_id)), 0)
        self.assertEqual(len(get_activities_by_lead(self.lead_id)), 0)

    def test_activity_insert_and_lead_ordering(self):
        from database.connection import get_connection
        from database.models import insert_contact, insert_activity, get_activities_by_lead

        contact_id = insert_contact(first_name="Jane", last_name="Doe", lead_id=self.lead_id)
        old_id = insert_activity("Call", subject="Old call", contact_id=contact_id,
                                 lead_id=self.lead_id, logged_by="alice")
        new_id = insert_activity("Meeting", subject="New meeting", contact_id=contact_id,
                                 lead_id=self.lead_id, logged_by="bob")

        # Force distinct activity dates so ordering is deterministic
        conn = get_connection()
        conn.execute("UPDATE activities SET activity_date = '2026-01-01 09:00:00' WHERE id = ?", (old_id,))
        conn.execute("UPDATE activities SET activity_date = '2026-06-15 09:00:00' WHERE id = ?", (new_id,))
        conn.commit()
        conn.close()

        activities = get_activities_by_lead(self.lead_id)
        self.assertEqual(len(activities), 2)
        # Newest first
        self.assertEqual(activities.iloc[0]["id"], new_id)
        self.assertEqual(activities.iloc[0]["subject"], "New meeting")
        self.assertEqual(activities.iloc[1]["id"], old_id)
        # Contact names joined in
        self.assertEqual(activities.iloc[0]["contact_first_name"], "Jane")
        self.assertEqual(activities.iloc[0]["contact_last_name"], "Doe")

    def test_get_activities_by_lead_limit(self):
        from database.models import insert_activity, get_activities_by_lead
        for i in range(5):
            insert_activity("Call", subject=f"Call {i}", lead_id=self.lead_id)
        self.assertEqual(len(get_activities_by_lead(self.lead_id, limit=3)), 3)

    def test_get_recent_activities_join_columns(self):
        from database.models import insert_contact, insert_activity, get_recent_activities

        contact_id = insert_contact(first_name="Jane", last_name="Doe", lead_id=self.lead_id)
        insert_activity("Call", subject="Intro", contact_id=contact_id, lead_id=self.lead_id)
        insert_activity("Note", subject="Unlinked note")

        recent = get_recent_activities(limit=20)
        self.assertEqual(len(recent), 2)
        for col in ["lead_name", "contact_first_name", "contact_last_name"]:
            self.assertIn(col, recent.columns)
        linked = recent[recent["subject"] == "Intro"].iloc[0]
        self.assertEqual(linked["lead_name"], "Test Lead")
        self.assertEqual(linked["contact_first_name"], "Jane")

    def test_clear_all_data_clears_new_tables(self):
        from database.models import (
            insert_contact, insert_activity, clear_all_data, get_table_counts,
        )
        contact_id = insert_contact(first_name="Jane", lead_id=self.lead_id)
        insert_activity("Call", contact_id=contact_id, lead_id=self.lead_id)

        counts = get_table_counts()
        self.assertIn("contacts", counts)
        self.assertIn("activities", counts)
        self.assertEqual(counts["contacts"], 1)
        self.assertEqual(counts["activities"], 1)

        clear_all_data()
        counts = get_table_counts()
        self.assertEqual(counts["contacts"], 0)
        self.assertEqual(counts["activities"], 0)
        self.assertEqual(counts["leads"], 0)
        self.assertEqual(counts["customers"], 0)


if __name__ == "__main__":
    unittest.main()
