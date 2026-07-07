"""Tests for the communications data layer (templates and emails)."""

import os
import sys
import unittest
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import config


class TestCommunications(unittest.TestCase):
    """Test template seeding/CRUD and email logging with a temporary database."""

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
        """Start each test from a clean slate with seeded templates and a lead/contact."""
        from database.connection import seed_communication_templates
        from database.models import clear_all_data, insert_lead, insert_contact
        clear_all_data()
        seed_communication_templates()
        self.lead_id = insert_lead(
            name="Test Lead", address="100 Main St", city="Denver", state="CO",
            zip_code="80202", latitude=39.74, longitude=-104.99,
            business_type="Restaurant", segment="Full-Service Restaurant",
        )
        self.contact_id = insert_contact(
            first_name="Jane", last_name="Doe", lead_id=self.lead_id,
        )

    # -- Seeding ------------------------------------------------------------

    def test_seed_defaults_present_with_placeholders(self):
        from database.models import get_all_templates

        templates = get_all_templates()
        self.assertEqual(len(templates), 3)

        by_name = {row["name"]: row for _, row in templates.iterrows()}
        self.assertEqual(
            set(by_name),
            {"Initial Outreach", "Follow-up After Call", "Cold Call Script"},
        )

        outreach = by_name["Initial Outreach"]
        self.assertEqual(outreach["template_type"], "email")
        self.assertEqual(outreach["subject"], "Partnering with {business_name}")

        followup = by_name["Follow-up After Call"]
        self.assertEqual(followup["template_type"], "email")
        self.assertEqual(
            followup["subject"], "Great speaking with you, {contact_name}"
        )

        script = by_name["Cold Call Script"]
        self.assertEqual(script["template_type"], "call_script")
        self.assertTrue(script.isna()["subject"])

        for row in by_name.values():
            self.assertIn("{business_name}", row["body"])
            self.assertIn("{contact_name}", row["body"])
            self.assertIn("{salesperson_name}", row["body"])

    def test_seed_is_idempotent(self):
        from database.connection import seed_communication_templates
        from database.models import get_all_templates

        seed_communication_templates()
        seed_communication_templates()
        self.assertEqual(len(get_all_templates()), 3)

    def test_seed_skipped_when_table_not_empty(self):
        from database.connection import seed_communication_templates
        from database.models import (
            clear_all_data, insert_template, get_all_templates,
        )

        clear_all_data()
        insert_template(name="Custom", template_type="email", body="Hello")
        seed_communication_templates()
        templates = get_all_templates()
        self.assertEqual(list(templates["name"]), ["Custom"])

    # -- Template CRUD --------------------------------------------------------

    def test_insert_and_get_template(self):
        from database.models import insert_template, get_template

        template_id = insert_template(
            name="Meeting Prep", template_type="meeting_agenda",
            body="Agenda for {business_name}", subject="Meeting agenda",
        )
        self.assertIsInstance(template_id, int)

        template = get_template(template_id)
        self.assertEqual(template["name"], "Meeting Prep")
        self.assertEqual(template["template_type"], "meeting_agenda")
        self.assertEqual(template["subject"], "Meeting agenda")
        self.assertEqual(template["body"], "Agenda for {business_name}")
        self.assertIsNotNone(template["created_at"])
        self.assertIsNotNone(template["updated_at"])

        # subject defaults to None
        minimal_id = insert_template(
            name="Script", template_type="call_script", body="Say hi",
        )
        self.assertIsNone(get_template(minimal_id)["subject"])
        self.assertIsNone(get_template(999999))

    def test_update_template_allowlist(self):
        from database.models import insert_template, update_template, get_template

        template_id = insert_template(
            name="Draft", template_type="email", body="v1", subject="s1",
        )
        first_updated_at = get_template(template_id)["updated_at"]

        update_template(
            template_id, name="Final", template_type="call_script",
            subject=None, body="v2",
        )
        template = get_template(template_id)
        self.assertEqual(template["name"], "Final")
        self.assertEqual(template["template_type"], "call_script")
        self.assertIsNone(template["subject"])
        self.assertEqual(template["body"], "v2")
        self.assertGreaterEqual(template["updated_at"], first_updated_at)

        with self.assertRaises(ValueError):
            update_template(template_id, id=42)
        with self.assertRaises(ValueError):
            update_template(template_id, created_at="2026-01-01")
        with self.assertRaises(ValueError):
            update_template(template_id, bogus_column="x")

        # No-op update is allowed
        update_template(template_id)
        self.assertEqual(get_template(template_id)["name"], "Final")

    def test_delete_template_nulls_email_references(self):
        from database.models import (
            insert_template, delete_template, get_template,
            insert_email, get_emails_by_lead, get_all_templates,
        )

        template_id = insert_template(
            name="Doomed", template_type="email", body="bye",
        )
        keep_id = insert_template(name="Keeper", template_type="email", body="hi")
        email_id = insert_email(
            subject="From template", body="hello", lead_id=self.lead_id,
            template_id=template_id,
        )

        delete_template(template_id)
        self.assertIsNone(get_template(template_id))
        self.assertIsNotNone(get_template(keep_id))
        self.assertNotIn("Doomed", set(get_all_templates()["name"]))

        emails = get_emails_by_lead(self.lead_id)
        self.assertEqual(len(emails), 1)
        row = emails.iloc[0]
        self.assertEqual(row["id"], email_id)
        self.assertTrue(row.isna()["template_id"])

    # -- Emails ---------------------------------------------------------------

    def test_insert_email_and_get_by_lead(self):
        from database.models import insert_email, get_emails_by_lead, insert_template

        template_id = insert_template(name="T", template_type="email", body="b")
        email_id = insert_email(
            subject="Hello", body="Body text", to_address="jane@example.com",
            lead_id=self.lead_id, contact_id=self.contact_id,
            template_id=template_id,
        )
        self.assertIsInstance(email_id, int)

        emails = get_emails_by_lead(self.lead_id)
        self.assertEqual(len(emails), 1)
        row = emails.iloc[0]
        self.assertEqual(row["subject"], "Hello")
        self.assertEqual(row["body"], "Body text")
        self.assertEqual(row["to_address"], "jane@example.com")
        self.assertEqual(row["status"], "Draft")
        self.assertEqual(row["contact_id"], self.contact_id)
        self.assertEqual(row["template_id"], template_id)
        self.assertTrue(row.isna()["sent_at"])
        self.assertIsNotNone(row["created_at"])
        # Joined display columns
        self.assertEqual(row["contact_first_name"], "Jane")
        self.assertEqual(row["contact_last_name"], "Doe")
        self.assertEqual(row["template_name"], "T")

        # Other leads have no emails
        self.assertEqual(len(get_emails_by_lead(999999)), 0)

    def test_get_emails_by_lead_ordering_newest_first(self):
        from database.connection import get_connection
        from database.models import insert_email, get_emails_by_lead, insert_lead

        first = insert_email(subject="First", body="b", lead_id=self.lead_id)
        second = insert_email(subject="Second", body="b", lead_id=self.lead_id)
        third = insert_email(subject="Third", body="b", lead_id=self.lead_id)
        # Backdate the first email to make created_at ordering unambiguous
        conn = get_connection()
        conn.execute(
            "UPDATE emails SET created_at = datetime('now', '-1 day') WHERE id = ?",
            (first,),
        )
        conn.commit()
        conn.close()
        # Email for a different lead must not appear
        other_lead = insert_lead(
            name="Other Lead", address="2 Oak St", city="Denver", state="CO",
            zip_code="80202", latitude=39.75, longitude=-104.98,
        )
        insert_email(subject="Other", body="b", lead_id=other_lead)

        emails = get_emails_by_lead(self.lead_id)
        self.assertEqual(list(emails["subject"]), ["Third", "Second", "First"])
        self.assertEqual(list(emails["id"]), [third, second, first])

    def test_mark_email_sent(self):
        from database.connection import get_connection
        from database.models import insert_email, mark_email_sent

        email_id = insert_email(subject="S", body="B", lead_id=self.lead_id)
        untouched_id = insert_email(subject="S2", body="B2", lead_id=self.lead_id)
        mark_email_sent(email_id)

        conn = get_connection()
        row = conn.execute("SELECT * FROM emails WHERE id = ?", (email_id,)).fetchone()
        untouched = conn.execute(
            "SELECT * FROM emails WHERE id = ?", (untouched_id,)
        ).fetchone()
        conn.close()

        self.assertEqual(row["status"], "Sent")
        self.assertIsNotNone(row["sent_at"])
        self.assertEqual(untouched["status"], "Draft")
        self.assertIsNone(untouched["sent_at"])

    # -- Utility integration ----------------------------------------------------

    def test_clear_all_data_and_counts_cover_communications(self):
        from database.models import (
            insert_email, clear_all_data, get_table_counts, get_all_templates,
        )

        insert_email(subject="S", body="B", lead_id=self.lead_id)
        counts = get_table_counts()
        self.assertIn("communication_templates", counts)
        self.assertIn("emails", counts)
        self.assertEqual(counts["communication_templates"], 3)
        self.assertEqual(counts["emails"], 1)

        clear_all_data()
        counts = get_table_counts()
        self.assertEqual(counts["communication_templates"], 0)
        self.assertEqual(counts["emails"], 0)
        self.assertEqual(counts["leads"], 0)
        self.assertEqual(len(get_all_templates()), 0)


if __name__ == "__main__":
    unittest.main()
