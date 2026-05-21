from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class ApplicationStatus(str, Enum):
    wishlist = "wishlist"
    ready = "ready"
    applied = "applied"
    phone_screen = "phone_screen"
    interview = "interview"
    technical_test = "technical_test"
    onsite = "onsite"
    offer = "offer"
    accepted = "accepted"
    declined = "declined"
    rejected = "rejected"
    withdrawn = "withdrawn"


class JobPosting(BaseModel):
    id: str
    title: str
    company: str
    location: Optional[str] = None
    source: str
    url: Optional[str] = None
    description_raw: Optional[str] = None
    description_clean: Optional[str] = None
    posted_date: Optional[str] = None
    scraped_date: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: str = "EUR"
    job_type: Optional[str] = "full-time"
    remote_type: Optional[str] = "on-site"
    skills_required: List[str] = Field(default_factory=list)
    experience_level: Optional[str] = None
    technologies: List[str] = Field(default_factory=list)
    is_duplicate: bool = False
    quality_score: float = 0.0
    match_score: Optional[float] = None


class JobUpsertRequest(BaseModel):
    id: str
    title: str
    company: str
    location: Optional[str] = None
    source: str
    url: Optional[str] = None
    description_raw: Optional[str] = None
    description_clean: Optional[str] = None
    posted_date: Optional[str] = None
    scraped_date: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: str = "EUR"
    job_type: Optional[str] = "full-time"
    remote_type: Optional[str] = "on-site"
    skills_required: List[str] = Field(default_factory=list)
    experience_level: Optional[str] = None
    technologies: List[str] = Field(default_factory=list)
    is_duplicate: bool = False
    quality_score: float = 0.0
    match_score: Optional[float] = None


class BatchUpsertRequest(BaseModel):
    jobs: List[JobUpsertRequest]


class BatchUpsertResponse(BaseModel):
    inserted: int
    updated: int
    errors: List[str] = Field(default_factory=list)


class ApplicationUpdate(BaseModel):
    status: Optional[ApplicationStatus] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None


class ScoreUpdate(BaseModel):
    match_score: float
    match_details: Optional[dict] = None


class SearchHistoryCreate(BaseModel):
    query: str
    location: str
    sources_used: Optional[List[str]] = None
    results_count: Optional[int] = None
    new_jobs_count: Optional[int] = None
    execution_time_seconds: Optional[float] = None


class PaginatedResponse(BaseModel):
    items: List[dict]
    total: int
    limit: int
    offset: int


class ScrapeRequest(BaseModel):
    scrapers: Optional[List[str]] = None
    parallel: bool = False
    query: Optional[str] = None
    location: Optional[str] = None


class ScrapeStatusResponse(BaseModel):
    task_id: str
    status: str
    scrapers: List[str]


class HealthResponse(BaseModel):
    status: str
    jobs_count: int
