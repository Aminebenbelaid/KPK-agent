import json
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from src.database import get_db

router = APIRouter(prefix="/api")

ALLOWED_KEYS = {
    "kisski_api_key",
    "kisski_base_url",
    "llm_model",
    "internal_api_key",
    "scraper_default_location",
    "scraper_max_jobs",
}


class SettingUpdate(BaseModel):
    value: str


class SettingsBulkUpdate(BaseModel):
    settings: dict[str, str]


def _get_setting(conn, key):
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def _set_setting(conn, key, value):
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
        (key, value, now),
    )


@router.get("/settings")
def get_all_settings():
    with get_db() as conn:
        rows = conn.execute("SELECT key, value, updated_at FROM settings").fetchall()
    result = {row["key"]: row["value"] for row in rows}
    for key in ALLOWED_KEYS:
        if key not in result:
            result[key] = ""
    if "kisski_api_key" in result and result["kisski_api_key"]:
        val = result["kisski_api_key"]
        result["kisski_api_key"] = val[:4] + "****" + val[-4:] if len(val) > 8 else "****"
    if "internal_api_key" in result and result["internal_api_key"]:
        val = result["internal_api_key"]
        result["internal_api_key"] = val[:4] + "****" + val[-4:] if len(val) > 8 else "****"
    return result


@router.get("/settings/{key}")
def get_setting(key: str):
    if key not in ALLOWED_KEYS:
        raise HTTPException(400, f"Unknown setting: {key}")
    with get_db() as conn:
        value = _get_setting(conn, key)
    return {"key": key, "value": value or ""}


@router.put("/settings/{key}")
def update_setting(key: str, update: SettingUpdate):
    if key not in ALLOWED_KEYS:
        raise HTTPException(400, f"Unknown setting: {key}")
    with get_db() as conn:
        _set_setting(conn, key, update.value)
    return {"key": key, "status": "saved"}


@router.put("/settings")
def update_settings_bulk(bulk: SettingsBulkUpdate):
    saved = []
    with get_db() as conn:
        for key, value in bulk.settings.items():
            if key not in ALLOWED_KEYS:
                continue
            _set_setting(conn, key, value)
            saved.append(key)
    return {"saved": saved, "status": "ok"}
