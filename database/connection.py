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
