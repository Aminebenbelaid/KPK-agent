"""Global serial work queue for heavy operations (scrape, score, generate).

The server is a small desktop box, so all expensive work — scraping runs,
scoring passes, CV/cover-letter generation, CV parsing — goes through ONE
worker. Requests enqueue a job and immediately get a task id + queue position;
clients poll ``/api/queue/{id}`` until it finishes.
"""
from __future__ import annotations

import queue
import threading
import traceback
import uuid
from datetime import datetime, timezone

_q: "queue.Queue[str]" = queue.Queue()
_tasks: dict[str, dict] = {}
_fns: dict[str, callable] = {}
_order: list[str] = []          # submission order, for position calculation
_lock = threading.Lock()
_started = False

MAX_TASKS_KEPT = 500


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def submit(kind: str, fn, sid: str = "", label: str = "") -> dict:
    """Enqueue fn() for serial execution. Returns {task_id, status, position}."""
    tid = uuid.uuid4().hex[:10]
    with _lock:
        _tasks[tid] = {
            "task_id": tid, "kind": kind, "sid": sid, "label": label,
            "status": "queued", "submitted_at": _now(),
            "started_at": None, "finished_at": None,
            "result": None, "error": None,
        }
        _fns[tid] = fn
        _order.append(tid)
        # bound memory
        while len(_order) > MAX_TASKS_KEPT:
            old = _order.pop(0)
            if _tasks.get(old, {}).get("status") in ("done", "failed"):
                _tasks.pop(old, None)
                _fns.pop(old, None)
    _q.put(tid)
    return {"task_id": tid, "status": "queued", "position": position(tid)}


def position(tid: str) -> int:
    """1-based position in line; 0 when running or finished."""
    with _lock:
        task = _tasks.get(tid)
        if not task or task["status"] != "queued":
            return 0
        ahead = 1
        for other in _order:
            if other == tid:
                break
            st = _tasks.get(other, {}).get("status")
            if st in ("queued", "running"):
                ahead += 1
        return ahead


def status(tid: str) -> dict | None:
    with _lock:
        task = _tasks.get(tid)
        if not task:
            return None
        out = dict(task)
    out["position"] = position(tid)
    return out


def queue_overview() -> dict:
    with _lock:
        queued = sum(1 for t in _tasks.values() if t["status"] == "queued")
        running = [t["kind"] for t in _tasks.values() if t["status"] == "running"]
    return {"queued": queued, "running": running[0] if running else None}


def _worker():
    while True:
        tid = _q.get()
        with _lock:
            task = _tasks.get(tid)
            fn = _fns.get(tid)
        if not task or not fn:
            continue
        task["status"] = "running"
        task["started_at"] = _now()
        try:
            task["result"] = fn()
            task["status"] = "done"
        except Exception as e:  # noqa: BLE001 - report to poller, keep worker alive
            task["status"] = "failed"
            task["error"] = str(e) or e.__class__.__name__
            traceback.print_exc()
        finally:
            task["finished_at"] = _now()
            with _lock:
                _fns.pop(tid, None)


def start_worker():
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_worker, daemon=True).start()
