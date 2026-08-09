"""The one type the pipeline sees, and the machinery every provider shares.

Above this module there is no `openai`, no `anthropic`, no HTTP status and no `/api/chat`.
There is `json_completion(system_prompt=..., user_prompt=...) -> CompletionResult` and the
three exceptions in `errors.py`. That is the whole seam: adding a provider is a subclass
here and a row in `registry.PROVIDER_DEFAULTS`, and switching to one is a config change.

Caching, retries, metrics and reply extraction are implemented once in `LLMClient` because
they are properties of the pipeline's needs, not of any vendor. A provider subclass answers
only two questions: what are your capabilities, and what does one call look like.
"""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from shared.config import get_processing_settings

from app.services import timings
from app.services.llm import cache
from app.services.llm.errors import LLMBadResponse
from app.services.llm.retry import with_retries

logger = logging.getLogger(__name__)
_settings = get_processing_settings()

#: Rough characters per token for English prose with numbers. Only ever used to size a
#: prompt budget conservatively, never to bill or to truncate exactly.
CHARS_PER_TOKEN = 3.5

#: How much of the context window one prompt may claim. The rest is the reply, which for a
#: reasoning model includes a trace several times longer than its answer.
PROMPT_CONTEXT_SHARE = 0.55


@dataclass(frozen=True)
class Capabilities:
    """What this provider can actually do, so callers degrade instead of guessing.

    `max_context_tokens` is what makes the prompt budget provider-derived: moving from a
    16k local model to a 200k hosted one widens the prompt without an env change.
    """

    supports_json_schema: bool = False      # grammar-constrained decoding
    supports_json_mode: bool = False        # "return JSON" enforced, shape unconstrained
    supports_reasoning_channel: bool = False
    max_context_tokens: int = 8192
    max_output_tokens: int = 4096


@dataclass(frozen=True)
class RawReply:
    """One provider call's answer, before it is parsed.

    `payload` is set only by providers that return structured output directly (Anthropic's
    tool use); everyone else returns text and goes through the extraction ladder.
    """

    text: str = ""
    thinking: str = ""
    payload: Optional[dict] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    finish_reason: Optional[str] = None


@dataclass(frozen=True)
class CompletionResult:
    payload: dict
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_seconds: float = 0.0
    finish_reason: Optional[str] = None
    from_cache: bool = False
    recovered_from_reasoning: bool = False


@dataclass(frozen=True)
class ProbeResult:
    """What one cheap call says about a deployment, for `/health` and worker startup."""

    reachable: bool
    provider: str
    model: str
    detail: str = ""
    schema_safe: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider, "model": self.model, "reachable": self.reachable,
            "schema_safe": self.schema_safe, "detail": self.detail,
        }


def outermost_object(text: str) -> Optional[dict]:
    """The first `{` to the last `}`, parsed.

    A model that narrates around its answer still emits exactly one object, and this finds
    it without the caller having to strip markdown fences or apologies.
    """
    opened, closed = text.find("{"), text.rfind("}")
    if opened < 0 or closed <= opened:
        return None
    try:
        parsed = json.loads(text[opened:closed + 1])
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def extract_object(reply: RawReply) -> tuple[dict, bool]:
    """The answer, from wherever the model put it. Returns (object, came_from_reasoning).

    `json.loads(content)` alone was fatal on a reply of two newlines: generation had ended
    before any JSON was emitted, and the paper died on a decode error that explained
    nothing. Content, then an object embedded in it, then the reasoning channel -- and if
    all three fail, an error carrying the counters that explain why.
    """
    if reply.payload is not None:
        return reply.payload, False

    for candidate, from_reasoning in ((reply.text, False), (reply.thinking, True)):
        if not candidate.strip():
            continue
        try:
            parsed = json.loads(candidate)
        except ValueError:
            parsed = outermost_object(candidate)
        if isinstance(parsed, dict):
            return parsed, from_reasoning

    raise LLMBadResponse(
        f"No JSON object in the reply: finish_reason={reply.finish_reason!r}, "
        f"prompt_tokens={reply.prompt_tokens}, completion_tokens={reply.completion_tokens}, "
        f"thinking={len(reply.thinking)} chars, content={reply.text[:200]!r}. "
        "An empty reply with reasoning enabled usually means generation was cut off before "
        "the answer: raise EXTRACTION_LLM_MAX_OUTPUT_TOKENS or lower "
        "EXTRACTION_LLM_MAX_PROMPT_CHARS."
    )


class LLMClient(ABC):
    """Base for every provider. Subclasses implement `capabilities` and `_invoke`."""

    #: Identifies the provider in cache keys, metrics and `/health`.
    provider: str = "unknown"

    def __init__(self, *, model: str, base_url: str = "", api_key: str = "") -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        # Held for the request, never logged, never part of a cache key.
        self._api_key = api_key

    # ── What a subclass provides ──────────────────────────────────────────────

    @property
    @abstractmethod
    def capabilities(self) -> Capabilities:
        ...

    @abstractmethod
    def _invoke(
        self, *, system_prompt: str, user_prompt: str, schema: Optional[dict]
    ) -> RawReply:
        """One call. Raise `Retryable` for a transient failure, `LLMPromptTooLarge` when
        the context window is exceeded, `LLMUnavailable` for anything terminal."""

    @abstractmethod
    def probe(self) -> ProbeResult:
        """Cheap reachability check. Must not raise."""

    # ── What every provider gets ──────────────────────────────────────────────

    @property
    def prompt_budget_chars(self) -> int:
        """The lower of the configured ceiling and what the context window affords."""
        affordable = int(
            self.capabilities.max_context_tokens * CHARS_PER_TOKEN * PROMPT_CONTEXT_SHARE
        )
        return min(_settings.LLM_MAX_PROMPT_CHARS, affordable)

    def options_fingerprint(self) -> str:
        """The decoding settings that change the answer, for the cache key. Not the key,
        not the timeout, not the retry count -- none of those change what is said."""
        return json.dumps(
            {
                "temperature": _settings.LLM_TEMPERATURE,
                "max_output_tokens": _settings.LLM_MAX_OUTPUT_TOKENS,
                "reasoning": _settings.LLM_REASONING,
            },
            sort_keys=True,
        )

    def json_completion(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: Optional[dict] = None,
        cache_scope: Optional[str] = None,
        paper: Optional[str] = None,
    ) -> CompletionResult:
        """Ask for one JSON object. Cached, retried and measured.

        `schema` is passed per call, not held on the client: the two call sites return
        different shapes, and constraining generation to the wrong one is worse than not
        constraining it at all. It is ignored where the provider cannot honour it.
        """
        if schema is not None and not self.capabilities.supports_json_schema:
            schema = None

        key = cache.content_key(
            cache_scope or "call", self.provider, self.model, system_prompt, user_prompt,
            self.options_fingerprint(), "schema" if schema else "json",
        )
        if cache_scope:
            cached = cache.load(key)
            if cached is not None:
                timings.record_metric("llm_cached", paper, scope=cache_scope, seconds=0.0)
                return CompletionResult(
                    payload=cached["payload"],
                    prompt_tokens=int(cached.get("prompt_tokens") or 0),
                    completion_tokens=int(cached.get("completion_tokens") or 0),
                    from_cache=True,
                )

        started = time.perf_counter()
        reply = with_retries(
            lambda: self._invoke(
                system_prompt=system_prompt, user_prompt=user_prompt, schema=schema
            ),
            what=f"{self.provider}/{self.model}",
        )
        latency = round(time.perf_counter() - started, 3)
        payload, from_reasoning = extract_object(reply)

        timings.record_metric(
            "llm", paper, scope=cache_scope, provider=self.provider, model=self.model,
            seconds=latency, prompt_tokens=reply.prompt_tokens,
            completion_tokens=reply.completion_tokens, finish_reason=reply.finish_reason,
            tokens_per_second=(
                round(reply.completion_tokens / latency, 2) if latency > 0 else None
            ),
        )
        if reply.finish_reason in ("length", "max_tokens"):
            logger.warning(
                "%s/%s hit the output limit; the reply is truncated. Raise "
                "EXTRACTION_LLM_MAX_OUTPUT_TOKENS or lower EXTRACTION_LLM_MAX_PROMPT_CHARS.",
                self.provider, self.model,
            )
        if from_reasoning:
            logger.info("Recovered the answer from the reasoning channel, not from content")

        if cache_scope:
            cache.store(key, {
                "payload": payload,
                "prompt_tokens": reply.prompt_tokens,
                "completion_tokens": reply.completion_tokens,
            })

        return CompletionResult(
            payload=payload,
            prompt_tokens=reply.prompt_tokens,
            completion_tokens=reply.completion_tokens,
            latency_seconds=latency,
            finish_reason=reply.finish_reason,
            recovered_from_reasoning=from_reasoning,
        )


class FakeLLMClient(LLMClient):
    """A client that answers from a script. Every Gold and review test runs against it, so
    the suite needs no model, no key and no network.

    Not a test-only import: it is what `LLM_PROVIDER=fake` resolves to in a deployment that
    deliberately runs the pipeline with its language stage stubbed out.
    """

    provider = "fake"

    def __init__(self, replies: Optional[dict[str, dict]] = None) -> None:
        super().__init__(model="fake")
        self.replies = replies or {}
        self.calls: list[dict] = []

    @property
    def capabilities(self) -> Capabilities:
        return Capabilities(
            supports_json_schema=True, supports_json_mode=True,
            supports_reasoning_channel=False, max_context_tokens=32768,
        )

    def _invoke(self, *, system_prompt: str, user_prompt: str, schema) -> RawReply:
        self.calls.append({"system": system_prompt, "user": user_prompt, "schema": schema})
        return RawReply(text=json.dumps(self._next_payload()))

    def _next_payload(self) -> dict:
        scope = self.calls[-1]
        for name, payload in self.replies.items():
            if name in scope["system"] or name in scope["user"]:
                return payload
        return self.replies.get("default", {})

    def probe(self) -> ProbeResult:
        return ProbeResult(reachable=True, provider=self.provider, model=self.model,
                           schema_safe=True, detail="scripted replies")
