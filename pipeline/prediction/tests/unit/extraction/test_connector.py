"""The mock connector produces the canonical frames and validates clean."""

from __future__ import annotations

from app.database import columns as C
from app.extraction.connectors import MockConnector
from app.extraction.services import ExtractionService


def test_mock_connector_columns():
    conn = MockConnector()
    assert list(conn.get_experiments().columns) == C.EXPERIMENT_COLUMNS
    assert list(conn.get_ingredients().columns) == C.INGREDIENT_COLUMNS
    assert list(conn.get_indicators().columns) == C.INDICATOR_COLUMNS
    assert (
        list(conn.get_experiment_ingredients().columns)
        == C.EXPERIMENT_INGREDIENT_COLUMNS
    )
    assert list(conn.get_measurements().columns) == C.MEASUREMENT_COLUMNS


def test_extraction_service_validates_clean():
    data = ExtractionService().extract()  # raises ConcordanceError if not concordant
    assert len(data.experiments) > 0
    assert len(data.measurements) > 0
