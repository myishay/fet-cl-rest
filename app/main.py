"""FastAPI application factory.

Wires the routes, the job manager (held on ``app.state``), and the
auto-generated OpenAPI 3.1 / Swagger UI (``/docs``) / ReDoc (``/redoc``).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.api.jobs import JobManager
from app.api.routes import router
from app.core.config import get_settings
from app.fet.options import FetOptions

DESCRIPTION = """
REST interface to **fet-cl**, the command line of
[FET — Free Timetabling Software](https://lalescu.ro/liviu/fet).

Upload a `.fet` problem file, choose generation options, and poll the resulting
job for the solved timetables.

* `POST /jobs` — submit a `.fet` file plus options (async; returns a job id)
* `GET /jobs/{id}` — poll status: `queued`, `running`, then a terminal state
  (`success`, `impossible`, `timeout`, `error`, `cancelled`)
* `GET /jobs/{id}/result` — download all generated timetables as a zip

`impossible` and `timeout` are normal terminal outcomes, not errors — FET ran
fine but could not satisfy every hard constraint in the allotted time.

FET is licensed AGPL-3.0; this service wraps the unmodified upstream binary as a
separate program. See the project `NOTICE`.
"""

TAGS_METADATA = [
    {"name": "jobs", "description": "Submit and manage timetable generation jobs."},
    {"name": "meta", "description": "Service health and version information."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.job_manager = JobManager(settings)
    try:
        yield
    finally:
        await app.state.job_manager.shutdown()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="fet-cl REST",
        version=settings.api_version,
        description=DESCRIPTION,
        openapi_tags=TAGS_METADATA,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.include_router(router)
    _customize_openapi(app, settings)
    return app


def _customize_openapi(app: FastAPI, settings) -> None:
    """Inject the FetOptions schema into components so it's browsable in Swagger.

    The `options` field of POST /jobs is a JSON string inside a multipart form,
    which FastAPI can't model as a typed body — so we add the schema manually.
    """

    def custom_openapi() -> dict:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            tags=app.openapi_tags,
            routes=app.routes,
        )
        defs = FetOptions.model_json_schema(ref_template="#/components/schemas/{model}")
        nested = defs.pop("$defs", {})
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        components.setdefault("FetOptions", defs)
        for name, definition in nested.items():
            components.setdefault(name, definition)
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi


app = create_app()
