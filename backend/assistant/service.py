"""
AssistantService -- the only thing backend/main.py's /api/assistant/chat
endpoint talks to. Owns the system prompt, the tool-dispatch loop, and the
LLMProvider it happens to be configured with. Never invents numbers itself:
every dataset/metric/prediction/explanation/reference fact must come back
through a tool call to model_service.ModelService.

No LangChain, no vector DB, no fine-tuning, no RAG -- a manual loop over a
plain HTTP call to the configured provider.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from model_service import ModelService

from .providers import LLMProvider, get_provider
from .tools import TOOL_IMPLS, TOOL_SPECS

logger = logging.getLogger("shelf_life.assistant")

MAX_TOOL_ROUNDS = 4

SYSTEM_PROMPT = """You are the in-app assistant for Shelf-Life Studio, a McGill Food Science \
research platform that predicts cheese shelf life from formulation, processing, packaging, \
and storage-condition data.

You can answer:
- what the project is about and how its pipeline/models work
- what a dataset feature means
- dataset statistics (products, ingredients, indicators, packaging, categories)
- which model performs best and its metrics
- shelf-life predictions for a given formulation
- treatment-vs-control comparisons
- why a prediction came out the way it did (explanations)
- general food-science background (spoilage mechanisms, preservation techniques) from your \
own knowledge

HARD RULE: you must NEVER invent a project-specific number -- a dataset statistic, a model \
metric, a prediction, an explanation, or a reference/provenance fact. For any question that \
needs one of those, call the matching tool and report only what it returns. If a tool \
returns an error, tell the user what went wrong rather than guessing a number. General \
food-science knowledge (e.g. "why does low water activity slow spoilage") does not require a \
tool call.

Keep answers concise and concrete. When you report numbers from a tool, use them exactly as \
returned (round sensibly for readability, but don't alter the underlying value)."""


class AssistantService:
    def __init__(self, model_service: ModelService, provider: LLMProvider | None = None):
        self.services = {"model_service": model_service}
        self.provider = provider or get_provider()

    def _page_context_message(self, page_context: dict[str, Any] | None) -> dict[str, Any] | None:
        if not page_context:
            return None
        return {
            "role": "system",
            "content": "Current app context (use only as hints for tool arguments -- never as facts to state directly): "
            + json.dumps(page_context),
        }

    def chat(self, history: list[dict[str, str]], page_context: dict[str, Any] | None = None) -> dict[str, Any]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        ctx_msg = self._page_context_message(page_context)
        if ctx_msg:
            messages.append(ctx_msg)
        messages.extend(history)

        tool_trace: list[dict[str, Any]] = []
        for _ in range(MAX_TOOL_ROUNDS):
            reply = self.provider.chat(messages, TOOL_SPECS)
            if not reply.tool_calls:
                return {"reply": reply.content or "", "tool_calls": tool_trace}

            args_as_string = self.provider.ARGS_AS_JSON_STRING
            messages.append({"role": "assistant", "content": reply.content or "", "tool_calls": [
                {"id": tc["id"], "type": "function", "function": {
                    "name": tc["name"],
                    "arguments": json.dumps(tc["arguments"], default=str) if args_as_string else tc["arguments"],
                }}
                for tc in reply.tool_calls
            ]})
            for tc in reply.tool_calls:
                name = tc["name"]
                args = tc["arguments"] or {}
                impl = TOOL_IMPLS.get(name)
                if impl is None:
                    result: dict[str, Any] = {"error": f"Unknown tool: {name}"}
                else:
                    try:
                        result = impl(self.services, **args)
                    except Exception as exc:  # noqa: BLE001 -- reported to the model, not raised
                        logger.exception("tool %s failed", name)
                        result = {"error": str(exc)}
                tool_trace.append({"name": name, "arguments": args, "result": result})
                # tool_call_id lets strict OpenAI-schema providers (Groq) match this
                # result back to its originating call; Ollama ignores the extra field.
                messages.append({
                    "role": "tool", "tool_call_id": tc["id"],
                    "content": json.dumps({"tool": name, "result": result}, default=str),
                })

        # Ran out of tool rounds -- ask once more for a final plain answer, no tools.
        final = self.provider.chat(messages, tools=[])
        return {"reply": final.content or "I wasn't able to finish that request.", "tool_calls": tool_trace}
