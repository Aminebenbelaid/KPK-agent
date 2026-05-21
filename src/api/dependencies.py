from fastapi import Header, HTTPException
from src.config import get_settings


def require_internal_api_key(x_internal_api_key: str = Header(...)):
    settings = get_settings()
    if x_internal_api_key != settings.INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
