"""The pipeline's only route to a language model.

    from app.services.llm import get_llm_client, LLMPromptTooLarge

    result = get_llm_client().json_completion(
        system_prompt=..., user_prompt=..., schema=Reply.model_json_schema(),
        cache_scope="gold", paper=slug,
    )

Which provider answers is `EXTRACTION_LLM_PROVIDER`; what it defaults to is one table in
`registry.py`. Nothing outside this package names a vendor, imports an SDK, or reads an
HTTP status, so switching Ollama for a paid API is a configuration change.
"""

from app.services.llm.base import (
    CHARS_PER_TOKEN, Capabilities, CompletionResult, FakeLLMClient, LLMClient, ProbeResult,
)
from app.services.llm.errors import LLMBadResponse, LLMPromptTooLarge, LLMUnavailable
from app.services.llm.registry import PROVIDER_DEFAULTS, build_client, get_llm_client

__all__ = [
    "CHARS_PER_TOKEN",
    "Capabilities",
    "CompletionResult",
    "FakeLLMClient",
    "LLMBadResponse",
    "LLMClient",
    "LLMPromptTooLarge",
    "LLMUnavailable",
    "PROVIDER_DEFAULTS",
    "ProbeResult",
    "build_client",
    "get_llm_client",
]
