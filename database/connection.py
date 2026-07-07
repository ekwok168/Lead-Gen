"""SQLite database connection helper."""

import os
import sqlite3

import config


def get_connection(db_path=None):
    """Get a SQLite connection with row factory enabled."""
    path = db_path or config.DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db(db_path=None):
    """Initialize database with schema."""
    conn = get_connection(db_path)
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, "r") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()


def seed_core_segments(db_path=None):
    """Insert default core segments if they don't exist."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM core_segments")
    if cursor.fetchone()[0] == 0:
        segments = [
            ("Full-Service Restaurant", "Restaurant", 500, 1),
            ("Quick-Service Restaurant", "Restaurant", 300, 2),
            ("C-Store", "Convenience Store", 400, 3),
            ("Hospitality", "Hotel", 600, 4),
        ]
        cursor.executemany(
            "INSERT INTO core_segments (segment_name, business_type, min_estimated_revenue, priority) "
            "VALUES (?, ?, ?, ?)",
            segments,
        )
        conn.commit()
    conn.close()


def seed_pipeline_stages(db_path=None):
    """Insert default pipeline stages if the table is empty."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM pipeline_stages")
    if cursor.fetchone()[0] == 0:
        cursor.executemany(
            "INSERT INTO pipeline_stages (name, display_order, probability_pct) "
            "VALUES (?, ?, ?)",
            config.DEFAULT_PIPELINE_STAGES,
        )
        conn.commit()
    conn.close()


DEFAULT_COMMUNICATION_TEMPLATES = [
    (
        "Initial Outreach",
        "email",
        "Partnering with {business_name}",
        "Hi {contact_name},\n\n"
        "My name is {salesperson_name}, and I work with a food distribution "
        "company that already delivers to several businesses in your "
        "neighborhood. Because one of our existing routes runs right by "
        "{business_name}, we can offer you reliable, frequent delivery "
        "without the usual minimums or long lead times.\n\n"
        "We supply restaurants and stores like yours with quality products "
        "at competitive prices, and our drivers are in your area every "
        "week. Adding {business_name} to the route would be simple, and "
        "I'd love to show you what that could look like for your business.\n\n"
        "Would you have 15 minutes this week for a quick call or visit? "
        "I'm happy to work around your schedule.\n\n"
        "Best regards,\n{salesperson_name}",
    ),
    (
        "Follow-up After Call",
        "email",
        "Great speaking with you, {contact_name}",
        "Hi {contact_name},\n\n"
        "Thank you for taking the time to speak with me today about "
        "{business_name}. As we discussed, our delivery route already "
        "passes close to your location, so we can offer dependable weekly "
        "service with minimal lead time.\n\n"
        "As a next step, I'll put together a tailored product and pricing "
        "overview for {business_name} and send it over shortly. If it "
        "looks good, we can schedule a quick visit to finalize the details.\n\n"
        "Talk soon,\n{salesperson_name}",
    ),
    (
        "Cold Call Script",
        "call_script",
        None,
        "OPENING:\n"
        "Hi, this is {salesperson_name}. May I speak with the owner or "
        "manager? ... Great, thanks {contact_name} — I'll keep this brief.\n\n"
        "VALUE PROPOSITION:\n"
        "I'm with a food distribution company, and one of our existing "
        "delivery routes already runs right past {business_name}. That "
        "means we can offer you frequent, reliable delivery at competitive "
        "prices — no long waits and no big order minimums, because our "
        "truck is in your area every week anyway.\n\n"
        "DISCOVERY QUESTIONS:\n"
        "- Who are you currently ordering from, and how often do they deliver?\n"
        "- Are there products you have trouble getting consistently?\n"
        "- How important are delivery timing and order minimums to you?\n"
        "- If you could change one thing about your current supplier, what "
        "would it be?\n\n"
        "CLOSE:\n"
        "Based on what you've shared, I think we could be a great fit for "
        "{business_name}. Could we set up a short visit this week so I can "
        "walk you through our catalog and pricing? What day works best for "
        "you?",
    ),
]


def seed_communication_templates(db_path=None):
    """Insert default communication templates if the table is empty."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM communication_templates")
    if cursor.fetchone()[0] == 0:
        cursor.executemany(
            "INSERT INTO communication_templates (name, template_type, subject, body) "
            "VALUES (?, ?, ?, ?)",
            DEFAULT_COMMUNICATION_TEMPLATES,
        )
        conn.commit()
    conn.close()
