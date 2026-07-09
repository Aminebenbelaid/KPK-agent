"""Per-session candidate profile (preferences), stored in the profiles table."""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from src.database import get_db
from src.models.schemas import ProfileUpdate

router = APIRouter(prefix="/api")

DEFAULT_PROFILE = {
    "name": "",
    "email": "",
    "location": "",
    "target_roles": [],
    "skills": [],
    "experience_years": 0,
    "languages": [],
    "preferred_remote_type": "",
    "min_salary": None,
    "notes": "",
}


def load_profile(sid: str) -> dict:
    with get_db() as conn:
        row = conn.execute(
            "SELECT data FROM profiles WHERE session_id = ?", (sid,)
        ).fetchone()
    merged = dict(DEFAULT_PROFILE)
    if row and isinstance(row.get("data"), dict):
        merged.update(row["data"])
    return merged


def save_profile(sid: str, data: dict):
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO profiles (session_id, data, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
            (sid, json.dumps(data), now),
        )


@router.get("/profile")
def get_profile(request: Request):
    return load_profile(request.state.effective_sid)


@router.put("/profile")
def update_profile(request: Request, update: ProfileUpdate):
    sid = request.state.effective_sid
    current = load_profile(sid)
    patch = {k: v for k, v in update.model_dump().items() if v is not None}
    current.update(patch)
    save_profile(sid, current)
    return current
