# fet-cl-rest — Containerized REST service for FET

**Date:** 2026-06-09
**Status:** Approved (design decisions confirmed via brainstorming)

## Goal

Expose the full capabilities of `fet-cl` — the command-line interface of FET
(Free Timetabling Software, https://lalescu.ro/liviu/fet) — as a containerized
REST service that also publishes OpenAPI 3.1 and Swagger UI.

## Confirmed decisions

| Decision | Choice |
|----------|--------|
| Stack | Python + FastAPI (auto OpenAPI 3.1 + Swagger UI + ReDoc) |
| Job model | Async jobs + polling |
| Input | Upload `.fet` file + typed JSON options |
| FET install | Build from source, CLI-only (`-DCOMMAND_LINE_ONLY=ON`) |

## Architecture (three isolated layers)

### 1. FET binary layer
`fet-cl` 7.8.6 built from upstream source with `-DCOMMAND_LINE_ONLY=ON` in a
multi-stage Dockerfile. Upstream is **unmodified** — we wrap it as a separate
program (subprocess), which keeps the AGPLv3 obligation simple: we link to the
exact source used and never patch FET itself.

### 2. Wrapper core (`app/fet/`) — pure Python, no web dependencies
- **`options.py`** — `FetOptions` Pydantic model mapping fet-cl's core flags
  (`timelimitseconds`, `htmllevel`, `language`, `verbose`, the six
  `randomseeds*`, the `writetimetables*` family, `exportcsv` + CSV options,
  HTML print toggles) plus a generic `extra_flags: dict[str, str]` passthrough
  for the long per-view formatting families. `to_args()` builds the
  `--name=value` argv fragment. `inputfile`/`outputdir` are **server-managed**
  and not part of this model.
- **`runner.py`** — `FetRunner` builds argv, runs `fet-cl` as a subprocess in a
  per-job temp dir, and **parses stdout / `logs/result.txt`** to classify the
  outcome. Exit codes are coarse (0 for success *and* impossible *and* timeout;
  1 only for arg/setup errors), so classification is driven by stdout strings:
  `Generation successful` → `success`, `Impossible` → `impossible`,
  `Time exceeded` / `Generation interrupted` → `timeout`. Reads
  `soft_conflicts.txt` for the soft-cost summary.
- **`outputs.py`** — zips the results tree (`timetables/NAME/`, `logs/`, and the
  partial `-current`/`-highest` dirs on failure) for download.

### 3. Web layer (`app/api/`, FastAPI)
- **`schemas.py`** — request/response Pydantic models (job creation, job status,
  outcome summary).
- **`jobs.py`** — `JobManager`: an `asyncio` worker pool with a concurrency cap
  (`MAX_CONCURRENT_JOBS`), an in-memory job registry, per-job temp workdirs
  under `JOBS_DIR`. Cancellation sends `SIGTERM` so FET dumps partial timetables.
- **`routes.py`** — the endpoints.

## API surface

| Method · Path | Purpose |
|---------------|---------|
| `POST /jobs` | multipart: `.fet` file + JSON `options` → `{id, status}` (202) |
| `GET /jobs` | list jobs |
| `GET /jobs/{id}` | status + parsed summary |
| `GET /jobs/{id}/result` | stream `result.zip` of all outputs |
| `GET /jobs/{id}/logs` | raw fet-cl stdout / result.txt |
| `DELETE /jobs/{id}` | cancel (SIGTERM) / cleanup |
| `GET /version` | fet-cl version + API version |
| `GET /healthz` | liveness |
| `GET /docs`, `/redoc`, `/openapi.json` | Swagger UI + ReDoc + OpenAPI 3.1 |

## Job lifecycle

`queued → running → (success | impossible | timeout | error)`

`impossible` and `timeout` are **terminal job states, not HTTP errors** — the run
executed fine, FET simply could not satisfy all hard constraints in the given
time. Outputs (including partial timetables) are still available.

## Error handling

- Input validation → 422 (Pydantic).
- fet-cl arg/setup failure (exit 1) → job state `error`, details in logs.
- Missing job → 404.
- Result requested before job finished → 409.

## State

Job state is intentionally **ephemeral** (in-memory registry + temp dirs);
restart clears jobs. Persistent storage (Redis/DB, object store for outputs) is a
documented future extension point, out of scope for the scaffold.

## Testing

- `test_options.py` — argv building, boolean rendering, extra_flags validation.
- `test_runner.py` — outcome classification against captured stdout fixtures
  (success/impossible/timeout) — no binary required. One `@pytest.mark.integration`
  test runs real `fet-cl` on a tiny `.fet` when the binary is present.
- `test_api.py` — endpoints via FastAPI `TestClient` with a fake runner.

## Layout

```
app/{api,fet,core}/   tests/   Dockerfile   docker-compose.yml
pyproject.toml   README.md   NOTICE   examples/sample.fet
```
