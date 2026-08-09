"""Gold: assemble from Silver, then ask the model only for what prose alone carries.

The one model call in the data path. It is given arms the gate already built and is asked
for `treatment` and `weight_g` — two fields no structural test can reach, because they
exist only as a sentence in a methods section.

There is deliberately no fallback to the bare bundle on failure. An arm with no protocol
and no mass looks exactly like a paper that described neither, and a silent degradation
that produces plausible-looking rows is worse than a job that fails and says why.
"""

from __future__ import annotations

import logging

from shared.config import get_processing_settings
from shared.schemas.science import GoldBundle, ProtocolReply

from app.services import timings
from app.services.gold import prompt as gold_prompt
from app.services.gold.assemble import heuristic_bundle
from app.services.gold.evidence import score_bundle
from app.services.gold.protocols import apply as apply_protocols
from app.services.llm import CHARS_PER_TOKEN, LLMPromptTooLarge

logger = logging.getLogger(__name__)
_settings = get_processing_settings()

#: One retry at half the budget. A second would be the same prompt shape failing again.
MAX_BUDGET_RETRIES = 1


def build(package: dict, client, index: dict, vocabulary=None) -> tuple[GoldBundle, dict]:
    """Returns (bundle, what the call cost and produced)."""
    bundle = heuristic_bundle(package, vocabulary)
    slug = package["paper_slug"]
    # The lower of the configured ceiling and what this provider's window affords, so a
    # move from a 16k local model to a 200k hosted one widens the prompt by itself.
    budget = min(_settings.LLM_MAX_PROMPT_CHARS, client.prompt_budget_chars)

    for attempt in range(MAX_BUDGET_RETRIES + 1):
        # Rebuilt each attempt: `fit_to_budget` mutates the payload it is given.
        payload = gold_prompt.build_payload(package, bundle)
        user_prompt = gold_prompt.fit_to_budget(payload, budget)
        logger.info(
            "%s: gold prompt ~%d tokens over %d arms",
            slug, int((len(gold_prompt.GOLD_SYSTEM_PROMPT) + len(user_prompt)) / CHARS_PER_TOKEN),
            len(bundle.experiments),
        )
        try:
            with timings.stage_timer("gold", slug, prompt_chars=len(user_prompt)):
                result = client.json_completion(
                    system_prompt=gold_prompt.GOLD_SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    schema=ProtocolReply.model_json_schema(),
                    cache_scope="gold",
                    paper=slug,
                )
            break
        except LLMPromptTooLarge:
            if attempt == MAX_BUDGET_RETRIES:
                raise
            budget //= 2
            logger.info("%s: the provider refused the prompt as too long — rebuilding at "
                        "%d chars and trying once more", slug, budget)

    bundle, summary = apply_protocols(bundle, result.payload)
    score_bundle(bundle, index)
    return bundle, {
        **summary,
        "provider": client.provider,
        "model": client.model,
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "seconds": result.latency_seconds,
        "from_cache": result.from_cache,
    }
