"""Anthropic's Messages API.

Two shape differences the adapter absorbs. The system prompt is a top-level argument rather
than a message, and there is no JSON mode: structured output comes from a single forced
tool whose `input_schema` is the reply's schema. That path returns a dict directly, so it
skips the text-extraction ladder entirely -- when a schema is supplied the answer cannot
arrive malformed.

Without a schema the model is asked for JSON in prose and the ladder salvages the object,
which is why `supports_json_mode` is False: nothing enforces it at the API level.
"""

from __future__ import annotations

from typing import Optional

from shared.config import get_processing_settings

from app.services.llm.base import Capabilities, LLMClient, ProbeResult, RawReply
from app.services.llm.errors import LLMPromptTooLarge, LLMUnavailable
from app.services.llm.retry import Retryable

_settings = get_processing_settings()

_RETRYABLE_STATUS = frozenset({408, 409, 429, *range(500, 600)})
_TOO_LARGE_MARKERS = ("prompt is too long", "context window", "max_tokens")
_DEFAULT_MAX_TOKENS = 8192
_CONTEXT_TOKENS = 200_000

#: The tool the model is forced to call when a schema is supplied. Its name is arbitrary
#: and never surfaces; only the argument object is read.
_REPLY_TOOL = "emit_reply"
_JSON_INSTRUCTION = "\n\nReturn ONLY a valid JSON object. No prose, no markdown fences."


class AnthropicClient(LLMClient):
    provider = "anthropic"

    def __init__(self, *, model: str, base_url: str = "", api_key: str = "") -> None:
        super().__init__(model=model, base_url=base_url, api_key=api_key)
        self._client = self._build_client()

    def _build_client(self):
        try:
            import anthropic
        except ImportError as exc:
            raise LLMUnavailable("The `anthropic` package is required for this provider") from exc
        return anthropic.Anthropic(
            api_key=self._api_key,
            base_url=self.base_url or None,
            timeout=_settings.LLM_TIMEOUT_SECONDS,
            max_retries=0,
        )

    @property
    def capabilities(self) -> Capabilities:
        return Capabilities(
            supports_json_schema=_settings.LLM_JSON_SCHEMA,
            supports_json_mode=False,
            supports_reasoning_channel=False,
            max_context_tokens=_CONTEXT_TOKENS,
            max_output_tokens=_settings.LLM_MAX_OUTPUT_TOKENS or _DEFAULT_MAX_TOKENS,
        )

    def _invoke(
        self, *, system_prompt: str, user_prompt: str, schema: Optional[dict]
    ) -> RawReply:
        request = {
            "model": self.model,
            "max_tokens": _settings.LLM_MAX_OUTPUT_TOKENS or _DEFAULT_MAX_TOKENS,
            "temperature": _settings.LLM_TEMPERATURE,
            "system": system_prompt if schema else system_prompt + _JSON_INSTRUCTION,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        if schema:
            request["tools"] = [{
                "name": _REPLY_TOOL,
                "description": "Return the extracted values.",
                "input_schema": schema,
            }]
            request["tool_choice"] = {"type": "tool", "name": _REPLY_TOOL}

        try:
            response = self._client.messages.create(**request)
        except Exception as exc:
            raise _translate(exc) from exc

        usage = response.usage
        common = {
            "prompt_tokens": int(getattr(usage, "input_tokens", 0) or 0),
            "completion_tokens": int(getattr(usage, "output_tokens", 0) or 0),
            "finish_reason": response.stop_reason,
        }
        for block in response.content:
            if getattr(block, "type", None) == "tool_use":
                return RawReply(payload=dict(block.input), **common)
        text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        return RawReply(text=text, **common)

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
        return ProbeResult(
            reachable=True, provider=self.provider, model=self.model, schema_safe=True,
        )


def _translate(exc: Exception) -> Exception:
    message = str(exc)
    if any(marker in message.lower() for marker in _TOO_LARGE_MARKERS):
        return LLMPromptTooLarge(message)

    status = getattr(exc, "status_code", None)
    if status in _RETRYABLE_STATUS:
        return Retryable(f"HTTP {status}: {message}")
    if status is None:
        return Retryable(message)
    return LLMUnavailable("The LLM provider refused the request", details={"status": status})
