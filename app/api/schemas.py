"""Request/response models for the REST API."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from app.fet.options import FetOptions


class JobState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    IMPOSSIBLE = "impossible"
    TIMEOUT = "timeout"
    ERROR = "error"
    CANCELLED = "cancelled"


#: Terminal states — the job will not change further.
TERMINAL_STATES = {
    JobState.SUCCESS, JobState.IMPOSSIBLE, JobState.TIMEOUT,
    JobState.ERROR, JobState.CANCELLED,
}

#: States for which a result archive exists (full or partial timetables).
RESULT_AVAILABLE_STATES = {
    JobState.SUCCESS, JobState.IMPOSSIBLE, JobState.TIMEOUT,
}


class CreateJobOptions(BaseModel):
    """JSON body part of ``POST /jobs`` (the file is the other part)."""

    options: FetOptions = Field(default_factory=FetOptions)


class OutcomeSummary(BaseModel):
    placed_activities: Optional[int] = Field(
        default=None, description="Activities FET managed to place."
    )
    soft_conflicts: Optional[str] = Field(
        default=None, description="Soft-constraint conflict report, if any."
    )
    warnings: list[str] = Field(default_factory=list)
    exit_code: Optional[int] = None


class JobStatus(BaseModel):
    id: str
    state: JobState
    filename: str
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    summary: Optional[OutcomeSummary] = None
    error: Optional[str] = Field(
        default=None, description="Failure detail when state is 'error'."
    )
    result_available: bool = False


class JobCreated(BaseModel):
    id: str
    state: JobState


class VersionInfo(BaseModel):
    api_version: str
    fet_cl_version: str


class HealthStatus(BaseModel):
    status: str = "ok"
