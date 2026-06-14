# fet-cl-rest

A containerized **REST service** that exposes the full capabilities of
[`fet-cl`](https://lalescu.ro/liviu/fet) — the command line of **FET, Free
Timetabling Software** — with auto-generated **OpenAPI 3.1**, **Swagger UI**,
and **ReDoc**.

Upload a `.fet` problem file, pick generation options, and poll an async job for
the solved timetables (HTML / XML / CSV), packaged as a downloadable zip.

> FET is licensed **AGPL-3.0**. This service wraps the **unmodified** upstream
> `fet-cl` binary as a separate subprocess. See [`NOTICE`](./NOTICE) — if you run
> this over a network you must offer users the corresponding FET source.

## Quick start (Docker)

```bash
git clone https://github.com/myishay/fet-cl-rest.git
cd fet-cl-rest

# Pulls the published image from GHCR (ghcr.io/myishay/fet-cl-rest)
docker compose up
# ...or build the image locally: uncomment the `build:` block in
# docker-compose.yml, then run `docker compose up --build`

# Swagger UI:   http://localhost:8000/docs
# ReDoc:        http://localhost:8000/redoc
# OpenAPI JSON: http://localhost:8000/openapi.json
```

Submit a job and download the result:

```bash
# Create a job (async): returns {"id": "...", "state": "queued"}
JOB=$(curl -s -F "file=@examples/sample.fet" \
            -F 'options={"timelimitseconds":30,"htmllevel":4}' \
            http://localhost:8000/jobs | python -c "import sys,json;print(json.load(sys.stdin)['id'])")

# Poll status until terminal (success | impossible | timeout | error)
curl -s http://localhost:8000/jobs/$JOB | python -m json.tool

# Download all generated timetables
curl -s -o result.zip http://localhost:8000/jobs/$JOB/result
```

## API

| Method · Path | Purpose |
|---------------|---------|
| `POST /jobs` | multipart: `.fet` `file` + JSON `options` → `{id, state}` (202) |
| `GET /jobs` | list jobs |
| `GET /jobs/{id}` | status + summary (placed activities, soft cost, warnings) |
| `GET /jobs/{id}/result` | stream `result.zip` of all outputs |
| `GET /jobs/{id}/logs` | raw fet-cl stdout / `result.txt` |
| `DELETE /jobs/{id}` | cancel (SIGTERM → partial timetables) and remove |
| `GET /version` | fet-cl version + API version |
| `GET /healthz` | liveness probe |
| `GET /docs`, `/redoc`, `/openapi.json` | Swagger UI / ReDoc / OpenAPI 3.1 |

### Job states

`queued → running → success | impossible | timeout | error | cancelled`

`impossible` and `timeout` are **normal terminal outcomes, not HTTP errors** —
FET ran fine but could not satisfy every hard constraint within the time limit.
Partial timetables are still available in the result archive.

### Options

The JSON `options` body maps directly to `fet-cl` flags via the `FetOptions`
schema (browse it in Swagger). Core fields include `timelimitseconds`,
`htmllevel` (0–7), `language`, `verbose`, the six `randomseeds*` (for
reproducible runs), the `writetimetables*` family, HTML print toggles, and CSV
export options. Anything not modelled explicitly can be passed through
`extra_flags` (a `name → value` map) to retain full parity with the CLI:

```json
{
  "timelimitseconds": 120,
  "exportcsv": true,
  "fieldseparatorcsv": "semicolon",
  "extra_flags": { "printroomscomments": "true" }
}
```

`inputfile` and `outputdir` are managed by the service and cannot be set.

## Configuration

Environment variables (prefix `FETREST_`):

| Variable | Default | Meaning |
|----------|---------|---------|
| `FETREST_FET_CL_BINARY` | `fet-cl` | Path to the fet-cl binary |
| `FETREST_JOBS_DIR` | `/tmp/fet-cl-rest/jobs` | Per-job workdirs |
| `FETREST_MAX_CONCURRENT_JOBS` | `4` | Worker-pool concurrency cap |
| `FETREST_MAX_UPLOAD_BYTES` | `26214400` | Max `.fet` upload size (25 MiB) |
| `FETREST_HARD_TIMEOUT_BUFFER_SECONDS` | `60` | Wall-clock guard above fet-cl's own limit |

## Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                       # unit + API tests (no binary needed)
pytest -m integration        # also runs real fet-cl, if on PATH
uvicorn app.main:app --reload
```

## Architecture

Three isolated layers:

1. **FET binary** — `fet-cl` built from upstream source, CLI-only, in a
   multi-stage Dockerfile.
2. **Wrapper core** (`app/fet/`) — pure Python: `FetOptions` (typed flags),
   `FetRunner` (subprocess + stdout outcome classification), output zipping.
   No web dependencies.
3. **Web layer** (`app/api/`) — FastAPI routes + an in-memory, semaphore-bounded
   async `JobManager`.

Job state is **ephemeral** (in-memory registry + temp dirs); a restart clears
jobs. Persistent storage is a deliberate, documented extension point.

See [`docs/superpowers/specs/2026-06-09-fet-cl-rest-design.md`](docs/superpowers/specs/2026-06-09-fet-cl-rest-design.md)
for the full design.

## License & compliance

This project is licensed **AGPL-3.0-or-later** — see [`LICENSE`](./LICENSE) for
the full text and [`NOTICE`](./NOTICE) for attribution. It wraps the
**unmodified** upstream `fet-cl` binary (FET, also AGPL-3.0) as a separate
subprocess.

Operator notes (a summary, not legal advice):

- **Building the image** downloads FET's source from a pinned upstream URL
  (`FET_VERSION` / `FET_URL` build args) and builds it unmodified.
- **Distributing the image** conveys the `fet-cl` binary (**AGPL-3.0**); its
  corresponding source is the pinned upstream release recorded in `NOTICE`. The
  `LICENSE` and `NOTICE` files are baked into the image (`/srv`) so they travel
  with it.
