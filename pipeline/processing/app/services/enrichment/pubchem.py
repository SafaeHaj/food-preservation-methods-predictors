"""PubChem PUG-REST: name -> CID -> the molecular properties `ingredient_molecular_features`
models.

No key needed. Two calls per ingredient: resolve the name to a CID, then ask that CID for
properties. `pKa` is never requested -- PUG-REST does not carry it as a property, only as
free text buried in the annotation view, and a value that does not parse cleanly from prose
is worse than the null the schema already allows for it.
"""

from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import quote

import httpx

from app.services.enrichment.base import EnrichmentResult

logger = logging.getLogger(__name__)

#: PUG-REST property names -> the `ingredient_molecular_features` column they fill.
_PROPERTIES = {
    "MolecularWeight": "molecular_weight",
    "XLogP": "logp",
    "HBondDonorCount": "hbd_count",
    "HBondAcceptorCount": "hba_count",
}


class PubChemClient:
    provider = "pubchem"

    def __init__(self, base_url: str, timeout: float = 15.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def lookup_ingredient(self, name: str) -> EnrichmentResult:
        cid = self._resolve_cid(name)
        if cid is None:
            return EnrichmentResult(found=False)

        properties = self._fetch_properties(cid)
        fields = {
            column: properties[prop]
            for prop, column in _PROPERTIES.items()
            if prop in properties and properties[prop] is not None
        }
        return EnrichmentResult(found=True, external_id=str(cid), fields=fields)

    def _resolve_cid(self, name: str) -> Optional[int]:
        url = f"{self._base_url}/compound/name/{quote(name, safe='')}/cids/JSON"
        response = httpx.get(url, timeout=self._timeout)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        cids = response.json().get("IdentifierList", {}).get("CID", [])
        return cids[0] if cids else None

    def _fetch_properties(self, cid: int) -> dict:
        props = ",".join(_PROPERTIES)
        url = f"{self._base_url}/compound/cid/{cid}/property/{props}/JSON"
        response = httpx.get(url, timeout=self._timeout)
        response.raise_for_status()
        rows = response.json().get("PropertyTable", {}).get("Properties", [])
        return rows[0] if rows else {}
