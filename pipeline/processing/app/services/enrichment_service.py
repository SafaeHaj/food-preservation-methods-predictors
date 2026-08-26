"""Fills `ingredient_molecular_features` and `matrix_profiles` from PubChem and USDA.

Idempotent by design, because a corpus-wide catalogue is asked about the same name from
every paper that mentions it: an ingredient already resolved or already known-missing for a
provider is skipped, and a provider merely down gets `ENRICHMENT_MAX_ATTEMPTS` more tries
before it stops being retried on every run. `ingredient_external_lookups` is the ledger that
makes this possible; `matrix_profiles` has no equivalent per-provider ledger of its own, so a
matrix is only ever attempted while `fetched_at` is still null -- a clean USDA miss on a
matrix is logged, not recorded, and stays retried on the next run (see the module's caller).

Follows the same fill-never-overwrite rule as `science_writer.py`: a field a paper or an
earlier fetch already supplied is never replaced.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from shared.config import get_processing_settings
from shared.db.models import (
    Ingredient, IngredientExternalLookup, IngredientMolecularFeature, MatrixProfile,
)
from shared.schemas.science import ENRICHABLE_CLASSES

logger = logging.getLogger(__name__)


def _get_lookup(db: Session, ingredient_id: int,
                provider: str) -> Optional[IngredientExternalLookup]:
    return (
        db.query(IngredientExternalLookup)
        .filter(IngredientExternalLookup.ingredient_id == ingredient_id,
                IngredientExternalLookup.provider == provider)
        .first()
    )


def _due(lookup: Optional[IngredientExternalLookup], max_attempts: int) -> bool:
    """Never asked, or asked and merely failed, under the attempts cap. A clean `not_found`
    is a real answer and is never retried."""
    if lookup is None:
        return True
    return lookup.status == "error" and lookup.attempts < max_attempts


def enrich_ingredients(db: Session, client, limit: Optional[int] = None) -> dict:
    """Fill `ingredient_molecular_features` for ingredients PubChem can plausibly resolve.

    Scoped to `ENRICHABLE_CLASSES`: those are the functional classes whose members are
    single compounds, so a name resolves to one CID. Everything else (essential oils,
    proteins, ...) is a mixture, and a mixture name resolving to one CID is a request that
    can only ever name the wrong thing.
    """
    settings = get_processing_settings()
    query = (
        db.query(Ingredient)
        .filter(Ingredient.functional_class.in_(ENRICHABLE_CLASSES))
        .order_by(Ingredient.id)
    )
    if limit:
        query = query.limit(limit)

    found = not_found = errors = skipped = 0
    for ingredient in query.all():
        lookup = _get_lookup(db, ingredient.id, client.provider)
        if not _due(lookup, settings.ENRICHMENT_MAX_ATTEMPTS):
            skipped += 1
            continue

        try:
            result = client.lookup_ingredient(ingredient.ingredient_name)
        except Exception as exc:
            logger.warning("%s: lookup failed for ingredient %r: %s",
                           client.provider, ingredient.ingredient_name, exc)
            _record_lookup(db, lookup, ingredient.id, client.provider,
                           status="error", detail=str(exc)[:500], bump_attempts=True)
            errors += 1
            continue

        if not result.found:
            _record_lookup(db, lookup, ingredient.id, client.provider, status="not_found")
            not_found += 1
            continue

        _fill_molecular_features(db, ingredient.id, client.provider, result)
        _record_lookup(db, lookup, ingredient.id, client.provider,
                       status="found", external_id=result.external_id)
        found += 1

    db.flush()
    return {"found": found, "not_found": not_found, "errors": errors, "skipped": skipped}


def _record_lookup(db: Session, existing: Optional[IngredientExternalLookup], ingredient_id: int,
                   provider: str, *, status: str, external_id: Optional[str] = None,
                   detail: Optional[str] = None, bump_attempts: bool = False) -> None:
    if existing is None:
        db.add(IngredientExternalLookup(
            ingredient_id=ingredient_id, provider=provider, status=status,
            external_id=external_id, detail=detail,
            attempts=1 if bump_attempts else 0, checked_at=datetime.utcnow(),
        ))
        return
    existing.status = status
    existing.external_id = external_id or existing.external_id
    existing.detail = detail
    existing.checked_at = datetime.utcnow()
    if bump_attempts:
        existing.attempts = (existing.attempts or 0) + 1


def _fill_molecular_features(db: Session, ingredient_id: int, provider: str, result) -> None:
    """Fill-never-overwrite, same rule `science_writer._get_or_create_ingredient` applies."""
    features = db.get(IngredientMolecularFeature, ingredient_id)
    if features is None:
        features = IngredientMolecularFeature(
            ingredient_id=ingredient_id, source=provider,
            external_id=result.external_id, fetched_at=datetime.utcnow(),
        )
        db.add(features)
    for column, value in result.fields.items():
        if getattr(features, column, None) is None:
            setattr(features, column, value)


def enrich_matrices(db: Session, client, limit: Optional[int] = None) -> dict:
    """Fill `matrix_profiles` composition fields from USDA for matrices never fetched.

    No idempotency ledger exists for matrices (unlike ingredients): a matrix is a candidate
    exactly while `fetched_at` is null. A clean USDA miss is logged and left null rather than
    recorded, so it is retried on the next run rather than permanently skipped -- the schema
    has no column to distinguish "asked, found nothing" from "never asked" for a matrix.
    """
    query = db.query(MatrixProfile).filter(MatrixProfile.fetched_at.is_(None)).order_by(
        MatrixProfile.id)
    if limit:
        query = query.limit(limit)

    found = not_found = errors = 0
    for profile in query.all():
        try:
            result = client.lookup_matrix(profile.matrix_name)
        except Exception as exc:
            logger.warning("%s: lookup failed for matrix %r: %s",
                           client.provider, profile.matrix_name, exc)
            errors += 1
            continue

        if not result.found:
            logger.info("%s: no match for matrix %r", client.provider, profile.matrix_name)
            not_found += 1
            continue

        for column, value in result.fields.items():
            if getattr(profile, column, None) is None:
                setattr(profile, column, value)
        profile.source = client.provider
        profile.external_id = result.external_id
        profile.fetched_at = datetime.utcnow()
        found += 1

    db.flush()
    return {"found": found, "not_found": not_found, "errors": errors}
