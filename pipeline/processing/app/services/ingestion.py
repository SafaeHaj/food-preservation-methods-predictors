"""Gated package in, scientific schema out — the ingestion job's whole body.

Five steps, and only two of them involve a model:

    review      ask which column is the axis on assets the gate could not key   (LLM)
    normalise   resolve every name and unit against the vocabulary
    gold        assemble validated records, ask for `treatment` and `weight_g`  (LLM)
    validate    cross-record rules the per-record models cannot express
    persist     the paper's bibliography, prose, arms, doses, measurements, evidence

The model is never asked for a number. Every value written here was read off a table or a
converted chart by the schema gate, resolved by the vocabulary, and validated before the
database saw it. That is the difference from the prompt-driven extractor this replaces, and
it is why a change of provider moves two prose fields and nothing else.

Runs inside the caller's transaction, so a paper's rows commit together.

Nothing here opens a PDF. The package extraction staged carries every observation the gate
found, so this service needs neither Docling nor PaddleOCR — which is the whole point of
the cut: extraction reads documents, processing reads meaning.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from shared.db.models import Paper
from shared.uow import JobProgressReporter

from app.services import (
    document_writer, evidence_writer, review_queue, science_writer, timings,
)
from app.services.gold import build as gold_build
from app.services.gold import validate as gold_validate
from app.services.gold.evidence import reference_text_index
from app.services.llm import get_llm_client
from app.services.silver import classify
from app.services.silver import normalise as silver_normalise
from app.services.silver import package_reader
from app.services.silver import review as silver_review
from app.services.silver.vocabulary import build_vocabulary, vocabulary_version

logger = logging.getLogger(__name__)

PROGRESS_LOAD = 10
PROGRESS_REVIEW = 20
PROGRESS_NORMALISE = 35
PROGRESS_GOLD = 50
PROGRESS_VALIDATE = 70
PROGRESS_DOCUMENT = 80
PROGRESS_PERSIST = 85


def run(db: Session, paper: Paper, job_id: int, progress: JobProgressReporter) -> dict:
    """Extract structured data for one paper. Returns the job result payload."""
    with timings.collect() as records:
        progress.update(progress=PROGRESS_LOAD, step="Loading the gated package")
        package = package_reader.load(db, paper)
        package.setdefault("source_name", paper.original_name)
        report = package["gate_report"]

        client = get_llm_client()
        progress.update(
            progress=PROGRESS_REVIEW,
            step=f"Reviewing {report.get('review', 0)} unresolved asset(s)",
        )
        silver_review.adjudicate(package, client)

        progress.update(progress=PROGRESS_NORMALISE, step="Resolving names, units and doses")
        vocabulary = build_vocabulary()
        with timings.stage_timer("normalise", package["paper_slug"]):
            reading = silver_normalise.normalise(package, vocabulary)

        progress.update(
            progress=PROGRESS_GOLD,
            step=f"Reading the protocol for {len(reading['measurements'])} measurements",
        )
        index = reference_text_index(package)
        bundle, llm_summary = gold_build.build(package, client, index, vocabulary)

        progress.update(progress=PROGRESS_VALIDATE, step="Checking the assembled records")
        violations = gold_validate.validate(bundle, index, vocabulary)
        if violations:
            logger.info("Paper %s: %d semantic violations", paper.id, len(violations))

        # Both stages' unnameable terms, parked for a curator. Silver's are the substances
        # and quantities no vocabulary entry matched, plus anything flagged as ambiguous
        # rather than simply missing (e.g. two row labels competing for one arm slot);
        # Gold's are the protocol sentences whose keywords matched two treatment families at
        # once. Neither stage writes here itself.
        queued = review_queue.drain(
            db,
            [(kind, text)
             for kind in ("ingredient", "indicator")
             for text in reading["vocabulary_review"]["unresolved"].get(kind, ())]
            + [(flag["kind"], flag["value"])
               for flag in reading["vocabulary_review"].get("flags", ())]
            + [tuple(term) for term in llm_summary.get("review_terms", ())],
            paper.id,
        )

        progress.update(progress=PROGRESS_DOCUMENT, step="Saving the document and its sections")
        sections = document_writer.write(db, paper, bundle)

        progress.update(
            progress=PROGRESS_PERSIST,
            step=f"Saving {len(bundle.experiments)} experiment(s)",
        )
        written = science_writer.write_bundle(
            db,
            project_id=paper.project_id,
            paper_id=paper.id,
            job_id=job_id,
            bundle=bundle,
            evidence_sink=evidence_writer.make_sink(
                db, paper.id, evidence_writer.build_reference_index(db, paper.id)
            ),
        )

    return {
        **written.as_dict(),
        "sections": sections,
        "gate_report": report,
        "experimental_groups": bundle.experimental_groups,
        "violations": violations,
        "vocabulary_review": reading["vocabulary_review"],
        "review_queued": queued,
        "vocabulary_version": vocabulary_version(),
        "unit_report": package.get("unit_report", {}),
        "classification_report": classify.report(
            [classify.classify_treatment(record.treatment_description)
             for record in bundle.experiments]),
        "fingerprint": gold_validate.fingerprint(bundle),
        "llm": llm_summary,
        "timings": timings.totals(records),
        "_step": (
            f"Done — {written.experiments} experiments, {written.measurements} measurements"
        ),
    }
