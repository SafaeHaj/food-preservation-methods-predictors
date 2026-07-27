"""Settings every service needs: database, identity, logging, storage roots."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

#: Repository root for the deployed service (…/shared/shared/config/base.py -> parents[3]).
#: Relative storage paths resolve against this so a bare `docker compose up` works with no
#: absolute paths configured, while production mounts override with absolute ones.
BASE_DIR = Path(__file__).resolve().parents[3]


class CommonSettings(BaseSettings):
    """Cross-cutting configuration. Unprefixed names, shared by all four services."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    DATABASE_URL: str = "sqlite:///./food_research.db"

    # Identity. SECRET_KEY has no default on purpose: a shipped default is a shipped
    # private key, and every prior deployment silently signed tokens with the same one.
    # docker-compose.yml supplies it for every service; startup fails loudly without it.
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    #: Shared secret proving a request came from the gateway. Empty disables the check
    #: (local dev, where the internal network is the only boundary).
    INTERNAL_SECRET: str = ""

    #: Root for all user-supplied and generated files. Relative resolves against BASE_DIR.
    STORAGE_DIR: str = "uploads"

    @property
    def storage_root(self) -> Path:
        return storage_path(self.STORAGE_DIR)

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")


def storage_path(configured: str) -> Path:
    """Resolve a configured path against BASE_DIR unless it is already absolute."""
    path = Path(configured)
    return path if path.is_absolute() else BASE_DIR / path


def storage_subpath(configured: str) -> Path:
    """Resolve against the storage root (STORAGE_DIR) unless already absolute.

    Use this, not `storage_path`, for anything that must live on the uploads volume the
    API containers and the Celery workers share -- Docling caches, chart caches, uploaded
    datasets, model artifacts.

    `BASE_DIR` is derived from this file's location, which is right in a source checkout
    but wrong once installed: the containers put `shared` at /shared, so `parents[3]`
    resolves to "/" and a relative path like "uploads/docling_cache" became
    /uploads/docling_cache -- a directory in the container's own filesystem, not the
    mounted volume. Nothing complained, because the containers ran as root and were happy
    to create it; the cache simply went unshared and was discarded on every recreate.
    """
    path = Path(configured)
    return path if path.is_absolute() else get_common_settings().storage_root / path


@lru_cache
def get_common_settings() -> CommonSettings:
    return CommonSettings()
