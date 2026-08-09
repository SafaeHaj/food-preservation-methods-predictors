"""Google Gemini through the `google-genai` SDK.

The system prompt is `system_instruction` on the config rather than a message, and JSON is
requested with `response_mime_type` plus an optional `response_schema` -- which is the same
two-rung ladder the other providers have, under different names.

Gemini's schema dialect is a subset: `$defs`/`$ref`, `additionalProperties` and several
keywords are rejected outright. Rather than teach every caller a second schema dialect,
`_flatten_schema` inlines definitions and drops what is not supported; a schema that
survives constrains generation, and one that does not falls back to plain JSON mode.
"""

from __future__ import annotations

import copy
from typing import Any, NamedTuple, Optional

from shared.config import get_processing_settings

from app.services.llm.base import Capabilities, LLMClient, ProbeResult, RawReply
from app.services.llm.errors import LLMPromptTooLarge, LLMUnavailable
from app.services.llm.retry import Retryable

_settings = get_processing_settings()

_RETRYABLE_STATUS = frozenset({408, 409, 429, *range(500, 600)})
_TOO_LARGE_MARKERS = ("token count", "exceeds the maximum", "input is too long")
_DEFAULT_MAX_TOKENS = 8192


class ModelSpec(NamedTuple):
    """What one model affords. `thinking` records whether its budget can be set at all:
    2.5 Pro always reasons, so asking for zero is refused rather than quietly ignored."""

    context: int
    max_output: int
    thinking: str          # "optional" | "always"


#: The catalogue drifts and this table will go stale, so an unlisted model falls back to
#: `_DEFAULT_SPEC` rather than failing -- a newer model must not be blocked by an old table.
#: `probe()` names what is actually available when an id is wrong.
#:
#: Verified against `GET /v1beta/models` on 2026-08-08. The 2.5 family is deliberately
#: absent: it still appears in the listing but returns 404 "no longer available to new
#: users" on a key created now, which is exactly the drift `_DEFAULT_SPEC` and `probe()`
#: exist to absorb. Every gemini-3 model reports `thinking: true` and cannot have its
#: budget zeroed, hence "always" throughout.
_MODELS = {
    "gemini-3.6-flash": ModelSpec(1_048_576, 65_536, "always"),
    "gemini-3.5-flash": ModelSpec(1_048_576, 65_536, "always"),
    "gemini-3.5-flash-lite": ModelSpec(1_048_576, 65_536, "always"),
    "gemini-3.1-flash-lite": ModelSpec(1_048_576, 65_536, "always"),
    "gemini-3-flash-preview": ModelSpec(1_048_576, 65_536, "always"),
    "gemini-3.1-pro-preview": ModelSpec(1_048_576, 65_536, "always"),
    "gemini-3-pro-preview": ModelSpec(1_048_576, 65_536, "always"),
}
_DEFAULT_SPEC = ModelSpec(1_048_576, 8_192, "optional")

#: `LLM_REASONING` -> a thinking budget in tokens. -1 lets the model decide, 0 disables it.
#: One setting drives every provider, which is the point of the seam; Gemini was the only
#: one ignoring it.
_THINKING_BUDGETS = {"false": 0, "low": 1024, "medium": 8192, "high": 24576, "true": -1}

#: JSON Schema keywords Gemini's `response_schema` does not accept.
#:
#: `anyOf` is deliberately NOT here: Gemini supports it, and pydantic emits it for every
#: `Optional` field. Dropping it left `{}` -- a typeless node -- on seven of the nine fields
#: the Gold call asks for, so the reply was unconstrained on exactly what it was called for.
_UNSUPPORTED_KEYWORDS = frozenset({
    "additionalProperties", "$schema", "$defs", "definitions", "allOf", "oneOf",
    "not", "const", "default", "examples", "title", "patternProperties",
    # Numeric bounds: Gemini rejects the JSON Schema spellings, and pydantic emits them for
    # any `Field(ge=…)`. Validation still happens in Python, where it is enforceable.
    "exclusiveMinimum", "exclusiveMaximum", "minimum", "maximum",
})


class GeminiClient(LLMClient):
    provider = "gemini"

    def __init__(self, *, model: str, base_url: str = "", api_key: str = "") -> None:
        super().__init__(model=model, base_url=base_url, api_key=api_key)
        self._client, self._types = self._build_client()
        self._spec = _MODELS.get(model, _DEFAULT_SPEC)

    def _build_client(self):
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise LLMUnavailable("The `google-genai` package is required for this provider") from exc
        return genai.Client(api_key=self._api_key), types

    @property
    def capabilities(self) -> Capabilities:
        return Capabilities(
            supports_json_schema=_settings.LLM_JSON_SCHEMA,
            supports_json_mode=True,
            supports_reasoning_channel=False,
            max_context_tokens=self._spec.context,
            max_output_tokens=_settings.LLM_MAX_OUTPUT_TOKENS or self._spec.max_output,
        )

    def _thinking_config(self):
        """`LLM_REASONING` as a `ThinkingConfig`, or None when it does not apply.

        A model whose reasoning cannot be switched off gets no config at all rather than a
        budget of zero it would refuse: the setting is reported as not applied instead of
        silently disobeyed.
        """
        value = (_settings.LLM_REASONING or "").strip().lower()
        budget = _THINKING_BUDGETS.get(value)
        if budget is None:
            return None
        if self._spec.thinking == "always" and budget == 0:
            return None
        return self._types.ThinkingConfig(thinking_budget=budget)

    def _invoke(
        self, *, system_prompt: str, user_prompt: str, schema: Optional[dict]
    ) -> RawReply:
        config: dict[str, Any] = {
            "system_instruction": system_prompt,
            "temperature": _settings.LLM_TEMPERATURE,
            "response_mime_type": "application/json",
        }
        if _settings.LLM_MAX_OUTPUT_TOKENS > 0:
            config["max_output_tokens"] = _settings.LLM_MAX_OUTPUT_TOKENS
        thinking = self._thinking_config()
        if thinking is not None:
            config["thinking_config"] = thinking
        if schema:
            flattened = _flatten_schema(schema)
            if flattened:
                config["response_schema"] = flattened

        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=user_prompt,
                config=self._types.GenerateContentConfig(**config),
            )
        except Exception as exc:
            raise _translate(exc) from exc

        usage = getattr(response, "usage_metadata", None)
        candidates = getattr(response, "candidates", None) or []
        return RawReply(
            text=response.text or "",
            prompt_tokens=int(getattr(usage, "prompt_token_count", 0) or 0),
            completion_tokens=int(getattr(usage, "candidates_token_count", 0) or 0),
            finish_reason=str(getattr(candidates[0], "finish_reason", "")) if candidates else None,
        )

    def probe(self) -> ProbeResult:
        if not self._api_key:
            return ProbeResult(
                reachable=False, provider=self.provider, model=self.model,
                detail="No API key configured",
            )
        try:
            self._client.models.get(model=self.model)
        except Exception as exc:
            # A wrong id gives a bare 404, which says nothing actionable. Listing what does
            # exist turns a drifted model name into a startup message with the fix in it --
            # which is the honest answer to a catalogue that changes faster than this code.
            return ProbeResult(
                reachable=False, provider=self.provider, model=self.model,
                detail=f"{exc}{self._available_models()}",
            )
        applied = "not applied (this model always reasons)" \
            if self._thinking_config() is None and self._spec.thinking == "always" \
            else _settings.LLM_REASONING
        return ProbeResult(
            reachable=True, provider=self.provider, model=self.model, schema_safe=True,
            detail=f"context {self._spec.context:,} tokens; reasoning {applied}",
        )

    def _available_models(self) -> str:
        """The catalogue, for a failed probe's message. Silent on failure: this is already
        the error path, and a second error would bury the first."""
        try:
            names = sorted(
                model.name.rsplit("/", 1)[-1]
                for model in self._client.models.list()
                if "generateContent" in (getattr(model, "supported_actions", None) or
                                         ["generateContent"])
            )
        except Exception:
            return ""
        return f" — models available to this key: {', '.join(names)}" if names else ""


def _optional_branch(branches: list) -> Optional[dict]:
    """The non-null branch of an `Optional[X]` union, or None if it is not one.

    `str | None` reaches here as `[{"type": "string"}, {"type": "null"}]`. Exactly one
    non-null branch makes it an optional scalar, which Gemini expresses as `nullable` --
    a genuine two-type union (`str | int`) has two and is left as `anyOf` for Gemini to
    handle itself.
    """
    concrete = [item for item in branches
                if isinstance(item, dict) and item.get("type") != "null"]
    nullable = len(concrete) < len(branches)
    return concrete[0] if nullable and len(concrete) == 1 else None


def _flatten_schema(schema: dict) -> Optional[dict]:
    """Translate a pydantic JSON Schema into Gemini's dialect. None when nothing usable
    remains.

    Three transformations, each forced by something `response_schema` refuses:

      `$ref`/`$defs`   inlined, because Gemini rejects references outright
      `anyOf` on null  collapsed to the non-null branch plus `nullable: true`
      unsupported keys dropped (see `_UNSUPPORTED_KEYWORDS`)

    The `anyOf` collapse is the one that matters. Pydantic emits it for every `Optional`
    field, and simply dropping the keyword -- which this did -- left `{}` behind: a node
    with no type, which constrains nothing. On `ProtocolReply` that was seven of nine
    fields, so the schema-constrained path was constraining only `experiment_index`.

    A rejected schema fails the whole call, so anything still untranslatable is dropped and
    JSON mode plus the extraction ladder carries the reply instead.
    """
    definitions = schema.get("$defs") or schema.get("definitions") or {}

    def resolve(node: Any, depth: int = 0) -> Any:
        if depth > 16:      # a self-referencing model would otherwise inline forever
            return {"type": "object"}
        if isinstance(node, list):
            return [resolve(item, depth + 1) for item in node]
        if not isinstance(node, dict):
            return node

        reference = node.get("$ref")
        if reference:
            name = reference.rsplit("/", 1)[-1]
            target = definitions.get(name)
            return resolve(copy.deepcopy(target), depth + 1) if target else {"type": "object"}

        branches = node.get("anyOf")
        if isinstance(branches, list):
            concrete = _optional_branch(branches)
            if concrete is not None:
                # Merge the siblings (`description`, `title`…) onto the branch so a field's
                # documentation survives the collapse -- it is what tells the model what the
                # field means.
                merged = {**{key: value for key, value in node.items() if key != "anyOf"},
                          **concrete, "nullable": True}
                return resolve(merged, depth + 1)

        flattened = {
            key: resolve(value, depth + 1)
            for key, value in node.items()
            if key not in _UNSUPPORTED_KEYWORDS
        }
        # Gemini honours `propertyOrdering` and adherence measurably improves with it. The
        # schema's own field order is the one the prompt describes.
        if flattened.get("type") == "object" and "properties" in flattened:
            flattened["propertyOrdering"] = list(flattened["properties"])
        return flattened

    flattened = resolve(schema)
    return flattened if isinstance(flattened, dict) and flattened.get("type") else None


def _translate(exc: Exception) -> Exception:
    message = str(exc)
    if any(marker in message.lower() for marker in _TOO_LARGE_MARKERS):
        return LLMPromptTooLarge(message)

    status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if status in _RETRYABLE_STATUS:
        return Retryable(f"HTTP {status}: {message}")
    if status is None:
        return Retryable(message)
    return LLMUnavailable("The LLM provider refused the request", details={"status": status})
