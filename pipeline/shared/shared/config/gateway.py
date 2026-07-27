"""Gateway-only settings: downstream service URLs, CORS, proxy and asset-URL signing."""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    EXTRACTION_SERVICE_URL: str = "http://extraction:8001"
    PROCESSING_SERVICE_URL: str = "http://processing:8002"

    #: Generous by default: a Docling parse of a large PDF is proxied synchronously on the
    #: first call. Once everything heavy is a Celery job this can drop substantially.
    PROXY_TIMEOUT_SECONDS: float = 600.0

    ALLOWED_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    #: How long a signed asset URL stays valid. Long enough for a page of thumbnails to
    #: load and for the user to open a detail panel; short enough that a leaked URL from a
    #: browser history or a referrer header is worthless.
    ASSET_URL_TTL_SECONDS: int = 900

    #: Server-Sent Events tuning for job progress.
    JOB_STREAM_POLL_SECONDS: float = 1.0
    JOB_STREAM_MAX_SECONDS: float = 3600.0
    #: Comment frames keep proxies and load balancers from reaping an idle stream.
    JOB_STREAM_KEEPALIVE_SECONDS: float = 15.0

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, value):
        """Accept the comma-separated form docker-compose and .env files use."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def allow_all_origins(self) -> bool:
        return "*" in self.ALLOWED_ORIGINS


@lru_cache
def get_gateway_settings() -> GatewaySettings:
    return GatewaySettings()
