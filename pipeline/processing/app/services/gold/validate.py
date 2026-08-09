"""Cross-record rules the per-record models cannot express.

A Pydantic model can say a functional class is one of seven; it cannot say that a
measurement references an indicator this arm declares, that a treatment is not secretly an
ingredient name, or that the number of arms the gate found matches the number of groups the
methods describe. Those need the whole bundle.

Never raises. One pass shows everything wrong at once, and an empty list means the bundle
is internally consistent — which is what makes this usable as a report rather than a gate.
"""

from __future__ import annotations

import json
from typing import Optional

from shared.schemas.science import GoldBundle, UNCLASSIFIED_CLASS, UNKNOWN_SOURCE
from shared.science.gate import canonical_key, parse_dosed_label

from app.services.gold.evidence import searchable
from app.services.silver.vocabulary import (
    UNRESOLVED_INDICATOR, UNSPECIFIED_UNIT, build_vocabulary,
)

SUMMARY_CHARS = 60
VALUE_DECIMALS = 4

#: Words that fill the `treatment` field without describing a procedure. A null says the
#: same thing honestly, and is distinguishable downstream from a real answer.
_PLACEHOLDER_TREATMENT = {"none", "na", "n_a", "nil", "not_specified", "not_stated",
                          "not_reported", "not_described", "unknown", "unspecified", "control"}


def _short(text) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= SUMMARY_CHARS else text[:SUMMARY_CHARS - 1] + "…"


def _violation(rule: str, table: str, key: str, detail: str) -> dict:
    return {"rule": rule, "table": table, "key": key, "detail": detail}


def _check_treatment(record, key, substances):
    """No vocabulary applies to free prose. What is checkable is that it is a protocol and
    not one of the things the schema keeps elsewhere."""
    if record.treatment_description is None:
        if record.measurements:
            yield _violation(
                "arm_needs_a_protocol", "experiments", key,
                "the study measured this arm but no protocol was extracted for it")
        return
    description = record.treatment_description
    if canonical_key(description) in _PLACEHOLDER_TREATMENT:
        yield _violation(
            "treatment_must_not_be_a_placeholder", "experiments", key,
            f"{_short(description)!r} says nothing — a null would say the same honestly")
    if canonical_key(description) in substances:
        yield _violation(
            "treatment_must_not_be_an_ingredient", "experiments", key,
            f"{_short(description)!r} is also an ingredient name")
    if parse_dosed_label(description):
        yield _violation(
            "dose_belongs_in_concentration", "experiments", key,
            f"{_short(description)!r} carries an amount — it belongs in concentration")


def _check_attribution(record, key, index):
    """No value without a source.

    A null field is exempt: absence of a span is how "never addressed" is recorded,
    distinct from "the paper says there was none".
    """
    attributed = {span.field_name for span in record.evidence}
    for field_name in ("treatment_description", "sample_weight_g"):
        if getattr(record, field_name) is not None and field_name not in attributed:
            yield _violation(
                f"{field_name}_needs_evidence", "experiments", key,
                f"{field_name} is set, but no evidence span says where it came from")
    if index is None:
        return
    for span in record.evidence:
        if span.docling_item_ref not in index:
            yield _violation(
                "evidence_ref_must_resolve", "evidence", f"{key}/{span.field_name}",
                f"{span.docling_item_ref!r} is not an item the model was shown")


def _check_ingredients(record, key, vocabulary):
    declared = {item.ingredient_name for item in record.ingredients}
    for item in record.ingredients:
        if vocabulary.resolve(item.ingredient_name, "ingredient") is None:
            yield _violation(
                "ingredient_must_be_in_vocabulary", "ingredients", item.ingredient_name,
                "not a known substance — a table read as a catalogue by shape alone")
        if item.functional_class == UNCLASSIFIED_CLASS:
            yield _violation(
                "ingredient_needs_a_functional_class", "ingredients", item.ingredient_name,
                "unclassified — add functional_class to vocabulary.yaml")
        if item.source_category == UNKNOWN_SOURCE:
            yield _violation(
                "ingredient_needs_a_source", "ingredients", item.ingredient_name,
                "unknown origin — add source to vocabulary.yaml")
    for link in record.experiment_ingredients:
        if link.ingredient_name not in declared:
            yield _violation(
                "link_must_reference_a_declared_ingredient", "experiment_ingredients",
                f"{key}/{link.ingredient_name}", "no matching ingredient record")
        elif link.concentration is None:
            yield _violation(
                "link_needs_a_concentration", "experiment_ingredients",
                f"{key}/{link.ingredient_name}", "no amount was read for this arm")
        elif link.concentration_ppm is None:
            # A stated dose that would not convert: the unit carries no mass basis, or
            # names a relative composition. Distinct from the case above, and the reason
            # `concentration_ppm` is nullable rather than defaulted to zero.
            yield _violation(
                "dose_must_be_convertible_to_ppm", "experiment_ingredients",
                f"{key}/{link.ingredient_name}",
                f"{link.concentration} {link.concentration_unit or '(no unit)'} has no "
                "mass basis, so it cannot join the ppm scale everything downstream sums")


def _check_indicators(record, key, vocabulary):
    declared = {(item.indicator_name, item.indicator_unit) for item in record.indicators}
    for item in record.indicators:
        if vocabulary.names_a_discarded_quantity(item.indicator_name):
            yield _violation(
                "indicator_must_not_be_sensory", "indicators", item.indicator_name,
                "sensory or gravimetric — should have been dropped in Silver")
        if item.indicator_name == UNRESOLVED_INDICATOR:
            yield _violation(
                "indicator_needs_a_name", "indicators", f"{key}/{item.indicator_unit}",
                "no caption or label named the quantity")
        if item.indicator_unit == UNSPECIFIED_UNIT:
            yield _violation(
                "indicator_needs_a_unit", "indicators", f"{key}/{item.indicator_name}",
                "no unit in the label and none in the vocabulary")
    for item in record.measurements:
        if (item.indicator_name, item.indicator_unit) not in declared:
            yield _violation(
                "measurement_must_reference_a_declared_indicator", "measurements",
                f"{key}/day {item.day}/{item.indicator_name}",
                "indicator not listed on this arm")


def _check_group_count(bundle):
    """The gate finds arms in the tables, the methods say how many groups the study
    defined, and neither side sees the difference alone: a phantom arm from a misread
    label, or a group whose data never reached a table."""
    expected = bundle.experimental_groups
    if not expected:
        return
    measured = sum(1 for record in bundle.experiments if record.measurements)
    if measured != expected:
        yield _violation(
            "experiment_count_must_match_the_study", "experiments", f"{measured} arms",
            f"the methods define {expected} experimental groups")


def validate(bundle: GoldBundle, index: Optional[dict] = None, vocabulary=None) -> list[dict]:
    """Every rule, over the whole bundle. Without `index` the citation rule is skipped,
    not guessed."""
    vocabulary = vocabulary or build_vocabulary()
    substances = {canonical_key(item.ingredient_name)
                  for record in bundle.experiments for item in record.ingredients}
    violations = list(_check_group_count(bundle))
    for record in bundle.experiments:
        key = (f"{record.matrix_name}/"
               f"{_short(record.treatment_description) or 'no protocol'}/"
               + (", ".join(sorted(item.ingredient_name for item in record.ingredients))
                  or "control"))
        violations += list(_check_treatment(record, key, substances))
        violations += list(_check_attribution(record, key, index))
        violations += list(_check_ingredients(record, key, vocabulary))
        violations += list(_check_indicators(record, key, vocabulary))
    return violations


def fingerprint(bundle: GoldBundle) -> dict:
    """Everything about a bundle that a change of speed or provider must not move.

    The arms, their protocols and masses, their doses and every measurement on them.
    Sorted throughout, because the order arms come out in is not part of the answer.

    This is the verification oracle: running the same papers under two providers and
    diffing the deterministic half of this is what proves the "backend assembles, model
    only reads prose" contract has no leak.
    """
    experiments = [{
        "matrix_name": record.matrix_name,
        "treatment_type": record.treatment_type,
        "treatment_description": searchable(record.treatment_description) or None,
        "sample_weight_g": (None if record.sample_weight_g is None
                            else round(record.sample_weight_g, VALUE_DECIMALS)),
        # The stated pair and the reconciled scale both, so a change to a conversion factor
        # shows up here as the deliberate change it is rather than passing unnoticed.
        "ingredients": sorted([link.ingredient_name, link.concentration,
                               link.concentration_unit, link.concentration_ppm,
                               link.application_method]
                              for link in record.experiment_ingredients),
        "measurements": sorted([item.day, item.indicator_name, item.indicator_unit,
                                round(item.indicator_value, VALUE_DECIMALS)]
                               for item in record.measurements),
        "evidence_spans": len(record.evidence),
    } for record in bundle.experiments]
    experiments.sort(key=lambda item: json.dumps(item, sort_keys=True, default=str))
    return {"experimental_groups": bundle.experimental_groups, "experiments": experiments}
