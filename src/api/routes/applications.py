import json
from datetime import datetime, timezone
from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from src.database import get_db
from src.models.schemas import ApplicationUpdate, ApplicationStatus

router = APIRouter(prefix="/api")


@router.get("/applications")
def list_applications(
    status: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    conditions = []
    params = []

    if status:
        conditions.append("status = ?")
        params.append(status)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    with get_db() as conn:
        total_row = conn.execute(
            f"SELECT COUNT(*) as total FROM applications {where_clause}", params
        ).fetchone()
        total = total_row["total"] if total_row else 0

        rows = conn.execute(
            f"SELECT * FROM applications {where_clause} ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()

    return {"items": rows, "total": total, "limit": limit, "offset": offset}


@router.get("/applications/stats/summary")
def application_stats():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) as count FROM applications GROUP BY status"
        ).fetchall()

    result = {s.value: 0 for s in ApplicationStatus}
    for row in rows:
        result[row["status"]] = row["count"]
    return result


@router.patch("/applications/{application_id}")
def update_application(application_id: str, update: ApplicationUpdate):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM applications WHERE id = ?", (application_id,)
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Application not found")

        updates = []
        params = []

        if update.status is not None:
            old_status = row["status"]
            new_status = update.status.value

            history = row.get("status_history") or []
            if isinstance(history, str):
                history = json.loads(history)
            history.append({
                "from": old_status,
                "to": new_status,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            updates.append("status = ?")
            params.append(new_status)
            updates.append("status_history = ?")
            params.append(json.dumps(history))

            if new_status == "applied" and not row.get("applied_date"):
                updates.append("applied_date = ?")
                params.append(datetime.now(timezone.utc).isoformat())

        if update.notes is not None:
            updates.append("notes = ?")
            params.append(update.notes)

        if update.tags is not None:
            updates.append("tags = ?")
            params.append(json.dumps(update.tags))

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        updates.append("updated_at = ?")
        params.append(datetime.now(timezone.utc).isoformat())
        params.append(application_id)

        conn.execute(
            f"UPDATE applications SET {', '.join(updates)} WHERE id = ?", params
        )

        updated = conn.execute(
            "SELECT * FROM applications WHERE id = ?", (application_id,)
        ).fetchone()

    return updated
