"""Ollama over its native `/api/chat`, on the stdlib.

Not the OpenAI-compatible `/v1` shim, because three things the pipeline uses only exist on
the native endpoint: `think` (the reasoning channel a recovered answer comes back in),
`keep_alive` (so a 14B model is not reloaded between papers) and `num_ctx` (the context
window, which is a server-side setting here rather than a property of the model).

Stdlib rather than an SDK: no key, nothing to misconfigure into a hosted provider by
accident, and one fewer dependency whose version has to agree with the others.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Optional

from shared.config import get_processing_settings

from app.services.llm.base import Capabilities, LLMClient, ProbeResult, RawReply
from app.services.llm.errors import LLMPromptTooLarge, LLMUnavailable
from app.services.llm.retry import Retryable

_settings = get_processing_settings()

_RETRYABLE_STATUS = frozenset({408, 429, *range(500, 600)})
_HTTP_REASON_CHARS = 300
_PROBE_TIMEOUT = 10

#: Ollama says a prompt overflowed in prose, not in a status code.
_TOO_LARGE_MARKERS = ("exceed", "context length", "too long", "n_ctx")

_SCHEMA_PROBE_PROMPT = 'Return the JSON object {"ok": true} and nothing else.'


def _reasoning_flag() -> Any:
    """`think` takes a boolean or an effort level; anything else means off.

    A model with no reasoning channel is 400ed by some builds when sent `think: true`,
    which is why `probe()` reports it rather than letting it surface on the first paper.
    """
    value = (_settings.LLM_REASONING or "").strip().lower()
    if value in ("low", "medium", "high"):
        return value
    return value in ("1", "true", "yes", "on")


class OllamaClient(LLMClient):
    provider = "ollama"

    @property
    def capabilities(self) -> Capabilities:
        return Capabilities(
            supports_json_schema=_settings.LLM_JSON_SCHEMA,
            supports_json_mode=True,
            supports_reasoning_channel=bool(_reasoning_flag()),
            max_context_tokens=_settings.OLLAMA_NUM_CTX,
            max_output_tokens=_settings.LLM_MAX_OUTPUT_TOKENS or _settings.OLLAMA_NUM_CTX,
        )

    @property
    def _url(self) -> str:
        # A base URL left pointing at the OpenAI shim still works: /v1 is stripped so an
        # existing .env does not have to change when the native provider takes over.
        root = self.base_url[: -len("/v1")] if self.base_url.endswith("/v1") else self.base_url
        return f"{root}/api/chat"

    def _options(self) -> dict:
        """`num_predict` bounds the whole generation, reasoning included, so a cap below a
        model's natural trace length ends the call before any JSON is emitted. It is sent
        only when set deliberately; unset, `num_ctx` still bounds a spiral."""
        options = {
            "temperature": _settings.LLM_TEMPERATURE,
            "num_ctx": _settings.OLLAMA_NUM_CTX,
        }
        limit = _settings.LLM_MAX_OUTPUT_TOKENS or _settings.OLLAMA_NUM_PREDICT
        if limit > 0:
            options["num_predict"] = limit
        return options

    def _keep_alive(self) -> Any:
        raw = (_settings.OLLAMA_KEEP_ALIVE or "").strip()
        try:
            return int(raw)
        except ValueError:
            return raw or "5m"

    def _post(self, body: dict, *, timeout: float) -> dict:
        request = urllib.request.Request(
            self._url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            reason = _http_reason(exc)
            if any(marker in reason.lower() for marker in _TOO_LARGE_MARKERS):
                raise LLMPromptTooLarge(reason) from exc
            if exc.code in _RETRYABLE_STATUS:
                raise Retryable(f"HTTP {exc.code}: {reason}") from exc
            raise LLMUnavailable(
                f"Ollama refused the request ({exc.code})", details={"reason": reason}
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise Retryable(str(exc)) from exc

    def _invoke(
        self, *, system_prompt: str, user_prompt: str, schema: Optional[dict]
    ) -> RawReply:
        response = self._post(
            {
                "model": self.model,
                "stream": False,
                "format": schema if schema else "json",
                "think": _reasoning_flag(),
                "keep_alive": self._keep_alive(),
                "options": self._options(),
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
            timeout=_settings.LLM_TIMEOUT_SECONDS,
        )
        message = response.get("message") or {}
        return RawReply(
            text=message.get("content") or "",
            thinking=message.get("thinking") or "",
            prompt_tokens=int(response.get("prompt_eval_count") or 0),
            completion_tokens=int(response.get("eval_count") or 0),
            finish_reason=response.get("done_reason"),
        )

    def probe(self) -> ProbeResult:
        """Is the server up, is the model pulled, and is schema decoding safe here?

        The last question is real: where the grammar is applied to the reasoning tokens as
        well, the reply comes back mangled. One call answers it, and it is worth answering
        at startup rather than on the first paper of a run.
        """
        root = self.base_url[: -len("/v1")] if self.base_url.endswith("/v1") else self.base_url
        try:
            with urllib.request.urlopen(f"{root}/api/tags", timeout=_PROBE_TIMEOUT) as response:
                entries = json.load(response).get("models", [])
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            return ProbeResult(
                reachable=False, provider=self.provider, model=self.model,
                detail=f"No Ollama server at {root}: {exc}",
            )

        available = {
            name for name in (entry.get("model") or entry.get("name") for entry in entries)
            if name
        }
        if self.model not in available:
            return ProbeResult(
                reachable=False, provider=self.provider, model=self.model,
                detail=(
                    f"{self.model!r} is not pulled. Run `ollama pull {self.model}`. "
                    f"Available: {', '.join(sorted(available)) or 'none'}"
                ),
            )
        return ProbeResult(
            reachable=True, provider=self.provider, model=self.model,
            schema_safe=self._schema_is_safe(),
        )

    def _schema_is_safe(self) -> bool:
        probe_schema = {
            "type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"],
        }
        try:
            response = self._post(
                {
                    "model": self.model, "stream": False, "format": probe_schema,
                    "think": _reasoning_flag(), "keep_alive": self._keep_alive(),
                    "options": {**self._options(), "num_predict": 512},
                    "messages": [{"role": "user", "content": _SCHEMA_PROBE_PROMPT}],
                },
                timeout=_PROBE_TIMEOUT * 6,
            )
        except (Retryable, LLMUnavailable, LLMPromptTooLarge):
            return False

        message = response.get("message") or {}
        try:
            json.loads(message.get("content") or "")
        except ValueError:
            return False
        # With reasoning on, an empty thinking channel means the grammar swallowed it.
        return bool(message.get("thinking")) or not _reasoning_flag()


def _http_reason(exc: urllib.error.HTTPError) -> str:
    """Ollama names the field it rejected in the body; `str(HTTPError)` names nothing."""
    try:
        body = exc.read().decode("utf-8", "replace").strip()
    except (OSError, ValueError):
        body = ""
    try:
        body = json.loads(body).get("error") or body
    except ValueError:
        pass
    return f"{exc.reason} — {body[:_HTTP_REASON_CHARS]}" if body else str(exc.reason)
