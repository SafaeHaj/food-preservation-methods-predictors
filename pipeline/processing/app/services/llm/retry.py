"""One retry ladder for every provider.

Without it a single timeout at paper 180 discards 180 papers of vision work. With a ladder
per provider, each would grow its own idea of what is worth retrying -- and the one that
retried a 400 would spend three timeouts proving the prompt is still malformed.

Retried: transport failures, 5xx, and 429. Not retried: any other 4xx (the request will
not become valid by being sent again) and `LLMPromptTooLarge` (the caller shrinks it).
"""

from __future__ import annotations

import logging
import random
import time
from typing import Callable, TypeVar

from shared.config import get_processing_settings

from app.services.llm.errors import LLMPromptTooLarge, LLMUnavailable

logger = logging.getLogger(__name__)
_settings = get_processing_settings()

T = TypeVar("T")


class Retryable(Exception):
    """A provider failure worth sending again. `retry_after` honours the server's own ask."""

    def __init__(self, reason: str, retry_after: float | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.retry_after = retry_after


def with_retries(call: Callable[[], T], *, what: str) -> T:
    """Run `call`, retrying what it raises as `Retryable`. Anything else propagates."""
    attempts = max(1, _settings.LLM_RETRIES)
    last = ""
    for attempt in range(1, attempts + 1):
        try:
            return call()
        except (LLMPromptTooLarge, LLMUnavailable):
            raise
        except Retryable as exc:
            last = exc.reason
            if attempt == attempts:
                break
            delay = exc.retry_after if exc.retry_after is not None else (
                _settings.LLM_RETRY_BACKOFF ** (attempt - 1) * (1.0 + random.random())
            )
            logger.warning(
                "%s failed (%s); retry %d/%d in %.1fs", what, last, attempt, attempts - 1, delay
            )
            time.sleep(delay)
    raise LLMUnavailable(
        f"{what} failed after {attempts} attempt(s)", details={"reason": last}
    )
