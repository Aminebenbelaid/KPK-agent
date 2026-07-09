"""Per-visitor sessions: cookie-based workspaces with an owner escape hatch.

Every browser gets its own isolated workspace (jobs, experiences, profile,
prompt add-ons, generated documents), keyed by a cookie. The pre-existing data
belongs to the special session id ``owner``; any session that presents the
ADMIN_KEY is flagged as owner and reads/writes that workspace.

Idle visitor sessions are pruned (rows + generated files) after IDLE_HOURS.
"""
from __future__ import annotations

import os
import re
import json
import time
import uuid
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path

from src.config import get_settings
from src.database import get_db

COOKIE_NAME = "kpk_session"
OWNER_SID = "owner"
IDLE_HOURS = 48
COOKIE_MAX_AGE = 60 * 60 * 24 * 60  # 60 days

# in-memory caches to keep the per-request overhead tiny
_known: set[str] = set()
_owners: set[str] = set()
_last_touch: dict[str, float] = {}
_lock = threading.Lock()

_SID_RE = re.compile(r"^[a-f0-9]{32}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def admin_key() -> str:
    return os.environ.get("ADMIN_KEY", "") or ""


def create_session() -> str:
    sid = uuid.uuid4().hex
    with get_db() as conn:
        conn.execute(
            "INSERT INTO sessions (id, is_owner, created_at, last_seen) VALUES (?, 0, ?, ?)",
            (sid, _now(), _now()),
        )
    with _lock:
        _known.add(sid)
        _last_touch[sid] = time.time()
    return sid


def is_valid(sid: str) -> bool:
    if not sid or not _SID_RE.match(sid):
        return False
    with _lock:
        if sid in _known:
            return True
    with get_db() as conn:
        row = conn.execute("SELECT id, is_owner FROM sessions WHERE id = ?", (sid,)).fetchone()
    if not row:
        return False
    with _lock:
        _known.add(sid)
        if row["is_owner"]:
            _owners.add(sid)
    return True


def touch(sid: str):
    """Update last_seen, throttled to once per 5 minutes per session."""
    now = time.time()
    with _lock:
        if now - _last_touch.get(sid, 0) < 300:
            return
        _last_touch[sid] = now
    with get_db() as conn:
        conn.execute("UPDATE sessions SET last_seen = ? WHERE id = ?", (_now(), sid))


def is_owner(sid: str) -> bool:
    with _lock:
        return sid in _owners


def effective_sid(sid: str) -> str:
    return OWNER_SID if is_owner(sid) else sid


def claim_owner(sid: str, key: str) -> bool:
    expected = admin_key()
    if not expected or key != expected:
        return False
    with get_db() as conn:
        conn.execute("UPDATE sessions SET is_owner = 1 WHERE id = ?", (sid,))
    with _lock:
        _owners.add(sid)
    return True


def release_owner(sid: str):
    with get_db() as conn:
        conn.execute("UPDATE sessions SET is_owner = 0 WHERE id = ?", (sid,))
    with _lock:
        _owners.discard(sid)


# ── cleanup of idle visitor workspaces ──

def _session_dir(sid: str) -> Path:
    return Path(get_settings().TRACKER_DB_PATH).parent / "cv" / "sessions" / sid


def _purge_session(conn, sid: str):
    """Delete a visitor session's rows and generated files. Never touches owner."""
    if sid == OWNER_SID:
        return
    app_ids = [r["id"] for r in conn.execute(
        "SELECT id FROM applications WHERE session_id = ?", (sid,)
    ).fetchall()]
    gen_root = Path(get_settings().TRACKER_DB_PATH).parent / "cv" / "generated"
    for app_id in app_ids:
        shutil.rmtree(gen_root / app_id, ignore_errors=True)
    shutil.rmtree(_session_dir(sid), ignore_errors=True)
    for table in ("applications", "experiences", "search_history",
                  "session_settings", "profiles"):
        conn.execute(f"DELETE FROM {table} WHERE session_id = ?", (sid,))
    conn.execute("DELETE FROM sessions WHERE id = ?", (sid,))
    with _lock:
        _known.discard(sid)
        _owners.discard(sid)
        _last_touch.pop(sid, None)


def cleanup_idle_sessions():
    """Prune non-owner sessions idle longer than IDLE_HOURS."""
    cutoff = datetime.now(timezone.utc).timestamp() - IDLE_HOURS * 3600
    with get_db() as conn:
        rows = conn.execute("SELECT id, is_owner, last_seen FROM sessions").fetchall()
        for row in rows:
            if row["is_owner"]:
                continue
            try:
                seen = datetime.fromisoformat(row["last_seen"]).timestamp()
            except (ValueError, TypeError):
                seen = 0
            if seen < cutoff:
                _purge_session(conn, row["id"])


def start_cleanup_thread():
    def loop():
        while True:
            time.sleep(3600)
            try:
                cleanup_idle_sessions()
            except Exception:  # noqa: BLE001 - cleanup must never kill the app
                pass
    threading.Thread(target=loop, daemon=True).start()
