import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from src.api.router import api_router
from src.config import get_settings
from src.init_db import init_database
from src import sessions, task_queue

DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard" / "dist"


def create_app() -> FastAPI:
    init_database()
    task_queue.start_worker()
    sessions.start_cleanup_thread()

    app = FastAPI(title="keinplankarriere", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def session_middleware(request: Request, call_next):
        sid = request.cookies.get(sessions.COOKIE_NAME, "")
        fresh = False
        if not sessions.is_valid(sid):
            sid = sessions.create_session()
            fresh = True
        request.state.sid = sid
        request.state.effective_sid = sessions.effective_sid(sid)
        sessions.touch(sid)
        response = await call_next(request)
        if fresh:
            response.set_cookie(
                sessions.COOKIE_NAME, sid,
                max_age=sessions.COOKIE_MAX_AGE,
                httponly=True, samesite="lax", path="/",
            )
        # Never let browsers/proxies cache the SPA shell: after a redeploy a stale
        # index.html would point at hashed bundles that no longer exist.
        ctype = response.headers.get("content-type", "")
        if "text/html" in ctype:
            response.headers["Cache-Control"] = "no-cache"
        return response

    app.include_router(api_router)

    if DASHBOARD_DIR.exists():
        app.mount("/", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="spa")

    return app


app = create_app()

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run("src.main:app", host=settings.HOST, port=settings.PORT, reload=True)
