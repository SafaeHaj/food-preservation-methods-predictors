"""The one shape both clients return, so the driver never branches on provider.

PubChem and USDA share nothing beyond "HTTP call, might not know the name" -- no common
request shape, no shared auth, no shared pagination. What they share is the shape of an
answer, which is what `enrichment_service` actually consumes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class EnrichmentResult:
    """One provider's answer about one name.

    `found=False` with no exception is a real, cacheable answer -- "this provider does not
    know this name" -- not a failure. A transport or parse error is raised by the client
    instead, so the driver can tell "asked and got nothing" from "could not ask" and record
    `not_found` against the former, `error` against the latter.
    """

    found: bool
    external_id: Optional[str] = None
    fields: dict = field(default_factory=dict)
