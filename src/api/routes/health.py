from fastapi import APIRouter, Request
from src.database import get_db
from src.models.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check(request: Request):
    sid = getattr(request.state, "effective_sid", "owner")
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(DISTINCT job_id) as cnt FROM applications WHERE session_id = ?",
            (sid,),
        ).fetchone()
        count = row["cnt"] if row else 0
    return {"status": "ok", "jobs_count": count}
