"""External enrichment (§5.2.9): found/not_found/error paths and idempotency.

Every test runs against `FakeEnrichmentClient`, the same role `FakeLLMClient` plays for the
Gold call, so the suite needs no network and no provider key.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.db.database import Base
from shared.db.models import (
    Ingredient, IngredientExternalLookup, IngredientMolecularFeature, MatrixProfile,
)

from app.services import enrichment_service
from app.services.enrichment import EnrichmentResult, FakeEnrichmentClient


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _ingredient(db, name: str, functional_class: str = "phenol") -> Ingredient:
    ingredient = Ingredient(ingredient_name=name, functional_class=functional_class,
                            source_category="plant")
    db.add(ingredient)
    db.flush()
    return ingredient


# ─── Ingredients: found / not_found / error ────────────────────────────────────

def test_a_found_ingredient_fills_molecular_features_and_records_the_lookup(db):
    carvacrol = _ingredient(db, "Carvacrol")
    client = FakeEnrichmentClient("pubchem", results={
        "Carvacrol": EnrichmentResult(found=True, external_id="10364",
                                      fields={"molecular_weight": 150.22, "logp": 3.8}),
    })

    report = enrichment_service.enrich_ingredients(db, client)
    db.flush()

    assert report == {"found": 1, "not_found": 0, "errors": 0, "skipped": 0}
    features = db.get(IngredientMolecularFeature, carvacrol.id)
    assert features.molecular_weight == 150.22
    assert features.logp == 3.8
    assert features.source == "pubchem"

    lookup = db.query(IngredientExternalLookup).one()
    assert lookup.status == "found"
    assert lookup.external_id == "10364"


def test_a_clean_miss_is_recorded_and_never_retried(db):
    _ingredient(db, "Zzz Novel Compound")
    client = FakeEnrichmentClient("pubchem")   # empty script: every lookup is a clean miss

    report = enrichment_service.enrich_ingredients(db, client)
    assert report["not_found"] == 1
    assert client.calls == ["Zzz Novel Compound"]

    # A second run does not ask again: `not_found` is a real answer, not a pending retry.
    report = enrichment_service.enrich_ingredients(db, client)
    assert report == {"found": 0, "not_found": 0, "errors": 0, "skipped": 1}
    assert client.calls == ["Zzz Novel Compound"]


def test_a_transport_error_is_retried_up_to_the_attempts_cap(db):
    _ingredient(db, "Flaky Compound")
    client = FakeEnrichmentClient("pubchem", raises={"Flaky Compound": RuntimeError("timeout")})

    for _ in range(3):   # ENRICHMENT_MAX_ATTEMPTS default
        report = enrichment_service.enrich_ingredients(db, client)
        assert report["errors"] == 1

    lookup = db.query(IngredientExternalLookup).one()
    assert lookup.status == "error"
    assert lookup.attempts == 3

    # The cap is reached: a fourth run does not ask again.
    report = enrichment_service.enrich_ingredients(db, client)
    assert report == {"found": 0, "not_found": 0, "errors": 0, "skipped": 1}


def test_fill_never_overwrites_an_existing_value(db):
    """A field a paper already supplied, or an earlier fetch already filled, is never
    replaced by a later one -- the same rule `science_writer` applies to ingredients and
    matrices."""
    ingredient = _ingredient(db, "Thymol")
    db.add(IngredientMolecularFeature(ingredient_id=ingredient.id, molecular_weight=150.22))
    db.flush()
    client = FakeEnrichmentClient("pubchem", results={
        "Thymol": EnrichmentResult(found=True, external_id="6989",
                                   fields={"molecular_weight": 999.0, "logp": 3.3}),
    })

    enrichment_service.enrich_ingredients(db, client)
    db.flush()

    features = db.get(IngredientMolecularFeature, ingredient.id)
    assert features.molecular_weight == 150.22   # untouched
    assert features.logp == 3.3                  # filled, was null


def test_only_single_compound_classes_are_attempted(db):
    """A mixture like an essential oil resolves to the wrong CID by name alone, so it is
    never even asked (§5.2.9's `ENRICHABLE_CLASSES` scoping)."""
    _ingredient(db, "Thyme Essential Oil", functional_class="essential oil")
    client = FakeEnrichmentClient("pubchem")

    report = enrichment_service.enrich_ingredients(db, client)
    assert report == {"found": 0, "not_found": 0, "errors": 0, "skipped": 0}
    assert client.calls == []


# ─── Matrices ───────────────────────────────────────────────────────────────────

def test_a_found_matrix_fills_composition_and_marks_fetched(db):
    db.add(MatrixProfile(matrix_name="Chicken breast", source="manual"))
    db.flush()
    client = FakeEnrichmentClient("usda", results={
        "Chicken breast": EnrichmentResult(
            found=True, external_id="171077",
            fields={"moisture_percent": 74.8, "protein_percent": 23.1}),
    })

    report = enrichment_service.enrich_matrices(db, client)
    assert report == {"found": 1, "not_found": 0, "errors": 0}

    profile = db.query(MatrixProfile).one()
    assert profile.moisture_percent == 74.8
    assert profile.source == "usda"
    assert profile.fetched_at is not None


def test_a_matrix_already_fetched_is_not_retried(db):
    from datetime import datetime
    db.add(MatrixProfile(matrix_name="Pork", source="usda", fetched_at=datetime.utcnow()))
    db.flush()
    client = FakeEnrichmentClient("usda")

    report = enrichment_service.enrich_matrices(db, client)
    assert report == {"found": 0, "not_found": 0, "errors": 0}
    assert client.calls == []
