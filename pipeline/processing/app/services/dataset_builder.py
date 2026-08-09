"""Turn the scientific schema into a flat dataset the prediction service can train on.

This is the seam between extraction and prediction, and it is deliberately the only thing
standing between them. Extraction owns papers, assets and the five scientific tables;
prediction owns the survival engines and the fitted artifacts. Neither knows the other's
shape. This module is what translates.

──────────────────────────────────────────────────────────────────────────────
Intended mapping (not yet implemented)
──────────────────────────────────────────────────────────────────────────────
Source::

    Experiment (meat_matrix, treatment) --< ExperimentIngredient >-- Ingredient
               \\--< Measurement (day, indicator_value) >-- Indicator (+ threshold)

Target: one row per (experiment, day), which is the grain the survival engines expect::

    experiment_id | meat_matrix | treatment | day | <ingredient cols> | <indicator cols> | event | duration

  * `meat_matrix`, `treatment`   categorical, straight from Experiment. `treatment` is
                                  nullable since the medallion pipeline landed -- a paper
                                  that never describes an arm's handling leaves it null
                                  rather than carrying an invented placeholder, so this
                                  needs an explicit "not stated" category rather than a
                                  dropna.
  * `<ingredient cols>`           one numeric column per Ingredient in the project, holding
                                  that experiment's concentration or 0. Concentrations must
                                  be unit-reconciled first -- `ExperimentIngredient` stores
                                  the paper's unit verbatim, so `2.0` can be % or mg/kg, and
                                  pivoting without normalising silently mixes scales. It is
                                  also nullable now (an additive named without a dose), which
                                  is distinct from a zero.
  * `<indicator cols>`            one numeric column per Indicator, holding the measurement
                                  at that day. Sparse: papers report different days for
                                  different indicators. Pivot on `Indicator.indicator_name`,
                                  not `indicator_type` -- the latter is now a two-valued
                                  category (microbial | chemical) and would fold every
                                  microbial count into one column.
  * `duration` / `event`          the survival label. `duration` is the first day at which
                                  an indicator crosses `Indicator.indicator_threshold`;
                                  `event=1` when a crossing was observed, `event=0` when the
                                  study ended first (right-censored -- the common case, and
                                  the reason this is a survival problem and not a
                                  regression). Experiments whose indicator has no threshold
                                  cannot be labelled and are excluded, which is what makes
                                  the editable threshold on the indicators screen a
                                  prerequisite rather than a nicety.

Open questions to settle before writing this:
  * Which indicator drives the label when several have thresholds -- first crossing, or a
    named primary indicator per project?
  * Interpolate between sampled days, or take the first sampled day at or past the
    threshold? The former invents precision the papers do not have; the latter biases
    `duration` upward by up to one sampling interval.
  * Do ingredient columns generalise across projects, or is the feature matrix
    project-local? A model trained on one project's ingredient set cannot score another's.

Until those are answered, `build` returns an empty, well-formed preview rather than a
half-decided schema. Everything downstream -- the route, the job, the Model Lab screen --
is wired and exercised against that empty result, so writing the builder is the only step
left, not the first of several.
"""

from __future__ import annotations

import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from shared.db.models import Experiment, Indicator, Ingredient, Measurement

from app.schemas.dataset import DatasetPreview, DatasetSource

logger = logging.getLogger(__name__)

#: Columns every built dataset carries regardless of the project's ingredients and
#: indicators. Declared here so the route can describe the target shape before one exists.
BASE_COLUMNS: tuple[str, ...] = (
    "experiment_id", "meat_matrix", "treatment", "day", "duration", "event",
)


def source_counts(db: Session, project_id: int) -> DatasetSource:
    """What the project has to build from.

    Real query, not a stub: the Model Lab screen needs to distinguish "nothing extracted
    yet" from "extracted, but the builder has not been written", and only the first of
    those is the user's problem to fix.
    """
    def count(model, *where) -> int:
        return db.query(func.count()).select_from(model).filter(*where).scalar() or 0

    labelable = (
        db.query(func.count(func.distinct(Indicator.id)))
        .filter(Indicator.project_id == project_id, Indicator.indicator_threshold.isnot(None))
        .scalar()
        or 0
    )

    return DatasetSource(
        experiments=count(Experiment, Experiment.project_id == project_id),
        ingredients=count(Ingredient, Ingredient.project_id == project_id),
        indicators=count(Indicator, Indicator.project_id == project_id),
        measurements=(
            db.query(func.count())
            .select_from(Measurement)
            .join(Experiment, Experiment.id == Measurement.experiment_id)
            .filter(Experiment.project_id == project_id)
            .scalar()
            or 0
        ),
        indicators_with_threshold=labelable,
    )


def preview(db: Session, project_id: int) -> DatasetPreview:
    """The current state of the project's dataset, built or not."""
    return DatasetPreview(
        project_id=project_id,
        status="not_implemented",
        columns=list(BASE_COLUMNS),
        row_count=0,
        rows=[],
        source=source_counts(db, project_id),
    )


def build(db: Session, project_id: int, progress=None) -> DatasetPreview:
    """Build the flat dataset for one project.

    Returns the same shape `preview` does, so the caller does not branch on whether a build
    just ran. Currently a no-op that reports the source counts it would have consumed.
    """
    source = source_counts(db, project_id)
    logger.info(
        "Dataset build requested for project %s (%s experiments, %s measurements, "
        "%s labelable indicators) -- builder not implemented, nothing written",
        project_id, source.experiments, source.measurements, source.indicators_with_threshold,
    )
    if progress is not None:
        progress.update(progress=100, step="Dataset builder is not implemented yet")

    return DatasetPreview(
        project_id=project_id,
        status="not_implemented",
        columns=list(BASE_COLUMNS),
        row_count=0,
        rows=[],
        source=source,
    )
