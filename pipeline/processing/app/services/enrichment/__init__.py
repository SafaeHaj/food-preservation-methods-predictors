"""Ingredient and matrix enrichment from external reference data (PubChem, USDA).

Each client answers one question: given a name, what does the provider know, or nothing.
`enrichment_service` is the idempotent driver that decides who still needs asking and writes
what comes back; the clients here do no persistence and hold no session.
"""

from __future__ import annotations

from app.services.enrichment.base import EnrichmentResult
from app.services.enrichment.fake import FakeEnrichmentClient
from app.services.enrichment.pubchem import PubChemClient
from app.services.enrichment.usda import UsdaClient

__all__ = ["EnrichmentResult", "FakeEnrichmentClient", "PubChemClient", "UsdaClient"]
