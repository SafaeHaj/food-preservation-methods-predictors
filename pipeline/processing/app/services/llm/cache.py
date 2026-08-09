"""On-disk cache for model replies, keyed on the prompts themselves.

A reasoning call is the most expensive thing in the pipeline and the most likely to be
repeated: a paper is re-queued, a shard is retried, a hundred-paper run is restarted.
Without this every restart re-pays every call it had already answered.

The key versions itself. It covers the provider, the model, both prompts, the decoding
options and the vocabulary digest, so editing a prompt or changing model invalidates
exactly the answers it could have changed -- and switching provider does not serve one
model's answers as another's. It deliberately does not cover the API key: a credential is
not part of the question asked.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Optional

from shared.config import get_processing_settings

logger = logging.getLogger(__name__)
_settings = get_processing_settings()


def content_key(*parts: Any) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(str(part).encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()[:32]


def _path(key: str) -> Path:
    directory = _settings.llm_cache_path
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{key}.json"


def load(key: str) -> Optional[dict]:
    if not _settings.LLM_CACHE_ENABLED:
        return None
    path = _path(key)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # A half-written or hand-edited entry is worth re-earning, not worth failing on.
        logger.warning("Discarding unreadable LLM cache entry %s", path.name)
        return None


def store(key: str, entry: dict) -> None:
    """Write through a temporary file: two workers may answer the same prompt at once, and
    a reader must never see a partial object."""
    if not _settings.LLM_CACHE_ENABLED:
        return
    path = _path(key)
    temporary = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        temporary.write_text(
            json.dumps(entry, ensure_ascii=False, default=str), encoding="utf-8"
        )
        os.replace(temporary, path)
    except OSError:
        logger.warning("Could not cache the LLM reply at %s", path.name, exc_info=True)
        temporary.unlink(missing_ok=True)
