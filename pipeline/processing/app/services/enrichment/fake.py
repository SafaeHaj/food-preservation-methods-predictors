"""A client that answers from a script, so enrichment tests need no network and no key --
the same role `FakeLLMClient` plays for the Gold call.
"""

from __future__ import annotations

from app.services.enrichment.base import EnrichmentResult


class FakeEnrichmentClient:
    """`results` maps a name to its `EnrichmentResult`; anything else is a clean miss.
    `raises` maps a name to an exception, for exercising the error path."""

    def __init__(self, provider: str, results: dict | None = None,
                 raises: dict | None = None) -> None:
        self.provider = provider
        self.results = results or {}
        self.raises = raises or {}
        self.calls: list[str] = []

    def _answer(self, name: str) -> EnrichmentResult:
        self.calls.append(name)
        if name in self.raises:
            raise self.raises[name]
        return self.results.get(name, EnrichmentResult(found=False))

    def lookup_ingredient(self, name: str) -> EnrichmentResult:
        return self._answer(name)

    def lookup_matrix(self, name: str) -> EnrichmentResult:
        return self._answer(name)
