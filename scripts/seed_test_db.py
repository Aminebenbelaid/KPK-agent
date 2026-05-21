"""Create a test database with seed data for development."""
import sqlite3
import json
import uuid
from datetime import datetime

DB_PATH = "data/tracker.db"

conn = sqlite3.connect(DB_PATH)
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
""")

now = datetime.utcnow().isoformat()

for i in range(5):
    job_id = f"linkedin-test-{i:04d}"
    job_data = json.dumps({
        "id": job_id,
        "title": f"Software Engineer {i}",
        "company": f"TestCorp {i}",
        "location": "Berlin, Germany",
        "source": "linkedin",
        "url": f"https://linkedin.com/jobs/{i}",
        "remote_type": "remote" if i % 2 == 0 else "on-site",
        "match_score": 75.0 + i * 5,
        "skills_required": ["Python", "FastAPI"],
        "technologies": ["Python"],
        "experience_level": "entry",
        "job_type": "full-time",
    })
    conn.execute(
        "INSERT INTO applications (id, job_id, job_data, match_score, status, created_at, updated_at) VALUES (?, ?, ?, ?, 'wishlist', ?, ?)",
        (str(uuid.uuid4()), job_id, job_data, 75.0 + i * 5, now, now),
    )

# Duplicate row for linkedin-test-0000 (lower score)
conn.execute(
    "INSERT INTO applications (id, job_id, job_data, match_score, status, created_at, updated_at) VALUES (?, ?, ?, ?, 'wishlist', ?, ?)",
    (str(uuid.uuid4()), "linkedin-test-0000",
     json.dumps({"id": "linkedin-test-0000", "title": "Software Engineer 0 DUP", "company": "TestCorp 0", "source": "linkedin"}),
     70.0, now, now),
)

# Row with 0-1 scale score
conn.execute(
    "INSERT INTO applications (id, job_id, job_data, match_score, status, created_at, updated_at) VALUES (?, ?, ?, ?, 'wishlist', ?, ?)",
    (str(uuid.uuid4()), "remotive-test-0001",
     json.dumps({"id": "remotive-test-0001", "title": "Remote Dev", "company": "RemoteCo", "source": "remotive", "remote_type": "remote"}),
     0.85, now, now),
)

conn.commit()

total = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
unique = conn.execute("SELECT COUNT(DISTINCT job_id) FROM applications").fetchone()[0]
print(f"Rows: {total}")
print(f"Unique jobs: {unique}")
print(f"Duplicates: {total - unique}")
conn.close()
print("Database created successfully")
