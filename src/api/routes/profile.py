import os
from typing import Optional
import yaml
from fastapi import APIRouter, HTTPException
from src.config import get_settings

router = APIRouter(prefix="/api")

_profile_cache: Optional[dict] = None
_profile_mtime: float = 0.0


@router.get("/profile")
def get_profile():
    global _profile_cache, _profile_mtime
    settings = get_settings()
    path = settings.USER_PROFILE_PATH

    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="User profile not found")

    mtime = os.path.getmtime(path)
    if _profile_cache is None or mtime != _profile_mtime:
        with open(path, "r", encoding="utf-8") as f:
            _profile_cache = yaml.safe_load(f)
        _profile_mtime = mtime

    return _profile_cache
