"""Shared test fixtures: a fake fet-cl runner and a TestClient."""

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.jobs import JobManager
from app.core.config import Settings
from app.fet.options import FetOptions
from app.fet.runner import Outcome, RunResult


class FakeRunner:
    """Stand-in for FetRunner that writes a tiny output tree, no binary needed.

    The outcome can be steered by the uploaded file's contents:
    a file containing 'IMPOSSIBLE' or 'TIMEOUT' yields that outcome.
    """

    def __init__(self, *_, **__):
        pass

    async def run(self, input_file: Path, workdir: Path,
                  options: FetOptions, on_process=None) -> RunResult:
        await asyncio.sleep(0)  # yield control so the task is schedulable
        output_dir = workdir / "output"
        name = input_file.stem
        tt_dir = output_dir / "timetables" / name
        tt_dir.mkdir(parents=True, exist_ok=True)
        (tt_dir / "index.html").write_text("<html>timetable</html>")
        (tt_dir / "soft_conflicts.txt").write_text("Total soft cost: 0")
        logs = output_dir / "logs"
        logs.mkdir(parents=True, exist_ok=True)

        text = input_file.read_text("utf-8", "replace").upper()
        if "IMPOSSIBLE" in text:
            outcome, stdout = Outcome.IMPOSSIBLE, "Impossible"
        elif "TIMEOUT" in text:
            outcome, stdout = Outcome.TIMEOUT, "Time exceeded"
        else:
            outcome, stdout = Outcome.SUCCESS, "Generation successful"
        (logs / "result.txt").write_text(stdout)

        return RunResult(
            outcome=outcome,
            exit_code=0,
            stdout=stdout,
            stderr="",
            output_dir=output_dir,
            timetable_dir=tt_dir,
            soft_conflicts="Total soft cost: 0",
            placed_activities=42,
        )


@pytest.fixture
def client(tmp_path):
    # Import here so any env overrides apply before the app reads settings.
    from app.main import app

    settings = Settings(jobs_dir=tmp_path / "jobs", max_concurrent_jobs=2)
    with TestClient(app) as c:
        # Replace the lifespan-created manager with one using the fake runner.
        app.state.job_manager = JobManager(settings, runner=FakeRunner())
        yield c


def poll_until_terminal(client, job_id, attempts=50):
    terminal = {"success", "impossible", "timeout", "error", "cancelled"}
    for _ in range(attempts):
        resp = client.get(f"/jobs/{job_id}")
        state = resp.json()["state"]
        if state in terminal:
            return resp.json()
    return client.get(f"/jobs/{job_id}").json()
