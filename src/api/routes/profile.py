import os
from typing import Optional
import yaml
from fastapi import APIRouter
from src.config import get_settings
from src.models.schemas import ProfileUpdate

router = APIRouter(prefix="/api")

_profile_cache: Optional[dict] = None
_profile_mtime: float = 0.0

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


def load_profile() -> dict:
    """Load the profile from disk (with caching), returning defaults if missing."""
    global _profile_cache, _profile_mtime
    path = get_settings().USER_PROFILE_PATH

    if not os.path.exists(path):
        return dict(DEFAULT_PROFILE)

    mtime = os.path.getmtime(path)
    if _profile_cache is None or mtime != _profile_mtime:
        with open(path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
        merged = dict(DEFAULT_PROFILE)
        merged.update(loaded)
        _profile_cache = merged
        _profile_mtime = mtime

    return _profile_cache


@router.get("/profile")
def get_profile():
    return load_profile()


@router.put("/profile")
def update_profile(update: ProfileUpdate):
    global _profile_cache, _profile_mtime
    path = get_settings().USER_PROFILE_PATH

    current = load_profile()
    patch = {k: v for k, v in update.model_dump().items() if v is not None}
    current.update(patch)

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(current, f, allow_unicode=True, sort_keys=False)

    # Refresh cache from the freshly written file.
    _profile_cache = current
    _profile_mtime = os.path.getmtime(path)
    return current
