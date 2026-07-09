"""Settings: global LLM credentials (owner-only) + per-session prompt add-ons."""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from src.database import get_db
from src import sessions

router = APIRouter(prefix="/api")

# Server-wide keys — only the owner session may read or change these.
GLOBAL_KEYS = {"kisski_api_key", "kisski_base_url", "llm_model"}
# Per-session keys — every visitor manages their own.
SESSION_KEYS = {"cv_instructions", "cover_letter_instructions"}


class SettingsBulkUpdate(BaseModel):
    settings: dict[str, str]


def get_session_setting(sid: str, key: str) -> str:
    with get_db() as conn:
        row = conn.execute(
            "SELECT value FROM session_settings WHERE session_id = ? AND key = ?",
            (sid, key),
        ).fetchone()
    return (row["value"] if row else "") or ""


def _mask(val: str) -> str:
    if not val:
        return ""
    return val[:4] + "****" + val[-4:] if len(val) > 8 else "****"


@router.get("/settings")
def get_all_settings(request: Request):
    sid = request.state.effective_sid
    owner = sessions.is_owner(request.state.sid)
    result: dict = {"_is_owner": owner}

    with get_db() as conn:
        for key in SESSION_KEYS:
            row = conn.execute(
                "SELECT value FROM session_settings WHERE session_id = ? AND key = ?",
                (sid, key),
            ).fetchone()
            result[key] = (row["value"] if row else "") or ""

        if owner:
            for key in GLOBAL_KEYS:
                row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
                result[key] = (row["value"] if row else "") or ""
            result["kisski_api_key"] = _mask(result.get("kisski_api_key", ""))

    return result


@router.put("/settings")
def update_settings_bulk(request: Request, bulk: SettingsBulkUpdate):
    sid = request.state.effective_sid
    owner = sessions.is_owner(request.state.sid)
    now = datetime.now(timezone.utc).isoformat()
    saved = []

    with get_db() as conn:
        for key, value in bulk.settings.items():
            if key in SESSION_KEYS:
                conn.execute(
                    "INSERT INTO session_settings (session_id, key, value, updated_at) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(session_id, key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                    (sid, key, value, now),
                )
                saved.append(key)
            elif key in GLOBAL_KEYS:
                if not owner:
                    raise HTTPException(403, "Only the owner can change server settings")
                conn.execute(
                    "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                    (key, value, now),
                )
                saved.append(key)

    return {"saved": saved, "status": "ok"}
