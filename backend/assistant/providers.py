"""
LLM provider abstraction for the assistant.

AssistantService talks only to the LLMProvider interface below -- it never
calls Ollama's (or Groq's) HTTP API directly. Swapping LLM_PROVIDER=groq for
LLM_PROVIDER=ollama (or adding a third provider later) requires no changes
to AssistantService or the tool-dispatch loop, only a new provider class and
a line in get_provider().
"""
from __future__ import annotations

import abc
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

import requests


def _parse_retry_after(resp: requests.Response) -> float | None:
    header = resp.headers.get("Retry-After")
    if header:
        try:
            return float(header)
        except ValueError:
            pass
    match = re.search(r"try again in ([\d.]+)s", resp.text)
    return float(match.group(1)) if match else None


@dataclass
class ProviderMessage:
    """Normalized shape every provider must return from chat(), regardless
    of how the underlying API represents assistant turns and tool calls."""
    content: str | None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] | None = None


class LLMProvider(abc.ABC):
    # Whether this provider's wire format wants function.arguments as a
    # JSON-encoded string (OpenAI/Groq) rather than a parsed object (Ollama)
    # when an assistant tool-call message is echoed back into history.
    ARGS_AS_JSON_STRING: bool = False

    @abc.abstractmethod
    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ProviderMessage:
        """messages: OpenAI-style [{role, content, ...}]. tools: OpenAI-style
        function-calling tool specs. Must return a ProviderMessage."""
        raise NotImplementedError


class OllamaProvider(LLMProvider):
    """Talks to a local Ollama server's /api/chat endpoint (OpenAI-compatible
    tool-calling support since Ollama 0.3+). Never called from Next.js --
    only ever invoked from this backend process."""

    def __init__(self, base_url: str | None = None, model: str | None = None, timeout: float = 180.0):
        self.base_url = (base_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        # qwen3:4b was tried as a faster default but on this CPU it doesn't
        # reliably use structured tool calls -- it narrates its reasoning as
        # plain content instead of calling the tool, which breaks the "never
        # invent numbers" guarantee. qwen3:8b follows the tool-calling format
        # correctly, so it stays the default despite being slower per round.
        self.model = model or os.environ.get("OLLAMA_MODEL", "qwen3:8b")
        self.timeout = timeout

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ProviderMessage:
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "stream": False,
            "think": False,  # qwen3's chain-of-thought adds ~30-70s of latency on CPU for no
                              # accuracy benefit on these tool-routing decisions; keep it off.
            "options": {"temperature": 0.2, "num_predict": 350},  # bound worst-case generation length
        }
        try:
            resp = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout)
            resp.raise_for_status()
        except requests.exceptions.ConnectionError as exc:
            raise RuntimeError(
                f"Could not reach Ollama at {self.base_url}. Is it running? Start it with `ollama serve` "
                f"(or the desktop app) and make sure `{self.model}` is pulled (`ollama pull {self.model}`)."
            ) from exc
        data = resp.json()
        message = data.get("message", {})
        tool_calls = []
        for i, tc in enumerate(message.get("tool_calls", []) or []):
            fn = tc.get("function", {})
            tool_calls.append({
                "id": tc.get("id") or f"call_{i}",
                "name": fn.get("name"), "arguments": fn.get("arguments") or {},
            })
        return ProviderMessage(content=message.get("content"), tool_calls=tool_calls, raw=data)


class GroqProvider(LLMProvider):
    """OpenAI-compatible chat-completions provider for Groq. Included to
    demonstrate the abstraction is real (not speculative) -- swap
    LLM_PROVIDER=groq and set GROQ_API_KEY to use it, no other code changes."""

    ARGS_AS_JSON_STRING = True

    def __init__(self, api_key: str | None = None, model: str | None = None, timeout: float = 60.0):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY", "")
        self.model = model or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.timeout = timeout
        self.base_url = "https://api.groq.com/openai/v1"

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ProviderMessage:
        if not self.api_key:
            raise RuntimeError("GROQ_API_KEY is not set; cannot use LLM_PROVIDER=groq.")
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {"model": self.model, "messages": messages, "tools": tools, "temperature": 0.2}

        # Free-tier Groq accounts have a low tokens-per-minute limit that a
        # tool-heavy system prompt can trip; Groq's 429 body names the exact
        # wait, so retry a couple of times instead of failing the whole turn.
        resp = requests.post(f"{self.base_url}/chat/completions", json=payload, headers=headers, timeout=self.timeout)
        for _ in range(3):
            if resp.status_code != 429:
                break
            wait_s = _parse_retry_after(resp) or 2.0
            time.sleep(min(wait_s, 10.0))
            resp = requests.post(f"{self.base_url}/chat/completions", json=payload, headers=headers, timeout=self.timeout)

        if not resp.ok:
            raise RuntimeError(f"Groq API error {resp.status_code}: {resp.text[:1000]}")
        data = resp.json()
        message = data["choices"][0]["message"]
        tool_calls = []
        for i, tc in enumerate(message.get("tool_calls", []) or []):
            fn = tc.get("function", {})
            import json as _json
            args = fn.get("arguments")
            if isinstance(args, str):
                try:
                    args = _json.loads(args)
                except ValueError:
                    args = {}
            tool_calls.append({
                "id": tc.get("id") or f"call_{i}",
                "name": fn.get("name"), "arguments": args or {},
            })
        return ProviderMessage(content=message.get("content"), tool_calls=tool_calls, raw=data)


def get_provider(name: str | None = None) -> LLMProvider:
    name = (name or os.environ.get("LLM_PROVIDER", "ollama")).lower()
    if name == "ollama":
        return OllamaProvider()
    if name == "groq":
        return GroqProvider()
    raise ValueError(f"Unknown LLM_PROVIDER: {name!r} (expected 'ollama' or 'groq')")
