"""Auto-create database tables on first run, and migrate older schemas."""
import json
import sqlite3
from pathlib import Path
from src.config import get_settings

OWNER_SID = "owner"


def _has_column(conn, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def _migrate_sessions(conn):
    """Add session scoping to pre-session databases. Existing data -> owner."""
    for table in ("applications", "experiences", "search_history"):
        if not _has_column(conn, table, "session_id"):
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN session_id TEXT NOT NULL DEFAULT '{OWNER_SID}'"
            )

    # job_id uniqueness is now per session
    conn.execute("DROP INDEX IF EXISTS idx_applications_job_id")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_apps_session_job "
        "ON applications(session_id, job_id)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_apps_session ON applications(session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_exps_session ON experiences(session_id)")

    # prompt add-ons used to live in the global settings table -> move to owner scope
    for key in ("cv_instructions", "cover_letter_instructions"):
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row and row[0]:
            conn.execute(
                "INSERT OR IGNORE INTO session_settings (session_id, key, value) VALUES (?, ?, ?)",
                (OWNER_SID, key, row[0]),
            )
        conn.execute("DELETE FROM settings WHERE key = ?", (key,))

    # profile used to live in a YAML file -> move to the owner profile row
    existing = conn.execute(
        "SELECT 1 FROM profiles WHERE session_id = ?", (OWNER_SID,)
    ).fetchone()
    if not existing:
        path = Path(get_settings().USER_PROFILE_PATH)
        data = {}
        if path.exists():
            try:
                import yaml
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except Exception:  # noqa: BLE001 - best-effort migration
                data = {}
        conn.execute(
            "INSERT INTO profiles (session_id, data) VALUES (?, ?)",
            (OWNER_SID, json.dumps(data)),
        )


def init_database():
    settings = get_settings()
    db_path = Path(settings.TRACKER_DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS applications (
        id TEXT PRIMARY KEY,
        job_id TEXT NOT NULL,
        job_data JSON NOT NULL,
        cv_path TEXT,
        cv_variant TEXT,
        cover_letter_path TEXT,
        cover_letter_template TEXT,
        status TEXT NOT NULL DEFAULT 'wishlist',
        status_history JSON DEFAULT '[]',
        applied_date TEXT,
        follow_up_date TEXT,
        last_contact_date TEXT,
        recruiter_name TEXT,
        recruiter_email TEXT,
        recruiter_linkedin TEXT,
        response_received INTEGER DEFAULT 0,
        response_date TEXT,
        interview_count INTEGER DEFAULT 0,
        offer_received INTEGER DEFAULT 0,
        offer_details TEXT,
        match_score REAL,
        match_details JSON,
        notes TEXT DEFAULT '',
        tags JSON DEFAULT '[]',
        session_id TEXT NOT NULL DEFAULT 'owner',
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS search_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        query TEXT NOT NULL,
        location TEXT NOT NULL,
        sources_used JSON,
        results_count INTEGER,
        new_jobs_count INTEGER,
        execution_time_seconds REAL,
        session_id TEXT NOT NULL DEFAULT 'owner',
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS experiences (
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL DEFAULT 'job',
        title TEXT NOT NULL,
        organization TEXT DEFAULT '',
        description TEXT DEFAULT '',
        stack JSON DEFAULT '[]',
        start_date TEXT,
        end_date TEXT,
        ai_summary TEXT DEFAULT '',
        ai_tags JSON DEFAULT '[]',
        source TEXT NOT NULL DEFAULT 'manual',
        sort_order INTEGER DEFAULT 0,
        session_id TEXT NOT NULL DEFAULT 'owner',
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        is_owner INTEGER NOT NULL DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')),
        last_seen TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS profiles (
        session_id TEXT PRIMARY KEY,
        data JSON NOT NULL DEFAULT '{}',
        updated_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS session_settings (
        session_id TEXT NOT NULL,
        key TEXT NOT NULL,
        value TEXT NOT NULL DEFAULT '',
        updated_at TEXT DEFAULT (datetime('now')),
        PRIMARY KEY (session_id, key)
    );
    """)
    _migrate_sessions(conn)
    conn.commit()
    conn.close()
