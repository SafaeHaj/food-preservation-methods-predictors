"""Merging the model's reply into the assembled bundle.

Everything here is defensive in one specific way: a malformed part of the reply costs that
part and nothing else. Each arm is validated on its own, the shared block separately, and
an `experiment_index` outside the bundle is an invented arm and is dropped. The alternative
— validating the reply as one object — means one bad field discards a paper's protocols.
"""

from __future__ import annotations

import logging

from pydantic import ValidationError

from shared.schemas.science import (
    GoldBundle, ProtocolRecord, SharedProtocol, UNCLASSIFIED_TREATMENT,
    UNSPECIFIED_APPLICATION,
)

from app.services.silver import classify

logger = logging.getLogger(__name__)

VALIDATION_MESSAGE_CHARS = 60


def _schema_problem(exc: ValidationError) -> str:
    return (f"{exc.error_count()} problems, "
            f"first: {exc.errors()[0]['msg'][:VALIDATION_MESSAGE_CHARS]}")


def _shared_protocol(payload: dict) -> SharedProtocol:
    """The paper-level half of the reply, validated apart from the arms so a malformed
    shared block costs the fallback rather than the per-arm answers beside it."""
    try:
        return SharedProtocol.model_validate(payload)
    except ValidationError as exc:
        logger.info("Shared protocol does not fit the schema — ignored (%s)",
                    _schema_problem(exc))
        return SharedProtocol()


def _needs_review(verdict, applied) -> bool:
    """Whether this decision is one a person should settle.

    Ambiguity, not absence. Two keyword families firing on one sentence is a real question
    -- the classifier refuses to rank them, so the sentence stays unclassified until someone
    says which reading is right. A sentence matching *nothing* is not queued: that is the
    arm which had no treatment, which is the common case in this corpus, and queueing it
    would bury the genuine ambiguities under every control group in the literature.

    A value that had to fall to its sink is the same question arriving by the other route:
    the model named something the closed set does not contain.
    """
    return len(verdict.matched) > 1 or applied in (UNCLASSIFIED_TREATMENT,
                                                   UNSPECIFIED_APPLICATION)


def _apply_treatment(experiment, record, queue) -> None:
    """Keywords first, the model's answer second, and nothing at all as the third option.

    The order matters: a sentence containing `mpa` is high-pressure processing whatever a
    model says about it, so the deterministic reading wins where it is decisive. Only an
    unmatched or ambiguous sentence defers to the reply.

    `treatment_type` stays None rather than falling to the sink when neither could answer.
    An arm that went through no physical treatment is the common case in this corpus, and
    filing it as "Other physical treatment" would invent a procedure -- the FK is nullable
    precisely so that absence stays sayable.
    """
    verdict = classify.classify_treatment(experiment.treatment_description)
    if verdict.confident:
        experiment.treatment_type = verdict.value
    elif record is not None and record.treatment_type is not None:
        experiment.treatment_type = classify.treatment_or_sink(record.treatment_type)
    if _needs_review(verdict, experiment.treatment_type):
        queue.append(("treatment", experiment.treatment_description))

    if experiment.treatment_type is None:
        return
    # Only meaningful once a treatment exists to qualify: "for 7 days" in a storage
    # sentence is not the duration of a thermal step.
    if record is not None and record.thermal_temperature_c is not None:
        experiment.thermal_temperature_c = record.thermal_temperature_c
    elif verdict.temperature_c is not None:
        experiment.thermal_temperature_c = verdict.temperature_c
    if record is not None and record.thermal_duration_min is not None:
        experiment.thermal_duration_min = record.thermal_duration_min
    elif verdict.duration_min is not None:
        experiment.thermal_duration_min = verdict.duration_min


def _apply_application(experiment, record, queue) -> None:
    """How the additives were applied, onto every dose link on the arm.

    One value per arm rather than per link: a paper describes one procedure for a treatment
    group, and claiming per-substance precision the prose does not carry would be fabrication.
    """
    verdict = classify.classify_application(experiment.treatment_description)
    if verdict.confident:
        method = verdict.value
    elif record is not None and record.application_method is not None:
        method = classify.application_or_sink(record.application_method)
    else:
        method = None
    # An arm with no additives has no application to describe, so nothing to ask about.
    if experiment.experiment_ingredients and _needs_review(verdict, method):
        queue.append(("application", experiment.treatment_description))
    if method is None:
        # The links keep the schema default, which happens to be the sink. Leaving them is
        # not a decision -- it is the absence of one, which is why it is not queued above
        # unless the sentence was ambiguous.
        return
    for link in experiment.experiment_ingredients:
        link.application_method = method


def apply(bundle: GoldBundle, payload: dict) -> tuple[GoldBundle, dict]:
    """Merge the reply into the bundle. Mutates, and returns it with a summary.

    An arm still without a protocol inherits the paper's shared one, and the evidence
    supporting it — so a paper that states its procedure once for all groups leaves no arm
    undescribed.
    """
    shared = _shared_protocol(payload)
    bundle.experimental_groups = shared.experimental_groups
    #: (kind, sentence) for every protocol decision a person should settle. Rides out on the
    #: summary rather than a second return value: `ingestion` holds the session this needs.
    queue: list[tuple[str, str]] = []

    entries = payload.get("experiments")
    if not isinstance(entries, list):
        logger.info("Protocol reply has no experiments list — only the shared protocol applies")
        entries = []

    dropped = 0
    for position, entry in enumerate(entries):
        try:
            record = ProtocolRecord.model_validate(entry)
        except ValidationError as exc:
            logger.info("Protocol entry %d does not fit the schema — dropped (%s)",
                        position, _schema_problem(exc))
            dropped += 1
            continue
        if not 0 <= record.experiment_index < len(bundle.experiments):
            logger.info("Protocol names experiment %d, which the gate did not find — dropped",
                        record.experiment_index)
            dropped += 1
            continue
        experiment = bundle.experiments[record.experiment_index]
        if record.treatment_description:
            experiment.treatment_description = record.treatment_description
        experiment.sample_weight_g = record.sample_weight_g
        experiment.storage_temperature_c = record.storage_temperature_c
        _apply_treatment(experiment, record, queue)
        _apply_application(experiment, record, queue)
        experiment.evidence.extend(record.evidence)

    inherited = 0
    if shared.protocol:
        for experiment in bundle.experiments:
            if experiment.treatment_description is None and experiment.measurements:
                experiment.treatment_description = shared.protocol
                experiment.evidence.extend(shared.evidence)
                inherited += 1
                # Both, not just the treatment: the shared sentence is where "dipped in
                # the coating dispersion" lives, and an arm that inherits it must inherit
                # what it says about application too.
                _apply_treatment(experiment, None, queue)
                _apply_application(experiment, None, queue)

    arms = [experiment for experiment in bundle.experiments if experiment.measurements]
    summary = {
        "arms_measured": len(arms),
        "arms_described": sum(1 for experiment in arms if experiment.treatment_description),
        "arms_classified": sum(1 for experiment in arms if experiment.treatment_type),
        "inherited_shared_protocol": inherited,
        "experimental_groups": shared.experimental_groups,
        "entries_dropped": dropped,
        # Deduplicated: a shared protocol classified once per arm is one question, not one
        # per arm. Order kept so the drain is deterministic.
        "review_terms": list(dict.fromkeys(
            (kind, text) for kind, text in queue if str(text or "").strip())),
    }
    logger.info("Protocols: %d/%d measured arms described, %d classified, %d inherited "
                "the shared protocol", summary["arms_described"], summary["arms_measured"],
                summary["arms_classified"], inherited)
    return bundle, summary
