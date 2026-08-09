"""Building validated records out of the Silver reading, resolving nothing.

Every number is fixed by the time this returns. The model has not been called yet and will
only ever be asked for `treatment` and `weight_g` — two fields that exist solely in the
methods prose, which no structural test can reach.

Arms are keyed on `arm_key`, which Silver built from the arm's substances and their
amounts. Nothing else separates one rung of a dose ladder from the next: two arms differing
only in concentration have the same substances, the same indicators and the same days.
"""

from __future__ import annotations

import logging
from itertools import chain
from pathlib import Path
from typing import Optional

from shared.schemas.science import (
    EvidenceSpan, ExperimentIngredientRecord, ExperimentRecord, FigureDocument, GoldBundle,
    IndicatorRecord, IngredientRecord, MeasurementRecord, PaperDocument, SectionDocument,
    TableDocument,
)

from app.services.silver import units

logger = logging.getLogger(__name__)

#: What a paper whose matrix the vocabulary could not name is filed under. A real value in
#: a NOT NULL column, and visible in the normalisation report as something to fix.
UNATTRIBUTED_MATRIX = "unattributed"

#: How close an axis value must sit to a whole number to be a storage day.
_DAY_TOLERANCE = 1e-6

#: `arm_key`s for the two rows that are not arms. Distinct literals rather than "", because
#: the writer keys on `arm_key` and both would otherwise collide with a real unnamed arm.
CATALOGUE_ARM = "__catalogue__"
UNMEASURED_ARM = "__unmeasured__"


def _as_day(axis_value) -> Optional[int]:
    try:
        number = float(axis_value)
    except (TypeError, ValueError):
        return None
    if number < 0 or abs(number - round(number)) > _DAY_TOLERANCE:
        return None
    return int(round(number))


def _add_ingredients(record: ExperimentRecord, ingredients) -> None:
    known = {item.ingredient_name for item in record.ingredients}
    for item in ingredients:
        if item["name"] in known:
            continue
        known.add(item["name"])
        record.ingredients.append(IngredientRecord(
            ingredient_name=item["name"], functional_class=item["functional_class"],
            source_category=item["source"]))
        record.experiment_ingredients.append(ExperimentIngredientRecord(
            ingredient_name=item["name"], concentration=item.get("amount"),
            concentration_unit=item.get("unit")))


def collapse_replicates(readings) -> float:
    """One value out of however many readings were printed for it.

    Where a group holds both replicates and a stated mean, only the stated means are kept:
    folding one in beside the replicates behind it would weight them twice.

    Returns the value alone. The count of folded readings is not stored -- papers publish a
    mean, so a count of two says the paper printed two series for one arm, not that the
    value rests on two observations, and a column holding it would be read as the latter.
    """
    stated = [value for value, reports_mean in readings if reports_mean]
    kept = stated or [value for value, _ in readings]
    return sum(kept) / len(kept)


def build_experiments(measurements, matrix: str) -> tuple:
    """One record per arm. Returns (records, observations that sat off the day axis).

    `treatment` is left unset on purpose: it is prose the gate never reads, and the model
    supplies it later.
    """
    grouped, off_axis, folded = {}, 0, 0
    for measurement in measurements:
        day = _as_day(measurement.axis_value)
        if day is None:
            off_axis += 1
            continue
        state = grouped.get(measurement.arm_key)
        if state is None:
            record = ExperimentRecord(matrix_name=matrix, arm_key=measurement.arm_key)
            _add_ingredients(record, measurement.ingredients)
            state = grouped[measurement.arm_key] = (record, {}, {}, set())
        record, readings, indicators, seen_evidence = state

        indicator_key = (measurement.indicator, measurement.unit)
        readings.setdefault((day, *indicator_key), []).append(
            (measurement.value, measurement.reports_mean))
        indicators.setdefault(
            indicator_key, (measurement.indicator_type, measurement.threshold))

        # One span per (asset, field): a table contributing forty values is one citation,
        # not forty identical ones.
        evidence_key = (measurement.item_ref, "indicator_value")
        if measurement.item_ref and evidence_key not in seen_evidence:
            seen_evidence.add(evidence_key)
            record.evidence.append(EvidenceSpan(
                field_name="indicator_value", docling_item_ref=measurement.item_ref,
                page_number=measurement.page_number,
                source_type="figure" if measurement.is_figure else "table",
                method="stated", value_is_approximate=measurement.is_figure))

    for record, readings, indicators, _ in grouped.values():
        for (name, unit), (indicator_type, threshold) in indicators.items():
            record.indicators.append(IndicatorRecord(
                indicator_name=name, indicator_type=indicator_type,
                indicator_unit=unit, indicator_threshold=threshold))
        for (day, name, unit), values in sorted(readings.items()):
            folded += len(values) > 1
            indicator_type, threshold = indicators[(name, unit)]
            record.measurements.append(MeasurementRecord(
                day=day, indicator_name=name, indicator_type=indicator_type,
                indicator_unit=unit, indicator_value=collapse_replicates(values),
                indicator_threshold=threshold))

    return [record for record, *_ in grouped.values()], off_axis, folded


def catalogue_experiment(reading: dict, matrix: str) -> Optional[ExperimentRecord]:
    """A row for composition-table substances to hang from without pretending to be an arm.

    Its shape says so: ingredients, and not one measurement.
    """
    if not reading["catalogue"]:
        return None
    record = ExperimentRecord(matrix_name=matrix, arm_key=CATALOGUE_ARM)
    _add_ingredients(record, reading["catalogue"])
    return record


def unmeasured_experiment(matrix: str) -> ExperimentRecord:
    """A paper with no gated series still has a matrix and a protocol. Without a row to
    hang them on it would be stored as a title and nothing else."""
    return ExperimentRecord(matrix_name=matrix, arm_key=UNMEASURED_ARM)


def _paper_document(package: dict) -> PaperDocument:
    """Bibliography from what Bronze recovered, falling back to the file name.

    Docling does not reliably mark a title, so a paper whose first heading is its title is
    common and a paper whose is "1. Introduction" equally so. The file name is a poor title
    but an honest one, and the field is nullable precisely so this stays visible.
    """
    title = (package.get("title")
             or Path(package.get("source_name") or package["paper_slug"]).stem)
    return PaperDocument(
        title=title.replace("_", " ").strip() or package["paper_slug"],
        doi=package.get("doi"),
        abstract=package.get("abstract"),
        published_year=package.get("published_year"),
    )


def reconcile_doses(experiments, vocabulary=None) -> dict:
    """Put every stated dose on the ppm scale, in place. Returns the run's unit report.

    Done here rather than in `normalise` because a dose belongs to an arm, and the arm is
    what this module builds: before the links exist there is nothing to reconcile against.
    """
    report = {"converted": 0, "approximate": 0, "unconvertible": []}
    for record in experiments:
        result = units.reconcile(record.experiment_ingredients, vocabulary)
        report["converted"] += result["converted"]
        report["approximate"] += result["approximate"]
        report["unconvertible"] += result["unconvertible"]
    return report


def heuristic_bundle(package: dict, vocabulary=None) -> GoldBundle:
    """Assemble a bundle from the Silver reading. Only the prose fields are missing.

    Attaches the unit report to `package`, as `normalise` attaches its reading: the caller
    passes the bundle to a model and the report to the job result, and they travel apart.
    """
    reading = package["reading"]
    matrix = reading["matrix"]["name"] or UNATTRIBUTED_MATRIX
    experiments, off_axis, folded = build_experiments(reading["measurements"], matrix)

    catalogue = catalogue_experiment(reading, matrix)
    if catalogue:
        experiments.append(catalogue)
    if not experiments:
        experiments.append(unmeasured_experiment(matrix))
        logger.info("%s: no gated series; one row kept for the matrix and the protocol",
                    package["paper_slug"])

    unit_report = package["unit_report"] = reconcile_doses(experiments, vocabulary)

    if off_axis:
        logger.info("%s: %d observations sit off the integer-day axis",
                    package["paper_slug"], off_axis)
    if folded:
        logger.info("%s: %d measurements averaged from series printed separately",
                    package["paper_slug"], folded)
    if unit_report["unconvertible"]:
        logger.info("%s: %d doses could not be put on the ppm scale",
                    package["paper_slug"], len(unit_report["unconvertible"]))

    return GoldBundle(
        paper=_paper_document(package),
        sections=[SectionDocument(section_title=section["section_title"],
                                  content_markdown=section["content_markdown"],
                                  docling_item_ref=section.get("docling_item_ref"),
                                  page_number=section.get("page_number"))
                  for section in package.get("sections", [])],
        # Tables and figures are projected from the gated assets rather than persisted:
        # `extraction_assets` already holds the CSV, the caption, the page and the bbox.
        tables=[TableDocument(caption=table.get("caption"),
                              csv_filepath=(table.get("cleaned_csv_path")
                                            or table.get("csv_path") or ""),
                              structured_json={"gate": table.get("gate", {}),
                                               "headers": table.get("headers", [])},
                              docling_item_ref=table.get("docling_item_ref"))
                for table in chain(package.get("tables", []), package.get("references", []))],
        figures=[FigureDocument(caption=figure.get("caption"),
                                image_filepath=figure.get("image_path") or "",
                                docling_item_ref=figure.get("docling_item_ref"))
                 for figure in package.get("figures", [])],
        experiments=experiments,
    )
