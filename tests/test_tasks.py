"""Tests for the task management data layer."""

import os
import sys
import unittest
import tempfile
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import config


class TestTasks(unittest.TestCase):
    """Test task CRUD, filtering, and due-date windows with a temporary database."""

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
        """Start each test from a clean slate with a lead, contact, and deal."""
        from database.connection import seed_pipeline_stages
        from database.models import (
            clear_all_data, insert_lead, insert_contact, insert_deal,
            get_pipeline_stages,
        )
        clear_all_data()
        seed_pipeline_stages()
        self.lead_id = insert_lead(
            name="Test Lead", address="100 Main St", city="Denver", state="CO",
            zip_code="80202", latitude=39.74, longitude=-104.99,
            business_type="Restaurant", segment="Full-Service Restaurant",
        )
        self.contact_id = insert_contact(
            first_name="Jane", last_name="Doe", lead_id=self.lead_id,
        )
        stages = get_pipeline_stages()
        self.stage_id = int(stages.loc[stages["name"] == "Prospect", "id"].iloc[0])
        self.deal_id = insert_deal(
            name="Test Deal", stage_id=self.stage_id, lead_id=self.lead_id,
        )

    @staticmethod
    def _db_today():
        """Return SQLite's date('now') as a Python date (avoids TZ mismatch)."""
        from database.connection import get_connection
        conn = get_connection()
        today_str = conn.execute("SELECT date('now')").fetchone()[0]
        conn.close()
        return date.fromisoformat(today_str)

    @staticmethod
    def _offset(base, days):
        """Return an ISO date string `days` from `base`."""
        return (base + timedelta(days=days)).isoformat()

    def test_insert_and_get_round_trip_with_joins(self):
        from database.models import insert_task, get_all_tasks, get_task

        task_id = insert_task(
            title="Call about proposal", description="Discuss pricing",
            task_type="Call", priority="High", assigned_to="alice",
            due_date="2026-08-01", lead_id=self.lead_id,
            contact_id=self.contact_id, deal_id=self.deal_id,
            created_by="bob",
        )
        self.assertIsInstance(task_id, int)

        tasks = get_all_tasks()
        self.assertEqual(len(tasks), 1)
        row = tasks.iloc[0]
        self.assertEqual(row["title"], "Call about proposal")
        self.assertEqual(row["description"], "Discuss pricing")
        self.assertEqual(row["task_type"], "Call")
        self.assertEqual(row["priority"], "High")
        self.assertEqual(row["status"], "Open")
        self.assertEqual(row["assigned_to"], "alice")
        self.assertEqual(row["due_date"], "2026-08-01")
        self.assertEqual(row["created_by"], "bob")
        # Joined display columns
        self.assertEqual(row["lead_name"], "Test Lead")
        self.assertEqual(row["contact_first_name"], "Jane")
        self.assertEqual(row["contact_last_name"], "Doe")
        self.assertEqual(row["deal_name"], "Test Deal")

        # Defaults
        minimal_id = insert_task(title="Minimal")
        task = get_task(minimal_id)
        self.assertEqual(task["task_type"], "Follow-up")
        self.assertEqual(task["priority"], "Medium")
        self.assertEqual(task["status"], "Open")
        self.assertIsNone(task["due_date"])
        self.assertIsNone(task["completed_at"])

    def test_include_completed_filtering(self):
        from database.models import insert_task, update_task_status, get_all_tasks

        insert_task(title="Open task")
        insert_task(title="In progress task")
        completed = insert_task(title="Completed task")
        cancelled = insert_task(title="Cancelled task")
        update_task_status(completed, "Completed")
        update_task_status(cancelled, "Cancelled")

        open_tasks = get_all_tasks()
        self.assertEqual(len(open_tasks), 2)
        self.assertNotIn("Completed task", set(open_tasks["title"]))
        self.assertNotIn("Cancelled task", set(open_tasks["title"]))

        all_tasks = get_all_tasks(include_completed=True)
        self.assertEqual(len(all_tasks), 4)

    def test_get_tasks_by_lead_and_deal(self):
        from database.models import (
            insert_task, update_task_status, get_tasks_by_lead, get_tasks_by_deal,
        )

        insert_task(title="Lead task", lead_id=self.lead_id)
        done = insert_task(title="Lead done", lead_id=self.lead_id)
        update_task_status(done, "Completed")
        insert_task(title="Deal task", deal_id=self.deal_id)
        insert_task(title="Unlinked task")

        lead_tasks = get_tasks_by_lead(self.lead_id)
        self.assertEqual(list(lead_tasks["title"]), ["Lead task"])
        lead_tasks = get_tasks_by_lead(self.lead_id, include_completed=True)
        self.assertEqual(len(lead_tasks), 2)

        deal_tasks = get_tasks_by_deal(self.deal_id)
        self.assertEqual(list(deal_tasks["title"]), ["Deal task"])
        self.assertEqual(deal_tasks.iloc[0]["deal_name"], "Test Deal")
        self.assertEqual(len(get_tasks_by_deal(999999)), 0)

    def test_due_date_windows(self):
        from database.models import (
            insert_task, update_task_status,
            get_overdue_tasks, get_tasks_due_today, get_tasks_due_this_week,
        )
        today = self._db_today()

        insert_task(title="Overdue", due_date=self._offset(today, -3))
        overdue_done = insert_task(title="Overdue completed",
                                   due_date=self._offset(today, -3))
        update_task_status(overdue_done, "Completed")
        insert_task(title="Due today", due_date=self._offset(today, 0))
        insert_task(title="Due in 5 days", due_date=self._offset(today, 5))
        insert_task(title="Due at week edge", due_date=self._offset(today, 7))
        insert_task(title="Due in 10 days", due_date=self._offset(today, 10))
        insert_task(title="No due date")

        overdue = get_overdue_tasks()
        self.assertEqual(set(overdue["title"]), {"Overdue"})

        due_today = get_tasks_due_today()
        self.assertEqual(set(due_today["title"]), {"Due today"})

        due_week = get_tasks_due_this_week()
        self.assertEqual(
            set(due_week["title"]),
            {"Due today", "Due in 5 days", "Due at week edge"},
        )

    def test_get_all_tasks_ordering(self):
        from database.models import insert_task, get_all_tasks

        insert_task(title="No date", priority="Urgent")
        insert_task(title="Later date", due_date="2026-09-01")
        insert_task(title="Early date low", due_date="2026-08-01", priority="Low")
        insert_task(title="Early date urgent", due_date="2026-08-01", priority="Urgent")

        tasks = get_all_tasks()
        self.assertEqual(
            list(tasks["title"]),
            ["Early date urgent", "Early date low", "Later date", "No date"],
        )

    def test_update_task_status_sets_and_clears_completed_at(self):
        from database.models import insert_task, update_task_status, get_task

        task_id = insert_task(title="Task")
        task = get_task(task_id)
        self.assertIsNone(task["completed_at"])
        first_updated_at = task["updated_at"]

        update_task_status(task_id, "Completed")
        task = get_task(task_id)
        self.assertEqual(task["status"], "Completed")
        self.assertIsNotNone(task["completed_at"])
        self.assertGreaterEqual(task["updated_at"], first_updated_at)

        update_task_status(task_id, "Open")
        task = get_task(task_id)
        self.assertEqual(task["status"], "Open")
        self.assertIsNone(task["completed_at"])

    def test_update_task_allowlist(self):
        from database.models import insert_task, update_task, get_task

        task_id = insert_task(title="Task")
        update_task(
            task_id, title="Renamed", description="desc", task_type="Meeting",
            priority="Urgent", status="In Progress", assigned_to="carol",
            due_date="2026-08-15",
        )
        task = get_task(task_id)
        self.assertEqual(task["title"], "Renamed")
        self.assertEqual(task["description"], "desc")
        self.assertEqual(task["task_type"], "Meeting")
        self.assertEqual(task["priority"], "Urgent")
        self.assertEqual(task["status"], "In Progress")
        self.assertEqual(task["assigned_to"], "carol")
        self.assertEqual(task["due_date"], "2026-08-15")

        with self.assertRaises(ValueError):
            update_task(task_id, lead_id=self.lead_id)
        with self.assertRaises(ValueError):
            update_task(task_id, completed_at="2026-01-01")
        with self.assertRaises(ValueError):
            update_task(task_id, bogus_column="x")

    def test_count_open_tasks_by_deal(self):
        from database.models import (
            insert_task, insert_deal, update_task_status, count_open_tasks_by_deal,
        )
        other_deal = insert_deal(name="Other Deal", stage_id=self.stage_id)

        insert_task(title="A", deal_id=self.deal_id)
        insert_task(title="B", deal_id=self.deal_id)
        done = insert_task(title="C", deal_id=self.deal_id)
        update_task_status(done, "Completed")
        insert_task(title="D", deal_id=other_deal)
        insert_task(title="No deal")

        counts = count_open_tasks_by_deal()
        by_deal = counts.set_index("deal_id")["open_task_count"]
        self.assertEqual(by_deal[self.deal_id], 2)
        self.assertEqual(by_deal[other_deal], 1)
        self.assertEqual(len(counts), 2)  # unlinked task not counted

    def test_delete_task(self):
        from database.models import insert_task, delete_task, get_task, get_all_tasks

        task_id = insert_task(title="Doomed")
        keep_id = insert_task(title="Keeper")
        delete_task(task_id)
        self.assertIsNone(get_task(task_id))
        self.assertIsNotNone(get_task(keep_id))
        self.assertEqual(list(get_all_tasks()["title"]), ["Keeper"])

    def test_clear_all_data_covers_tasks(self):
        from database.models import insert_task, clear_all_data, get_table_counts

        insert_task(title="Task", lead_id=self.lead_id, deal_id=self.deal_id)
        counts = get_table_counts()
        self.assertIn("tasks", counts)
        self.assertEqual(counts["tasks"], 1)

        clear_all_data()
        counts = get_table_counts()
        self.assertEqual(counts["tasks"], 0)
        self.assertEqual(counts["deals"], 0)
        self.assertEqual(counts["leads"], 0)


if __name__ == "__main__":
    unittest.main()
