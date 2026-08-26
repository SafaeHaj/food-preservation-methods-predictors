"""The queue that makes "unrecognised" a decision someone owes rather than a silent drop.

Four sinks feed it. What each test here pins down is not that a term reaches the queue --
that is one insert -- but the two boundaries the design turns on:

  * a term met again bumps one row rather than opening a second, and a `resolved` ruling
    that never reached `vocabulary.yaml` reopens instead of staying closed;
  * absence is not ambiguity. A protocol sentence matching nothing is the arm that had no
    treatment, which is most of the corpus; only a sentence matching two families at once
    is a question a person can answer.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.db.database import Base
from shared.db.models import Ingredient, VocabularyReviewQueue
from shared.schemas.science import (
    EvidenceSpan, ExperimentIngredientRecord, GoldBundle, ExperimentRecord,
    IngredientRecord, PaperDocument, SectionDocument, UNCLASSIFIED_CLASS,
    UNCLASSIFIED_TREATMENT, UNKNOWN_SOURCE, UNSPECIFIED_APPLICATION,
)

from app.services import review_queue, science_writer
from app.services.gold import protocols
from app.services.gold import validate as gold_validate
from app.services.silver.vocabulary import build_vocabulary


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _entries(db) -> list[VocabularyReviewQueue]:
    return db.query(VocabularyReviewQueue).order_by(VocabularyReviewQueue.id).all()


# ─── Dedup and reopening ──────────────────────────────────────────────────────

def test_the_same_term_bumps_one_row(db):
    """Forty papers naming one unknown substance is one question, asked forty times."""
    assert review_queue.enqueue(db, "ingredient", "Nisin A") is True
    assert review_queue.enqueue(db, "ingredient", "nisin  a") is False
    db.flush()

    entries = _entries(db)
    assert len(entries) == 1
    assert entries[0].occurrences == 2
    # The paper's own wording is kept, not the folded key a curator cannot read back.
    assert entries[0].raw_text == "Nisin A"


def test_kinds_do_not_collide(db):
    """One string can be an unknown substance and an unresolved indicator at once."""
    review_queue.enqueue(db, "ingredient", "lactate")
    review_queue.enqueue(db, "indicator", "lactate")
    db.flush()
    assert {entry.kind for entry in _entries(db)} == {"ingredient", "indicator"}


def test_a_resolved_term_reopens_when_it_turns_up_again(db):
    """`resolved` means "I added it". Meeting it again proves that did not take effect."""
    review_queue.enqueue(db, "ingredient", "carvacrol")
    db.flush()
    entry = _entries(db)[0]
    entry.status = "resolved"
    db.flush()

    review_queue.enqueue(db, "ingredient", "carvacrol")
    db.flush()
    assert _entries(db)[0].status == "pending"


def test_a_rejected_term_stays_rejected(db):
    """Rejection is a standing decision. Re-queueing it every paper is the loop it ends."""
    review_queue.enqueue(db, "ingredient", "sample code B")
    db.flush()
    entry = _entries(db)[0]
    entry.status = "rejected"
    db.flush()

    review_queue.enqueue(db, "ingredient", "sample code B")
    db.flush()
    entry = _entries(db)[0]
    assert entry.status == "rejected"
    assert entry.occurrences == 2   # still counted, just not reopened


def test_blank_terms_are_not_queued(db):
    assert review_queue.enqueue(db, "ingredient", "   ") is False
    assert review_queue.enqueue(db, "ingredient", None) is False
    db.flush()
    assert _entries(db) == []


# ─── Silver: an unknown substance lands rather than vanishing ─────────────────

def test_a_dosed_unknown_substance_keeps_its_name_and_sinks_its_class():
    """The dose is the evidence that it is a substance at all."""
    vocabulary = build_vocabulary()
    resolved = vocabulary.normalise_ingredient("zzz novel peptide", dosed=True)

    assert resolved == {"name": "zzz novel peptide",
                        "functional_class": UNCLASSIFIED_CLASS,
                        "source": UNKNOWN_SOURCE}
    assert "zzz novel peptide" in vocabulary.review()["unresolved"]["ingredient"]


def test_an_undosed_unknown_string_is_still_dropped():
    """With no amount beside it, the vocabulary is all that separates an additive from a
    footnote or a packaging condition."""
    vocabulary = build_vocabulary()
    assert vocabulary.normalise_ingredient("vacuum packed") is None


# ─── Gold: ambiguity is the trigger, not absence ──────────────────────────────

def _bundle(description: str, with_ingredient: bool = True, arms: int = 1) -> GoldBundle:
    records = []
    for index in range(arms):
        record = ExperimentRecord(matrix_name="Ground beef", arm_key=f"a{index}",
                                  treatment_description=description)
        if with_ingredient:
            record.ingredients.append(IngredientRecord(
                ingredient_name="Nisin", functional_class="protein",
                source_category="microbial"))
            record.experiment_ingredients.append(
                ExperimentIngredientRecord(ingredient_name="Nisin"))
        records.append(record)
    return GoldBundle(paper=PaperDocument(title="A paper"), experiments=records)


def _reply(bundle: GoldBundle) -> dict:
    """What the Gold call returns for these arms. Classification runs off the reply, so a
    bundle with no entry for an arm never reaches the classifier at all."""
    return {"experiments": [
        {"experiment_index": index,
         "treatment_description": record.treatment_description}
        for index, record in enumerate(bundle.experiments)
    ]}


def test_a_sentence_matching_nothing_is_not_queued():
    """The arm that had no treatment is the common case; queueing it would bury the real
    ambiguities under every control group in the literature."""
    bundle = _bundle("Samples were stored at 4 C for 9 days.")
    _, summary = protocols.apply(bundle, _reply(bundle))
    assert summary["review_terms"] == []


def test_an_ambiguous_sentence_is_queued():
    """Two keyword families on one sentence: the classifier will not rank them, so it is a
    question only a person can settle."""
    bundle = _bundle("Fillets were dipped in the coating and then vacuum-packed.")
    _, summary = protocols.apply(bundle, _reply(bundle))
    assert ("application", bundle.experiments[0].treatment_description) in \
        summary["review_terms"]


def test_an_arm_with_no_additives_asks_nothing_about_application():
    bundle = _bundle("Fillets were dipped in the coating and then vacuum-packed.",
                     with_ingredient=False)
    _, summary = protocols.apply(bundle, _reply(bundle))
    assert [kind for kind, _ in summary["review_terms"]] == []


def test_review_terms_are_deduplicated():
    """A shared protocol classified once per arm is one question, not one per arm."""
    bundle = _bundle("Fillets were dipped in the coating and then vacuum-packed.", arms=2)
    _, summary = protocols.apply(bundle, _reply(bundle))
    assert len(summary["review_terms"]) == 1


# ─── Validation covers all four sinks ─────────────────────────────────────────

def test_a_sunk_treatment_is_reported():
    bundle = _bundle("Samples were treated.")
    bundle.experiments[0].treatment_type = UNCLASSIFIED_TREATMENT
    rules = {item["rule"] for item in gold_validate.validate(bundle)}
    assert "treatment_needs_a_type" in rules


def test_an_undescribed_arm_is_not_reported_for_application():
    """`application_method`'s sink is also its column default, so flagging absence would
    fire on most links in the corpus and say nothing."""
    bundle = _bundle("Samples were stored at 4 C.")
    assert bundle.experiments[0].experiment_ingredients[0].application_method == \
        UNSPECIFIED_APPLICATION
    rules = {item["rule"] for item in gold_validate.validate(bundle)}
    assert "application_needs_a_method" not in rules


def test_an_ambiguous_application_is_reported():
    bundle = _bundle("Fillets were dipped in the coating and then vacuum-packed.")
    rules = {item["rule"] for item in gold_validate.validate(bundle)}
    assert "application_needs_a_method" in rules


# ─── A NUL byte must not cost the whole paper ─────────────────────────────────

def test_nul_bytes_are_stripped_from_extracted_prose():
    """PostgreSQL rejects `\\x00` in a text field, and a paper's rows are written in one
    transaction -- so one such byte in one section discarded every record for that paper.
    Seen on real corpus papers 7 and 10."""
    section = SectionDocument(section_title="Results\x00", content_markdown="a\x00b")
    assert (section.section_title, section.content_markdown) == ("Results", "ab")

    paper = PaperDocument(title="Effect of\x00 nisin", abstract="x\x00y")
    assert (paper.title, paper.abstract) == ("Effect of nisin", "xy")

    span = EvidenceSpan(field_name="treatment_description", docling_item_ref="#/texts/1",
                        source_type="prose", method="stated", exact_text="dipped\x00")
    assert span.exact_text == "dipped"


# ─── The write side heals what a corrected vocabulary fixes ───────────────────

def test_a_sunk_ingredient_is_healed_when_the_vocabulary_catches_up(db):
    """Keyed on name alone, a substance first met before its vocabulary entry existed would
    otherwise sit on `unclassified` forever."""
    db.add(Ingredient(ingredient_name="Carvacrol", functional_class=UNCLASSIFIED_CLASS,
                      source_category=UNKNOWN_SOURCE))
    db.flush()

    science_writer._get_or_create_ingredient(db, IngredientRecord(
        ingredient_name="Carvacrol", functional_class="phenol", source_category="plant"))
    db.flush()

    healed = db.query(Ingredient).one()
    assert (healed.functional_class, healed.source_category) == ("phenol", "plant")


def test_a_real_class_is_never_overwritten(db):
    """Fill-never-overwrite: only a sink is filled, so two papers disagreeing does not make
    the catalogue drift to whichever was ingested last."""
    db.add(Ingredient(ingredient_name="Carvacrol", functional_class="phenol",
                      source_category="plant"))
    db.flush()

    science_writer._get_or_create_ingredient(db, IngredientRecord(
        ingredient_name="Carvacrol", functional_class="organic acid",
        source_category="microbial"))
    db.flush()

    assert db.query(Ingredient).one().functional_class == "phenol"
