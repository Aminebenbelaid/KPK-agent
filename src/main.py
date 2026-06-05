import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from src.api.router import api_router
from src.config import get_settings
from src.init_db import init_database

DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard" / "dist"


def create_app() -> FastAPI:
    init_database()

    app = FastAPI(title="keinplankarriere", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    if DASHBOARD_DIR.exists():
        app.mount("/", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="spa")

    return app


app = create_app()

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run("src.main:app", host=settings.HOST, port=settings.PORT, reload=True)
