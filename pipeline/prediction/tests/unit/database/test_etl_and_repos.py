"""ETL load, repository reads, and concordance on the mock dataset."""

from __future__ import annotations

from app.core.config import load_config
from app.database.checks import run_concordance_checks
from app.extraction.services import ExtractionService
from app.services import ETLService, QueryService


def test_etl_load_and_query(db_session):
    counts = ETLService(db_session).load()
    assert counts["experiments"] == 15
    assert counts["measurements"] == 240

    query = QueryService(db_session)
    assert len(query.list_experiments()) == 15
    assert len(query.list_ingredients()) == 8
    assert len(query.measurements_for("EXP001")) == 16


def test_etl_is_idempotent(db_session):
    first = ETLService(db_session).load()
    second = ETLService(db_session).load()
    assert first == second
    assert len(QueryService(db_session).list_experiments()) == 15


def test_concordance_clean_on_mock():
    data = ExtractionService().extract()
    violations = run_concordance_checks(
        data.experiments,
        data.ingredients,
        data.experiment_ingredients,
        data.indicators,
        data.measurements,
        load_config(),
    )
    assert violations.empty
