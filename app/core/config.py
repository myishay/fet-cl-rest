"""Service configuration, sourced from environment variables.

All settings carry sensible defaults so the service runs with zero config in the
container; override any of them with the ``FETREST_`` prefix, e.g.
``FETREST_MAX_CONCURRENT_JOBS=8``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FETREST_", env_file=".env")

    fet_cl_binary: str = "fet-cl"
    jobs_dir: Path = Path("/tmp/fet-cl-rest/jobs")
    max_concurrent_jobs: int = 4
    max_upload_bytes: int = 25 * 1024 * 1024  # 25 MiB
    hard_timeout_buffer_seconds: int = 60
    api_version: str = "0.1.0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
