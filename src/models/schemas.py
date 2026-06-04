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


class SearchHistoryCreate(BaseModel):
    query: str
    location: str
    sources_used: Optional[List[str]] = None
    results_count: Optional[int] = None
    new_jobs_count: Optional[int] = None
    execution_time_seconds: Optional[float] = None


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    location: Optional[str] = None
    target_roles: Optional[List[str]] = None
    skills: Optional[List[str]] = None
    experience_years: Optional[int] = None
    languages: Optional[List[str]] = None
    preferred_remote_type: Optional[str] = None
    min_salary: Optional[float] = None
    notes: Optional[str] = None


class ScoreRunRequest(BaseModel):
    only_unscored: bool = False
    use_llm: bool = True


class ExperienceBase(BaseModel):
    kind: str = "job"  # 'job' | 'project'
    title: str
    organization: Optional[str] = ""
    description: Optional[str] = ""
    stack: List[str] = Field(default_factory=list)
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class ExperienceCreate(ExperienceBase):
    source: str = "manual"
    ai_summary: Optional[str] = None
    ai_tags: Optional[List[str]] = None


class ExperienceUpdate(BaseModel):
    kind: Optional[str] = None
    title: Optional[str] = None
    organization: Optional[str] = None
    description: Optional[str] = None
    stack: Optional[List[str]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    ai_summary: Optional[str] = None
    ai_tags: Optional[List[str]] = None


class CVParseRequest(BaseModel):
    text: str


class CVConfirmRequest(BaseModel):
    experiences: List[ExperienceCreate]
    replace_existing: bool = False


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
