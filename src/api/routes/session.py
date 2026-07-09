"""Session identity, owner claim, and work-queue status."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src import sessions, task_queue

router = APIRouter(prefix="/api")


class ClaimRequest(BaseModel):
    key: str


@router.get("/session")
def get_session(request: Request):
    sid = request.state.sid
    return {
        "is_owner": sessions.is_owner(sid),
        "workspace": "owner" if sessions.is_owner(sid) else "personal",
        "queue": task_queue.queue_overview(),
    }


@router.post("/session/claim")
def claim(request: Request, req: ClaimRequest):
    if not sessions.admin_key():
        raise HTTPException(400, "No admin key configured on the server")
    if not sessions.claim_owner(request.state.sid, req.key.strip()):
        raise HTTPException(403, "Wrong admin key")
    return {"is_owner": True}


@router.post("/session/release")
def release(request: Request):
    sessions.release_owner(request.state.sid)
    return {"is_owner": False}


@router.get("/queue/{task_id}")
def queue_status(task_id: str):
    st = task_queue.status(task_id)
    if not st:
        raise HTTPException(404, "Task not found")
    # never leak internals like sid to other visitors
    return {
        "task_id": st["task_id"], "kind": st["kind"], "status": st["status"],
        "position": st["position"], "result": st["result"], "error": st["error"],
    }
