"""The controlled vocabularies must reach the database.

`shared.schemas.science` is meant to be the single edit point for the scientific schema:
the Pydantic records validate against its tuples and the `CHECK` constraints are built from
the same ones. Two things can silently break that.

  * Someone writes a literal list into `models.py` instead of deriving it. The models and
    the columns then disagree the moment a tuple changes.
  * Someone edits a tuple and does not write the migration that resyncs the constraints.
    `alembic --autogenerate` does not detect CHECK-constraint drift, so nothing complains
    until a production INSERT fails on a value the models accepted.

These tests are what makes "change it in one place" a guarantee rather than a convention.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from shared.db.models import Base
from shared.schemas.science import (
    APPLICATION_METHODS, EVIDENCE_METHODS, EVIDENCE_SOURCE_TYPES, EXTERNAL_LOOKUP_STATUSES,
    EXTERNAL_PROVIDERS, FUNCTIONAL_CLASSES, INDICATOR_TYPES, INGREDIENT_SOURCES,
    MATRIX_PROFILE_SOURCES, REGULATORY_STATUSES, REVIEW_KINDS, REVIEW_STATUSES,
    TREATMENT_TYPES, UNCLASSIFIED_CLASS, UNKNOWN_SOURCE, sql_values,
)

VERSIONS_DIR = Path(__file__).resolve().parents[1] / "alembic" / "versions"

#: What each vocabulary is called in a revision's `VOCABULARY_SNAPSHOT`, and the live tuple
#: it must equal. Adding a controlled vocabulary means adding a row here too.
VOCABULARIES = {
    "functional_classes": FUNCTIONAL_CLASSES + (UNCLASSIFIED_CLASS,),
    "ingredient_sources": INGREDIENT_SOURCES + (UNKNOWN_SOURCE,),
    "indicator_types": INDICATOR_TYPES,
    "evidence_methods": EVIDENCE_METHODS,
    "evidence_source_types": EVIDENCE_SOURCE_TYPES,
    "treatment_types": TREATMENT_TYPES,
    "application_methods": APPLICATION_METHODS,
    "matrix_profile_sources": MATRIX_PROFILE_SOURCES,
    "regulatory_statuses": REGULATORY_STATUSES,
    "external_providers": EXTERNAL_PROVIDERS,
    "external_lookup_statuses": EXTERNAL_LOOKUP_STATUSES,
    "review_kinds": REVIEW_KINDS,
    "review_statuses": REVIEW_STATUSES,
}

#: constraint name -> (table, the values its IN (...) list must hold)
DERIVED_CONSTRAINTS = {
    "ck_ingredients_functional_class": ("ingredients", VOCABULARIES["functional_classes"]),
    "ck_ingredients_source": ("ingredients", VOCABULARIES["ingredient_sources"]),
    "ck_indicators_type": ("indicators", VOCABULARIES["indicator_types"]),
    "ck_evidence_method": ("evidence", VOCABULARIES["evidence_methods"]),
    "ck_evidence_source_type": ("evidence", VOCABULARIES["evidence_source_types"]),
    "ck_treatment_profiles_type": ("treatment_profiles", VOCABULARIES["treatment_types"]),
    "ck_experiment_ingredients_application": (
        "experiment_ingredients", VOCABULARIES["application_methods"],
    ),
    "ck_matrix_profiles_source": ("matrix_profiles", VOCABULARIES["matrix_profile_sources"]),
    "ck_regulatory_status": ("ingredient_regulatory_status",
                             VOCABULARIES["regulatory_statuses"]),
    "ck_external_lookup_provider": ("ingredient_external_lookups",
                                    VOCABULARIES["external_providers"]),
    "ck_external_lookup_status": ("ingredient_external_lookups",
                                  VOCABULARIES["external_lookup_statuses"]),
    "ck_molecular_features_source": ("ingredient_molecular_features",
                                     VOCABULARIES["external_providers"]),
    "ck_review_queue_kind": ("vocabulary_review_queue", VOCABULARIES["review_kinds"]),
    "ck_review_queue_status": ("vocabulary_review_queue", VOCABULARIES["review_statuses"]),
}


def _revision_modules() -> dict[str, dict]:
    """Every revision, parsed statically as {revision: {down_revision, snapshot}}.

    Read with `ast` rather than imported: a revision module runs `from alembic import op`
    and is only valid inside a migration context.
    """
    revisions: dict[str, dict] = {}
    for path in VERSIONS_DIR.glob("*.py"):
        assignments: dict[str, ast.expr] = {}
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            # `revision: str = "..."` is annotated, `VOCABULARY_SNAPSHOT = {...}` is not.
            targets = (
                [node.target] if isinstance(node, ast.AnnAssign)
                else node.targets if isinstance(node, ast.Assign)
                else []
            )
            for target in targets:
                if isinstance(target, ast.Name) and node.value is not None:
                    assignments[target.id] = node.value
        if "revision" not in assignments:
            continue
        snapshot = assignments.get("VOCABULARY_SNAPSHOT")
        revisions[ast.literal_eval(assignments["revision"])] = {
            "down_revision": ast.literal_eval(assignments["down_revision"]),
            "snapshot": ast.literal_eval(snapshot) if snapshot else None,
            "path": path,
        }
    return revisions


def _head(revisions: dict[str, dict]) -> str:
    parents = {entry["down_revision"] for entry in revisions.values()}
    heads = [revision for revision in revisions if revision not in parents]
    assert len(heads) == 1, f"expected exactly one alembic head, found {sorted(heads)}"
    return heads[0]


def _latest_snapshot(revisions: dict[str, dict]) -> tuple[dict, Path]:
    """The vocabulary snapshot of the most recent revision that declares one."""
    revision = _head(revisions)
    while revision is not None:
        entry = revisions[revision]
        if entry["snapshot"] is not None:
            return entry["snapshot"], entry["path"]
        revision = entry["down_revision"]
    pytest.fail("No revision declares a VOCABULARY_SNAPSHOT")


@pytest.mark.parametrize("name", sorted(VOCABULARIES))
def test_migrations_are_synced_with_the_live_vocabulary(name: str) -> None:
    snapshot, path = _latest_snapshot(_revision_modules())
    assert tuple(snapshot.get(name, ())) == VOCABULARIES[name], (
        f"`{name}` in shared.schemas.science no longer matches the CHECK constraints the "
        f"database has, last set by {path.name}. Write a revision that drops and recreates "
        "the affected constraints with the new values, and give it a VOCABULARY_SNAPSHOT."
    )


@pytest.mark.parametrize(
    ("name", "table", "values"),
    [(name, table, values) for name, (table, values) in DERIVED_CONSTRAINTS.items()],
)
def test_constraints_are_derived_from_the_constants(
    name: str, table: str, values: tuple
) -> None:
    """The constraint's SQL must be the tuple, not a list retyped beside it."""
    constraints = {
        constraint.name: constraint
        for constraint in Base.metadata.tables[table].constraints
        if type(constraint).__name__ == "CheckConstraint"
    }
    assert name in constraints, f"{table} has no CHECK named {name}"
    assert f"IN ({sql_values(values)})" in str(constraints[name].sqltext), (
        f"{name} does not list exactly {list(values)}; build it with `sql_values(...)` over "
        "the tuple in shared.schemas.science rather than writing the values out."
    )
