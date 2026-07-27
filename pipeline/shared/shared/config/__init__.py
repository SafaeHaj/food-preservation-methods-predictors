"""Layered, per-service configuration.

Replaces the previous single 25-field `Settings` class that every service imported whole.
Each service now depends only on the settings it actually uses, which is what makes the
dependency direction meaningful: the extraction service has no reason to know a prediction
service URL exists, and the gateway has no reason to hold LLM API keys.

Layout::

    CommonSettings       everything shares: database, JWT, logging, storage roots
    GatewaySettings      service URLs, CORS, proxy behaviour, asset-URL signing
    ExtractionSettings   LLM providers, upload limits, Docling/chart caches, scoring
    ProcessingSettings   export dir, prediction service client, model families

Every field is environment-driven and prefixed (`EXTRACTION_`, `PROCESSING_`, ...) except
the common ones, which keep their historical unprefixed names so existing deployments and
`docker-compose.yml` keep working. Accessors are `lru_cache`d, so settings are read once
per process but are still patchable in tests via `.cache_clear()`.
"""

from shared.config.base import (
    CommonSettings, get_common_settings, storage_path, storage_subpath,
)
from shared.config.gateway import GatewaySettings, get_gateway_settings
from shared.config.extraction import ExtractionSettings, get_extraction_settings
from shared.config.processing import ProcessingSettings, get_processing_settings

__all__ = [
    "CommonSettings",
    "GatewaySettings",
    "ExtractionSettings",
    "ProcessingSettings",
    "get_common_settings",
    "get_gateway_settings",
    "get_extraction_settings",
    "get_processing_settings",
    "storage_path",
    "storage_subpath",
]
