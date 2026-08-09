"""Which provider `EXTRACTION_LLM_PROVIDER` means, and what it defaults to.

This table is the whole of "switch to a paid API". Adding a fifth provider is one file in
`providers/` and one row here; using it is one environment variable and its key. No
pipeline module names a provider, so nothing above this file changes either way.

Keys never have defaults and never appear in a log line, a cache key or a job result. A
provider selected without its key fails here, at construction, naming the variable to
set -- rather than on the fortieth paper of a run, inside a worker, as a 401.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, Optional

from shared.config import get_processing_settings

from app.services.llm.base import FakeLLMClient, LLMClient
from app.services.llm.errors import LLMUnavailable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderDefault:
    """`build` is deferred so importing this module does not import four vendor SDKs."""

    build: Callable[..., LLMClient]
    model: str
    base_url: str = ""
    key_field: Optional[str] = None


def _ollama(**kwargs) -> LLMClient:
    from app.services.llm.providers.ollama import OllamaClient
    return OllamaClient(**kwargs)


def _openai_compatible(provider: str) -> Callable[..., LLMClient]:
    def build(**kwargs) -> LLMClient:
        from app.services.llm.providers.openai_compatible import OpenAIChatClient
        return OpenAIChatClient(provider=provider, **kwargs)
    return build


def _anthropic(**kwargs) -> LLMClient:
    from app.services.llm.providers.anthropic import AnthropicClient
    return AnthropicClient(**kwargs)


def _gemini(**kwargs) -> LLMClient:
    from app.services.llm.providers.gemini import GeminiClient
    return GeminiClient(**kwargs)


def _fake(**kwargs) -> LLMClient:
    return FakeLLMClient()


PROVIDER_DEFAULTS: dict[str, ProviderDefault] = {
    # Local, and the default: no key, so the stack extracts out of the box.
    "ollama": ProviderDefault(_ollama, model="llama3.2:3b", base_url="http://ollama:11434"),
    "openai": ProviderDefault(
        _openai_compatible("openai"), model="gpt-4.1-mini",
        base_url="https://api.openai.com/v1", key_field="OPENAI_API_KEY",
    ),
    # Groq speaks the OpenAI chat API, so it needs no SDK and no class of its own.
    "groq": ProviderDefault(
        _openai_compatible("groq"), model="llama-3.3-70b-versatile",
        base_url="https://api.groq.com/openai/v1", key_field="GROQ_API_KEY",
    ),
    "anthropic": ProviderDefault(
        _anthropic, model="claude-sonnet-4-5", key_field="ANTHROPIC_API_KEY",
    ),
    # Not a 2.5 model: those still appear in the catalogue but 404 with "no longer
    # available to new users" on any key created recently, so they are not a usable default.
    "gemini": ProviderDefault(
        _gemini, model="gemini-3.6-flash", key_field="GEMINI_API_KEY",
    ),
    # Answers from a script: runs the pipeline with its language stage stubbed out.
    "fake": ProviderDefault(_fake, model="fake"),
}


def build_client(provider: Optional[str] = None) -> LLMClient:
    """Resolve settings into a client. Explicit settings win over the provider's defaults,
    so changing provider alone is a complete, valid change."""
    settings = get_processing_settings()
    name = (provider or settings.LLM_PROVIDER or "").strip().lower()
    default = PROVIDER_DEFAULTS.get(name)
    if default is None:
        raise LLMUnavailable(
            f"Unknown LLM provider {name!r}",
            details={"supported": sorted(PROVIDER_DEFAULTS)},
        )

    api_key = getattr(settings, default.key_field, "") if default.key_field else ""
    if default.key_field and not api_key:
        raise LLMUnavailable(
            f"LLM provider {name!r} needs an API key",
            details={"set": f"PROCESSING_{default.key_field}"},
        )

    # Ollama's OpenAI shim ignores the key but its SDKs refuse to init without one.
    return default.build(
        model=settings.LLM_MODEL or default.model,
        base_url=settings.LLM_BASE_URL or default.base_url,
        api_key=api_key,
    )


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    """The process-wide client. Holds no per-call state, so it is safe to share between
    threads; one server with several slots is how two calls run at once, where two clients
    would each make the server load its own copy of the weights."""
    return build_client()
