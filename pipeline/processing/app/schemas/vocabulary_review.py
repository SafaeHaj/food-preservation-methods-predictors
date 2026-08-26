"""Request and response models for the vocabulary review queue."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from shared.schemas.science import REVIEW_STATUSES


class ReviewEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    #: What was being decided: ingredient, indicator, treatment or application.
    kind: str
    #: The paper's own wording, which is what a curator needs to see to rule on it.
    raw_text: str
    status: str
    #: How many times the corpus has hit this term. The queue is worked highest-first.
    occurrences: int
    first_seen_paper_id: Optional[int] = None
    last_seen_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[int] = None
    note: Optional[str] = None


class ReviewEntryUpdate(BaseModel):
    """A curator's ruling.

    `status` only, plus the reason. `kind`, `raw_text` and `canonical_key` are what the
    pipeline observed and what dedupes the row -- editing them would either collide with
    another entry or silently detach this one from the term it was raised for.

    Resolving does not touch `vocabulary.yaml`. Adding the term stays a file edit: a machine
    widening its own vocabulary from an endpoint is the loop this queue exists to break.
    """

    status: str
    note: Optional[str] = None

    @field_validator("status")
    @classmethod
    def _status(cls, value: str) -> str:
        # Validated against the tuple rather than a Literal retyped here, for the reason
        # `shared.schemas.science` exists: one edit point, and the CHECK constraint agrees.
        assert value in REVIEW_STATUSES, f"status must be one of {REVIEW_STATUSES}"
        return value
