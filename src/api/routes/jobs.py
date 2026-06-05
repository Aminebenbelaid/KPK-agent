from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from src.database import get_db

router = APIRouter(prefix="/api")

SORT_OPTIONS = {
    "match_score_desc": "match_score DESC",
    "match_score_asc": "match_score ASC",
    "created_at_desc": "created_at DESC",
    "created_at_asc": "created_at ASC",
    "title_asc": "json_extract(job_data, '$.title') ASC",
    "company_asc": "json_extract(job_data, '$.company') ASC",
}


@router.get("/jobs")
def list_jobs(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sort: str = Query("match_score_desc"),
    source: Optional[str] = None,
    remote_type: Optional[str] = None,
    min_match: Optional[float] = None,
    search: Optional[str] = None,
):
    order_clause = SORT_OPTIONS.get(sort, "match_score DESC")

    base_cte = """
        WITH best AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY job_id
                       ORDER BY match_score DESC, updated_at DESC
                   ) as rn
            FROM applications
        )
        SELECT * FROM best WHERE rn = 1
    """

    conditions = []
    params = []

    if source:
        conditions.append("json_extract(job_data, '$.source') = ?")
        params.append(source)
    if remote_type:
        conditions.append("json_extract(job_data, '$.remote_type') = ?")
        params.append(remote_type)
    if min_match is not None:
        conditions.append("match_score >= ?")
        params.append(min_match)
    if search:
        conditions.append(
            "(json_extract(job_data, '$.title') LIKE ? OR json_extract(job_data, '$.company') LIKE ?)"
        )
        params.extend([f"%{search}%", f"%{search}%"])

    where_clause = ""
    if conditions:
        where_clause = " AND " + " AND ".join(conditions)

    count_query = f"""
        WITH best AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY job_id
                       ORDER BY match_score DESC, updated_at DESC
                   ) as rn
            FROM applications
        )
        SELECT COUNT(*) as total FROM best WHERE rn = 1{where_clause}
    """

    data_query = f"""
        WITH best AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY job_id
                       ORDER BY match_score DESC, updated_at DESC
                   ) as rn
            FROM applications
        )
        SELECT * FROM best WHERE rn = 1{where_clause}
        ORDER BY {order_clause}
        LIMIT ? OFFSET ?
    """

    with get_db() as conn:
        total_row = conn.execute(count_query, params).fetchone()
        total = total_row["total"] if total_row else 0

        rows = conn.execute(data_query, params + [limit, offset]).fetchall()
        for row in rows:
            row.pop("rn", None)

    return {"items": rows, "total": total, "limit": limit, "offset": offset}


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    with get_db() as conn:
        row = conn.execute(
            """
            WITH best AS (
                SELECT *,
                       ROW_NUMBER() OVER (
                           PARTITION BY job_id
                           ORDER BY match_score DESC, updated_at DESC
                       ) as rn
                FROM applications
                WHERE job_id = ?
            )
            SELECT * FROM best WHERE rn = 1
            """,
            (job_id,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    row.pop("rn", None)
    return row


@router.delete("/jobs")
def delete_jobs(source: Optional[str] = None):
    """Delete all tracked jobs, or only those from a given source."""
    with get_db() as conn:
        if source:
            cur = conn.execute(
                "DELETE FROM applications WHERE json_extract(job_data, '$.source') = ?",
                (source,),
            )
        else:
            cur = conn.execute("DELETE FROM applications")
        deleted = cur.rowcount
    return {"deleted": deleted, "source": source}


@router.delete("/jobs/{job_id}")
def delete_job(job_id: str):
    """Delete a single tracked job by its job_id."""
    with get_db() as conn:
        cur = conn.execute("DELETE FROM applications WHERE job_id = ?", (job_id,))
        deleted = cur.rowcount
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"deleted": deleted, "job_id": job_id}
