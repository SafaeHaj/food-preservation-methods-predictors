"""Routes over the vocabulary review queue — the terms the pipeline could not name.

Corpus-wide rather than per project, so there is no `project_id` to authorize against:
what "nisin" is does not vary by tenant, and scoping the queue would mean one team
answering the same question another team already answered. Any authenticated user may read
and rule; the gateway has already established who they are.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from shared.db.database import get_db
from shared.db.models import User

from app.api.deps import get_current_user
from app.schemas.vocabulary_review import ReviewEntryOut, ReviewEntryUpdate
from app.services import review_queue

router = APIRouter(tags=["vocabulary-review"])


@router.get("/vocabulary-review", response_model=list[ReviewEntryOut])
def list_review_entries(
    kind: Optional[str] = Query(None, description="ingredient | indicator | treatment | application"),
    status: Optional[str] = Query(None, description="pending | resolved | rejected"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Terms awaiting a decision, the most-encountered first."""
    return review_queue.list_entries(db, kind=kind, status=status)


@router.patch("/vocabulary-review/{entry_id}", response_model=ReviewEntryOut)
def update_review_entry(
    entry_id: int,
    body: ReviewEntryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Resolve or reject one term.

    Resolving records that the vocabulary has been extended; it does not extend it. A term
    that turns up again after being resolved reopens, which is how a ruling that never
    reached `vocabulary.yaml` becomes visible.
    """
    return review_queue.update_entry(db, entry_id, body, user)
