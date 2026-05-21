from fastapi import APIRouter
from src.database import get_db
from src.models.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check():
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(DISTINCT job_id) as cnt FROM applications").fetchone()
        count = row["cnt"] if row else 0
    return {"status": "ok", "jobs_count": count}
