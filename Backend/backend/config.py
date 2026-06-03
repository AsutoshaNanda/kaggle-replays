"""Application settings, loaded from ``backend/.env`` via pydantic-settings.

All secrets and tunables come from environment variables — nothing is hardcoded.
The ``.env`` file is resolved by absolute path relative to this module so that
settings load identically whether the process is started from the project root
(``uvicorn backend.main:app``) or from inside ``backend/`` (``alembic`` CLI).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/.env regardless of the current working directory.
_ENV_PATH = Path(__file__).resolve().parent / ".env"


class Settings(BaseSettings):
    """Typed application configuration.

    Attributes mirror the variables documented in ``.env.example``. Security
    primitives (algorithm, token lifetimes, session cap) are intentionally fixed
    defaults — per the project's stop conditions they must not be changed
    without explicit approval.
    """

    model_config = SettingsConfigDict(
        env_file=str(_ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # --- Database -----------------------------------------------------------
    DATABASE_URL: str

    # --- JWT / auth secrets -------------------------------------------------
    JWT_SECRET: str
    JWT_REFRESH_SECRET: str

    # --- CORS ---------------------------------------------------------------
    ALLOWED_ORIGINS: str = "http://localhost:5173"

    # --- Local dev login ----------------------------------------------------
    # When true, /auth/kaggle-login points at /auth/dev-login, which logs in
    # using the local Backend/auth.json (single-user local development only).
    # MUST be false in any real/multi-user deployment.
    DEV_LOGIN_ENABLED: bool = False

    # --- Filesystem locations ----------------------------------------------
    SESSIONS_BASE_DIR: str = "./sessions"
    DOWNLOADS_BASE_DIR: str = "./downloads"

    # --- Concurrency / lifecycle -------------------------------------------
    MAX_CONCURRENT_CONTEXTS: int = 10
    MAX_PARALLEL_DOWNLOAD_JOBS: int = 5
    JOB_OUTPUT_TTL_HOURS: float = 0.25

    # --- Logging ------------------------------------------------------------
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "./logs/backend.log"

    # --- Fixed security parameters (do NOT change without approval) ---------
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    MAX_SESSIONS_PER_USER: int = 5
    GLOBAL_RATE_LIMIT: str = "100/minute"

    @property
    def allowed_origins_list(self) -> list[str]:
        """Return ``ALLOWED_ORIGINS`` parsed into a list of clean origins."""
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def sessions_base_path(self) -> Path:
        """Absolute path to the per-user Playwright sessions directory."""
        return Path(self.SESSIONS_BASE_DIR).resolve()

    @property
    def downloads_base_path(self) -> Path:
        """Absolute path to the job output downloads directory."""
        return Path(self.DOWNLOADS_BASE_DIR).resolve()


@lru_cache
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance (single load per process)."""
    return Settings()
