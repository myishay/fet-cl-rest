"""End-to-end API tests using a fake fet-cl runner."""

import io
import json
import zipfile

from tests.conftest import poll_until_terminal


def _upload(client, content=b"<fet></fet>", options=None, filename="data.fet"):
    files = {"file": (filename, io.BytesIO(content), "application/xml")}
    data = {}
    if options is not None:
        data["options"] = json.dumps(options)
    return client.post("/jobs", files=files, data=data)


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_openapi_and_swagger_exposed(client):
    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    body = spec.json()
    assert body["openapi"].startswith("3.")
    assert "/jobs" in body["paths"]
    assert client.get("/docs").status_code == 200   # Swagger UI
    assert client.get("/redoc").status_code == 200   # ReDoc
    # The full fet-cl option set is browsable in the schema.
    assert "FetOptions" in body["components"]["schemas"]


def test_options_schema_endpoint(client):
    resp = client.get("/options/schema")
    assert resp.status_code == 200
    props = resp.json()["properties"]
    assert "timelimitseconds" in props
    assert "extra_flags" in props


def test_create_job_returns_202(client):
    resp = _upload(client)
    assert resp.status_code == 202
    body = resp.json()
    assert body["state"] in {"queued", "running", "success"}
    assert body["id"]


def test_job_reaches_success(client):
    job_id = _upload(client).json()["id"]
    status = poll_until_terminal(client, job_id)
    assert status["state"] == "success"
    assert status["result_available"] is True
    assert status["summary"]["placed_activities"] == 42


def test_impossible_is_terminal_not_error(client):
    job_id = _upload(client, content=b"<fet>IMPOSSIBLE</fet>").json()["id"]
    status = poll_until_terminal(client, job_id)
    assert status["state"] == "impossible"
    assert status["result_available"] is True


def test_options_are_validated(client):
    resp = _upload(client, options={"htmllevel": 99})
    assert resp.status_code == 422


def test_invalid_options_json_rejected(client):
    files = {"file": ("data.fet", io.BytesIO(b"<fet></fet>"), "application/xml")}
    resp = client.post("/jobs", files=files, data={"options": "{not json"})
    assert resp.status_code == 422


def test_empty_file_rejected(client):
    resp = _upload(client, content=b"")
    assert resp.status_code == 422


def test_result_zip_download(client):
    job_id = _upload(client).json()["id"]
    poll_until_terminal(client, job_id)
    resp = client.get(f"/jobs/{job_id}/result")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = zf.namelist()
    assert any("index.html" in n for n in names)


def test_result_before_finished_conflict(client):
    # A still-running job (no result yet) returns 409 on /result. Inject a job
    # directly so no background task can race it to a terminal state.
    from pathlib import Path

    from app.api.jobs import Job
    from app.api.schemas import JobState
    from app.fet.options import FetOptions
    from app.main import app

    manager = app.state.job_manager
    job = Job(id="stuck", filename="data.fet", workdir=Path("/tmp"),
              options=FetOptions(), state=JobState.RUNNING)
    manager._jobs["stuck"] = job

    resp = client.get("/jobs/stuck/result")
    assert resp.status_code == 409


def test_logs_endpoint(client):
    job_id = _upload(client).json()["id"]
    poll_until_terminal(client, job_id)
    resp = client.get(f"/jobs/{job_id}/logs")
    assert resp.status_code == 200
    assert "successful" in resp.text.lower()


def test_list_jobs(client):
    _upload(client)
    _upload(client)
    resp = client.get("/jobs")
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


def test_get_missing_job_404(client):
    assert client.get("/jobs/does-not-exist").status_code == 404


def test_delete_job(client):
    job_id = _upload(client).json()["id"]
    poll_until_terminal(client, job_id)
    assert client.delete(f"/jobs/{job_id}").status_code == 204
    assert client.get(f"/jobs/{job_id}").status_code == 404
