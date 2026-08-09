"""The three failures a caller can act on.

Every provider maps its own vocabulary -- an HTTP status, an SDK exception, a message
saying "context length exceeded" -- into one of these. Above this module nothing catches an
`openai.APIError` or reads `exc.code`, which is what makes swapping a provider a config
change: the handling of a too-large prompt does not have to be rewritten per vendor.
"""

from __future__ import annotations

from shared.errors import ServiceUnavailableError


class LLMUnavailable(ServiceUnavailableError):
    """No usable provider: the server is down, the key is missing, or retries ran out.

    A `ServiceUnavailableError` so it reaches the client as 503 with the shared envelope
    when it escapes; the review call catches it and degrades instead.
    """


class LLMPromptTooLarge(RuntimeError):
    """The prompt did not fit the model's context window.

    Distinct from `LLMUnavailable` because it is actionable rather than fatal: the caller
    rebuilds at a smaller budget and tries once more.
    """


class LLMBadResponse(RuntimeError):
    """The reply contained no JSON object, in content or anywhere else."""
