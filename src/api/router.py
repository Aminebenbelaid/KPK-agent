from fastapi import APIRouter
from src.api.routes import (
    health, jobs, applications, profile, internal, settings, matching, experiences, generate,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(jobs.router)
api_router.include_router(applications.router)
api_router.include_router(profile.router)
api_router.include_router(matching.router)
api_router.include_router(experiences.router)
api_router.include_router(generate.router)
api_router.include_router(settings.router)
api_router.include_router(internal.router)
api_router.include_router(internal.public_router)
