"""The Pydantic records and the columns they land in must agree.

`shared.schemas.science` is validated against; `shared.db.models` is written to. Nothing
connects them at import time, so a field added to a record with no column behind it fails
at the INSERT -- inside a Celery worker, on paper forty, with the transaction rolled back
and the message truncated onto a job row.

These tests only assert what the writers actually rely on: every field a record carries has
a column to go in, and a field that may be `None` has a column that accepts it. Column-only
fields (surrogate keys, `project_id`, `created_at`) are the writer's business, not the
record's, so the check is deliberately one-directional.
"""

from __future__ import annotations

import pytest

from shared.db.models import Base
from shared.schemas.science import (
    EvidenceSpan, ExperimentIngredientRecord, ExperimentRecord, IndicatorRecord,
    IngredientRecord, MatrixComposition, MeasurementRecord, PaperDocument, SectionDocument,
)

#: record -> (table, fields that are not columns of it and why)
RECORD_TABLES = [
    (PaperDocument, "papers", set()),
    (SectionDocument, "sections", set()),
    (IngredientRecord, "ingredients", set()),
    # `ingredient_name` identifies the ingredient row the link points at; the junction
    # stores its id. The raw `concentration`/`concentration_unit` pair is what the paper
    # printed -- kept on the record so the derived-ppm evidence rationale can quote it,
    # while only the reconciled `concentration_ppm` is stored.
    (ExperimentIngredientRecord, "experiment_ingredients",
     {"ingredient_name", "concentration", "concentration_unit"}),
    (IndicatorRecord, "indicators", set()),
    # Likewise: a measurement names its indicator, and stores `indicator_id`.
    (MeasurementRecord, "measurements",
     {"indicator_name", "indicator_type", "indicator_unit", "indicator_threshold"}),
    # The measured composition block, whose seven fields are columns of `experiments`
    # under the same names. Checked here rather than excluded, so the pairing stays guarded.
    (MatrixComposition, "experiments", set()),
    # The nested record lists are separate tables and `evidence` has its own sink;
    # `matrix_name` resolves to `matrix_id`, and the treatment triple resolves to
    # `treatment_id` on `treatment_profiles`, which is what deduplicates them corpus-wide.
    (ExperimentRecord, "experiments",
     {"ingredients", "experiment_ingredients", "indicators", "measurements", "evidence",
      "matrix_name", "composition",
      "treatment_type", "thermal_temperature_c", "thermal_duration_min"}),
    # A span names the field it supports; `entity_type`/`entity_key` are the writer's.
    (EvidenceSpan, "evidence", set()),
]


def _cases() -> list:
    return [
        pytest.param(Base.metadata.tables[table_name], name, field,
                     id=f"{record.__name__}.{name}")
        for record, table_name, not_columns in RECORD_TABLES
        for name, field in record.model_fields.items()
        if name not in not_columns
    ]


@pytest.mark.parametrize(("table", "name", "field"), _cases())
def test_every_record_field_has_a_column(table, name, field) -> None:
    assert name in table.columns, (
        f"{table.name} has no column for {name!r}. Add it in shared.db.models and write "
        "the migration, or exclude it in RECORD_TABLES with the reason."
    )


@pytest.mark.parametrize(("table", "name", "field"), _cases())
def test_optional_fields_have_nullable_columns(table, name, field) -> None:
    if name not in table.columns or field.is_required():
        return
    column = table.columns[name]
    if column.default is not None or column.server_default is not None:
        return
    assert column.nullable, (
        f"{table.name}.{name} is NOT NULL but the record leaves it optional: a valid "
        "record would fail on write."
    )
