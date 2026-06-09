"""HTTP routes for the fet-cl REST service."""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError

from app.api.jobs import Job, JobManager
from app.api.schemas import (
    HealthStatus,
    JobCreated,
    JobState,
    JobStatus,
    VersionInfo,
)
from app.core.config import Settings, get_settings
from app.fet.options import FetOptions
from app.fet.version import get_fet_cl_version

router = APIRouter()


def get_manager(request: Request) -> JobManager:
    return request.app.state.job_manager


def _require_job(manager: JobManager, job_id: str) -> Job:
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job


@router.get("/healthz", response_model=HealthStatus, tags=["meta"])
async def healthz() -> HealthStatus:
    return HealthStatus()


@router.get("/version", response_model=VersionInfo, tags=["meta"])
async def version(settings: Settings = Depends(get_settings)) -> VersionInfo:
    return VersionInfo(
        api_version=settings.api_version,
        fet_cl_version=get_fet_cl_version(settings.fet_cl_binary),
    )


@router.get(
    "/options/schema",
    tags=["meta"],
    summary="JSON Schema of the fet-cl options accepted by POST /jobs",
)
async def options_schema() -> dict:
    """The full validated option set (the `options` form field of POST /jobs).

    Multipart form fields can't carry a typed JSON body in OpenAPI, so this
    endpoint exposes the `FetOptions` JSON Schema for discoverability.
    """
    return FetOptions.model_json_schema()


@router.post(
    "/jobs",
    response_model=JobCreated,
    status_code=202,
    tags=["jobs"],
    summary="Create a timetable generation job",
)
async def create_job(
    file: UploadFile = File(..., description="The .fet input file."),
    options: Optional[str] = Form(
        default=None,
        description="JSON object of fet-cl options (see FetOptions schema).",
    ),
    manager: JobManager = Depends(get_manager),
    settings: Settings = Depends(get_settings),
) -> JobCreated:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds max upload size of {settings.max_upload_bytes} bytes.",
        )

    try:
        parsed = json.loads(options) if options else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid options JSON: {exc}")
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=422, detail="options must be a JSON object.")

    try:
        fet_options = FetOptions.model_validate(parsed)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())

    job = manager.create_job(file.filename or "input.fet", content, fet_options)
    return JobCreated(id=job.id, state=job.state)


@router.get("/jobs", response_model=list[JobStatus], tags=["jobs"])
async def list_jobs(manager: JobManager = Depends(get_manager)) -> list[JobStatus]:
    return [job.to_status() for job in manager.list()]


@router.get("/jobs/{job_id}", response_model=JobStatus, tags=["jobs"])
async def get_job(job_id: str, manager: JobManager = Depends(get_manager)) -> JobStatus:
    return _require_job(manager, job_id).to_status()


@router.get(
    "/jobs/{job_id}/result",
    tags=["jobs"],
    summary="Download all generated outputs as a zip archive",
    responses={200: {"content": {"application/zip": {}}}},
)
async def get_result(job_id: str, manager: JobManager = Depends(get_manager)) -> Response:
    job = _require_job(manager, job_id)
    if not job.result_available:
        raise HTTPException(
            status_code=409,
            detail=f"No result available; job state is '{job.state.value}'.",
        )
    data = manager.result_zip(job)
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{job.id}-result.zip"'
        },
    )


@router.get(
    "/jobs/{job_id}/logs",
    tags=["jobs"],
    summary="Raw fet-cl stdout / result.txt",
    responses={200: {"content": {"text/plain": {}}}},
)
async def get_logs(job_id: str, manager: JobManager = Depends(get_manager)) -> Response:
    job = _require_job(manager, job_id)
    if job.result is None:
        raise HTTPException(
            status_code=409,
            detail=f"No logs yet; job state is '{job.state.value}'.",
        )
    body = job.result.stdout or ""
    if job.result.stderr:
        body += "\n--- stderr ---\n" + job.result.stderr
    return Response(content=body, media_type="text/plain")


@router.delete("/jobs/{job_id}", status_code=204, tags=["jobs"])
async def delete_job(job_id: str, manager: JobManager = Depends(get_manager)) -> Response:
    job = _require_job(manager, job_id)
    await manager.cancel(job)
    manager.delete(job)
    return Response(status_code=204)
