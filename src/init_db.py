"""Auto-create database tables on first run."""
import sqlite3
from pathlib import Path
from src.config import get_settings


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
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS feedback_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        event_data JSON,
        user_feedback TEXT,
        rating INTEGER,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (application_id) REFERENCES applications(id)
    );
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT DEFAULT (datetime('now'))
    );
    CREATE UNIQUE INDEX IF NOT EXISTS idx_applications_job_id ON applications(job_id);
    """)
    conn.close()
