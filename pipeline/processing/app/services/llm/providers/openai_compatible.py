"""Any provider speaking the OpenAI chat API: OpenAI itself, Groq, vLLM, Together.

One class covers all of them because they differ only in base URL, model name and key --
which is exactly what `registry.PROVIDER_DEFAULTS` holds. Adding another is a row in that
table, not a file here.

Three notebook concepts have no equivalent and are dropped rather than faked: `keep_alive`
(there is no local weight residency to manage), `num_ctx` (the context window is a property
of the model, reported through `Capabilities` instead) and `think` as a boolean (only the
reasoning models take an effort level, and the rest ignore it).
"""

from __future__ import annotations

from typing import Optional

from shared.config import get_processing_settings

from app.services.llm.base import Capabilities, LLMClient, ProbeResult, RawReply
from app.services.llm.errors import LLMPromptTooLarge, LLMUnavailable
from app.services.llm.retry import Retryable

_settings = get_processing_settings()

_RETRYABLE_STATUS = frozenset({408, 409, 429, *range(500, 600)})
_TOO_LARGE_MARKERS = ("context_length_exceeded", "context length", "too large", "maximum context")
_REASONING_EFFORTS = ("low", "medium", "high")

#: Context windows for the models this pipeline is expected to run against. A model that is
#: not listed falls back to the conservative default, which only ever narrows the prompt.
_CONTEXT_TOKENS = {
    "gpt-4.1": 1_047_576, "gpt-4.1-mini": 1_047_576, "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000, "o4-mini": 200_000,
    "llama-3.3-70b-versatile": 128_000, "llama-3.1-8b-instant": 128_000,
}
_DEFAULT_CONTEXT_TOKENS = 32_000


class OpenAIChatClient(LLMClient):
    provider = "openai"

    def __init__(self, *, model: str, base_url: str = "", api_key: str = "",
                 provider: str = "openai") -> None:
        super().__init__(model=model, base_url=base_url, api_key=api_key)
        self.provider = provider
        self._client = self._build_client()

    def _build_client(self):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise LLMUnavailable(
                "The `openai` package is required for OpenAI-compatible providers"
            ) from exc
        return OpenAI(
            api_key=self._api_key,
            base_url=self.base_url or None,
            timeout=_settings.LLM_TIMEOUT_SECONDS,
            max_retries=0,   # `retry.with_retries` owns the ladder; two would compound
        )

    @property
    def capabilities(self) -> Capabilities:
        return Capabilities(
            supports_json_schema=_settings.LLM_JSON_SCHEMA,
            supports_json_mode=True,
            supports_reasoning_channel=False,   # traces are not returned on the chat API
            max_context_tokens=_CONTEXT_TOKENS.get(self.model, _DEFAULT_CONTEXT_TOKENS),
            max_output_tokens=_settings.LLM_MAX_OUTPUT_TOKENS or 8192,
        )

    def _response_format(self, schema: Optional[dict]) -> dict:
        if schema:
            return {
                "type": "json_schema",
                "json_schema": {"name": "reply", "strict": False, "schema": schema},
            }
        return {"type": "json_object"}

    def _invoke(
        self, *, system_prompt: str, user_prompt: str, schema: Optional[dict]
    ) -> RawReply:
        request = {
            "model": self.model,
            "temperature": _settings.LLM_TEMPERATURE,
            "response_format": self._response_format(schema),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if _settings.LLM_MAX_OUTPUT_TOKENS > 0:
            request["max_tokens"] = _settings.LLM_MAX_OUTPUT_TOKENS
        effort = (_settings.LLM_REASONING or "").strip().lower()
        if effort in _REASONING_EFFORTS:
            request["reasoning_effort"] = effort

        try:
            response = self._client.chat.completions.create(**request)
        except Exception as exc:
            raise _translate(exc) from exc

        choice = response.choices[0]
        usage = response.usage
        return RawReply(
            text=choice.message.content or "",
            prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            finish_reason=choice.finish_reason,
        )

    def probe(self) -> ProbeResult:
        if not self._api_key:
            return ProbeResult(
                reachable=False, provider=self.provider, model=self.model,
                detail="No API key configured",
            )
        try:
            self._client.models.retrieve(self.model)
        except Exception as exc:
            return ProbeResult(
                reachable=False, provider=self.provider, model=self.model, detail=str(exc),
            )
        # Structured outputs are a documented feature here, not a build-dependent one.
        return ProbeResult(
            reachable=True, provider=self.provider, model=self.model, schema_safe=True,
        )


def _translate(exc: Exception) -> Exception:
    """Map an SDK exception into the three the pipeline knows about."""
    message = str(exc)
    if any(marker in message.lower() for marker in _TOO_LARGE_MARKERS):
        return LLMPromptTooLarge(message)

    status = getattr(exc, "status_code", None)
    if status in _RETRYABLE_STATUS:
        return Retryable(f"HTTP {status}: {message}", retry_after=_retry_after(exc))
    if status is None:
        # No status means it never reached the server: a DNS failure, a reset, a timeout.
        return Retryable(message)
    return LLMUnavailable("The LLM provider refused the request", details={"status": status})


def _retry_after(exc: Exception) -> Optional[float]:
    headers = getattr(getattr(exc, "response", None), "headers", None) or {}
    try:
        return float(headers.get("retry-after"))
    except (TypeError, ValueError):
        return None
