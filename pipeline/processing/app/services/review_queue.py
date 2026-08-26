"""Terms the pipeline could not name, parked for a person to name.

Fed from both stages, which is why this sits at the service root rather than under `silver/`:
Silver contributes the substances and quantities no vocabulary entry matched, Gold the
protocol sentences whose keywords matched two treatment families at once.

Neither producer writes here itself. `Vocabulary` holds no `Session` and is built once per
paper, and `classify` is a pure keyword module behind an `lru_cache`; giving either one a
database would make the vocabulary layer untestable without one. Each collects instead, and
`ingestion` drains — it is the one place holding both the session and the paper.

Nothing here decides anything. A queued term keeps the sink value it was already given, so
the row still lands in the dataset; the queue only records that a human owes it a decision.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from shared.db.models import User, VocabularyReviewQueue
from shared.errors import NotFoundError
from shared.science.gate import canonical_key
from shared.uow import unit_of_work

from app.schemas.vocabulary_review import ReviewEntryOut, ReviewEntryUpdate

logger = logging.getLogger(__name__)

#: Highest occurrences first: the term blocking forty papers is the one worth a curator's
#: time, and `id` breaks ties so paging is stable.
_ORDER = (VocabularyReviewQueue.occurrences.desc(), VocabularyReviewQueue.id.asc())


def enqueue(db: Session, kind: str, raw_text: str, paper_id: Optional[int] = None) -> bool:
    """Record one unnameable term. True when this opened a row rather than bumping one.

    Deduplicated on `(kind, canonical_key)`: the same substance met in forty papers is one
    row with `occurrences = 40`, which is what makes the queue triageable at all — and what
    lets it be worked highest-first, since the term blocking forty papers is the one worth
    a curator's time.

    A `resolved` row whose term turns up again reopens. Resolving means "I added this to the
    vocabulary", and meeting it again is proof that did not take effect — a stale `resolved`
    would hide the term forever. A `rejected` row does not reopen: rejection is a standing
    decision that the string is not a term, and re-queueing it every paper is the loop that
    decision exists to end.
    """
    text = str(raw_text or "").strip()
    if not text:
        return False
    key = canonical_key(text)
    if not key:
        return False

    entry = (
        db.query(VocabularyReviewQueue)
        .filter(VocabularyReviewQueue.kind == kind,
                VocabularyReviewQueue.canonical_key == key)
        .first()
    )
    if entry is None:
        db.add(VocabularyReviewQueue(
            kind=kind, raw_text=text, canonical_key=key, status="pending",
            occurrences=1, first_seen_paper_id=paper_id, last_seen_at=datetime.utcnow(),
        ))
        return True

    entry.occurrences = (entry.occurrences or 0) + 1
    entry.last_seen_at = datetime.utcnow()
    if entry.status == "resolved":
        entry.status = "pending"
        entry.resolved_at = None
        entry.resolved_by = None
    return False


def drain(db: Session, terms: Iterable[tuple[str, str]],
          paper_id: Optional[int] = None) -> dict:
    """Enqueue every `(kind, raw_text)` a stage collected. Returns a small summary."""
    opened = met = 0
    for kind, raw_text in terms:
        if enqueue(db, kind, raw_text, paper_id):
            opened += 1
        met += 1
    if met:
        logger.info("Review queue: %d term(s) queued for paper %s, %d new",
                    met, paper_id, opened)
    return {"queued": met, "opened": opened}


# ── The curator's side ────────────────────────────────────────────────────────

def list_entries(db: Session, kind: Optional[str] = None,
                 status: Optional[str] = None) -> list[ReviewEntryOut]:
    """The queue, worked highest-occurrence first.

    Not scoped to a project: what a term means is a fact about the term, and the queue is
    corpus-wide for the same reason `ingredients` and `matrix_profiles` are.
    """
    query = db.query(VocabularyReviewQueue)
    if kind:
        query = query.filter(VocabularyReviewQueue.kind == kind)
    if status:
        query = query.filter(VocabularyReviewQueue.status == status)
    return [ReviewEntryOut.model_validate(row) for row in query.order_by(*_ORDER).all()]


def update_entry(db: Session, entry_id: int, body: ReviewEntryUpdate,
                 user: User) -> ReviewEntryOut:
    """Record a curator's ruling on one term.

    Deliberately does not touch `vocabulary.yaml`. `resolved` means "I have added this term",
    and the next paper that meets it either resolves cleanly or reopens the row -- which is
    what makes a ruling that never took effect visible instead of silently closed. Writing
    the YAML from here would put a machine back in the loop this queue exists to break.
    """
    entry = db.get(VocabularyReviewQueue, entry_id)
    if entry is None:
        raise NotFoundError.for_resource("Review entry", entry_id)

    with unit_of_work(db):
        entry.status = body.status
        if body.note is not None:
            entry.note = body.note
        settled = body.status in ("resolved", "rejected")
        entry.resolved_at = datetime.utcnow() if settled else None
        entry.resolved_by = user.id if settled else None

    return ReviewEntryOut.model_validate(entry)
