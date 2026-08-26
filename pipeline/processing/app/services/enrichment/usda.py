"""USDA FoodData Central: matrix name -> the reference composition `matrix_profiles` models.

Needs a free API key. FDC's nutrient list is per-100g, numbered by nutrient id rather than
name, so `_NUTRIENT_IDS` maps the handful this schema cares about; anything else in the
response is left alone.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.services.enrichment.base import EnrichmentResult

logger = logging.getLogger(__name__)

#: FDC nutrient ids -> the `matrix_profiles` column they fill. moisture_percent and
#: salt_percent come from "Water" and "Sodium" respectively; sodium is converted to a rough
#: salt-equivalent percentage by the caller, not here, since that is a unit decision.
_NUTRIENT_IDS = {
    1051: "moisture_percent",   # Water, g/100g
    1004: "fat_percent",        # Total lipid (fat), g/100g
    1003: "protein_percent",    # Protein, g/100g
}


class UsdaClient:
    provider = "usda"

    def __init__(self, base_url: str, api_key: str, timeout: float = 15.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    def lookup_matrix(self, name: str) -> EnrichmentResult:
        if not self._api_key:
            raise RuntimeError("USDA_FDC_API_KEY is not set")

        fdc_id = self._search(name)
        if fdc_id is None:
            return EnrichmentResult(found=False)

        fields = self._fetch_nutrients(fdc_id)
        return EnrichmentResult(found=True, external_id=str(fdc_id), fields=fields)

    def _search(self, name: str) -> Optional[int]:
        response = httpx.get(
            f"{self._base_url}/foods/search",
            params={"query": name, "pageSize": 1, "api_key": self._api_key},
            timeout=self._timeout,
        )
        response.raise_for_status()
        foods = response.json().get("foods", [])
        return foods[0]["fdcId"] if foods else None

    def _fetch_nutrients(self, fdc_id: int) -> dict:
        response = httpx.get(
            f"{self._base_url}/food/{fdc_id}",
            params={"api_key": self._api_key},
            timeout=self._timeout,
        )
        response.raise_for_status()
        fields = {}
        for entry in response.json().get("foodNutrients", []):
            nutrient_id = (entry.get("nutrient") or {}).get("id")
            column = _NUTRIENT_IDS.get(nutrient_id)
            value = entry.get("amount")
            if column and value is not None:
                fields[column] = value
        return fields
