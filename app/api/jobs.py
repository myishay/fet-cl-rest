"""In-memory job manager with a bounded asyncio worker pool.

Each job gets a temp workdir under ``settings.jobs_dir`` containing the uploaded
``.fet`` file and the ``output/`` tree fet-cl writes. State is ephemeral: a
restart clears the registry (documented; persistence is a future extension).
"""

from __future__ import annotations

import asyncio
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.core.config import Settings
from app.fet.options import FetOptions
from app.fet.outputs import zip_directory
from app.fet.runner import FetRunner, Outcome, RunResult
from app.api.schemas import (
    JobState,
    JobStatus,
    OutcomeSummary,
    RESULT_AVAILABLE_STATES,
)

_OUTCOME_TO_STATE = {
    Outcome.SUCCESS: JobState.SUCCESS,
    Outcome.IMPOSSIBLE: JobState.IMPOSSIBLE,
    Outcome.TIMEOUT: JobState.TIMEOUT,
    Outcome.ERROR: JobState.ERROR,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Job:
    id: str
    filename: str
    workdir: Path
    options: FetOptions
    state: JobState = JobState.QUEUED
    created_at: datetime = field(default_factory=_now)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    result: Optional[RunResult] = None
    error: Optional[str] = None
    _process: Optional["asyncio.subprocess.Process"] = None
    _task: Optional[asyncio.Task] = None

    @property
    def input_file(self) -> Path:
        return self.workdir / self.filename

    @property
    def result_available(self) -> bool:
        return (
            self.state in RESULT_AVAILABLE_STATES
            and self.result is not None
            and self.result.output_dir.is_dir()
        )

    def to_status(self) -> JobStatus:
        summary = None
        if self.result is not None:
            summary = OutcomeSummary(
                placed_activities=self.result.placed_activities,
                soft_conflicts=self.result.soft_conflicts,
                warnings=self.result.warnings,
                exit_code=self.result.exit_code,
            )
        return JobStatus(
            id=self.id,
            state=self.state,
            filename=self.filename,
            created_at=self.created_at,
            started_at=self.started_at,
            finished_at=self.finished_at,
            summary=summary,
            error=self.error,
            result_available=self.result_available,
        )


class JobManager:
    """Owns the job registry and a semaphore-bounded worker pool."""

    def __init__(self, settings: Settings, runner: Optional[FetRunner] = None):
        self.settings = settings
        self.runner = runner or FetRunner(
            binary=settings.fet_cl_binary,
            hard_timeout_buffer=settings.hard_timeout_buffer_seconds,
        )
        self._jobs: dict[str, Job] = {}
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_jobs)
        settings.jobs_dir.mkdir(parents=True, exist_ok=True)

    def create_job(self, filename: str, content: bytes,
                   options: FetOptions) -> Job:
        job_id = uuid.uuid4().hex
        workdir = self.settings.jobs_dir / job_id
        workdir.mkdir(parents=True, exist_ok=True)
        safe_name = _safe_filename(filename)
        (workdir / safe_name).write_bytes(content)

        job = Job(id=job_id, filename=safe_name, workdir=workdir, options=options)
        self._jobs[job_id] = job
        job._task = asyncio.create_task(self._run_job(job))
        return job

    async def _run_job(self, job: Job) -> None:
        async with self._semaphore:
            if job.state == JobState.CANCELLED:
                return
            job.state = JobState.RUNNING
            job.started_at = _now()
            try:
                result = await self.runner.run(
                    input_file=job.input_file,
                    workdir=job.workdir,
                    options=job.options,
                    on_process=lambda p: setattr(job, "_process", p),
                )
                job.result = result
                if job.state != JobState.CANCELLED:
                    job.state = _OUTCOME_TO_STATE.get(result.outcome, JobState.ERROR)
                    if job.state == JobState.ERROR and not job.error:
                        job.error = (result.stderr or result.stdout or "").strip()[:2000]
            except asyncio.CancelledError:
                job.state = JobState.CANCELLED
                raise
            except Exception as exc:  # noqa: BLE001 - surfaced to the caller
                job.state = JobState.ERROR
                job.error = f"{type(exc).__name__}: {exc}"
            finally:
                job.finished_at = _now()

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    async def cancel(self, job: Job) -> None:
        """Cancel a job. SIGTERM lets fet-cl dump partial timetables first."""
        if job.state in {JobState.QUEUED, JobState.RUNNING}:
            job.state = JobState.CANCELLED
            if job._process is not None:
                FetRunner._terminate(job._process)
            if job._task is not None:
                job._task.cancel()

    def delete(self, job: Job) -> None:
        self._jobs.pop(job.id, None)
        shutil.rmtree(job.workdir, ignore_errors=True)

    def result_zip(self, job: Job) -> bytes:
        assert job.result is not None
        return zip_directory(job.result.output_dir)

    async def shutdown(self) -> None:
        for job in list(self._jobs.values()):
            if job._task is not None and not job._task.done():
                await self.cancel(job)


def _safe_filename(name: str) -> str:
    """Reduce an uploaded filename to a safe basename ending in ``.fet``."""
    base = Path(name).name.strip() or "input.fet"
    base = base.replace("/", "_").replace("\\", "_")
    if not base.lower().endswith(".fet"):
        base += ".fet"
    return base
