"""Gateway configuration loaded from files rather than compiled into source."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import yaml

from shared.schemas.projects import SchemaField

logger = logging.getLogger(__name__)

#: …/gateway/app/config.py -> parents[1] is the service root holding app/ and config/.
SERVICE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA_PATH = SERVICE_ROOT / "config" / "default_schema.yaml"


@lru_cache
def load_default_schema() -> tuple[SchemaField, ...]:
    """Fields a new project starts with.

    Returns a tuple because the result is cached and must not be mutated by a caller.
    Validation happens here, at load time, so a malformed file fails at the first project
    creation with a clear pydantic error rather than corrupting a stored schema.
    """
    if not DEFAULT_SCHEMA_PATH.exists():
        logger.warning("No default schema at %s; new projects start empty", DEFAULT_SCHEMA_PATH)
        return ()

    raw = yaml.safe_load(DEFAULT_SCHEMA_PATH.read_text(encoding="utf-8")) or {}
    return tuple(SchemaField(**field) for field in raw.get("fields", []))
