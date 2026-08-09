"""Gold's three invariants: computed confidence, a bounded prompt, and a defensive merge.

Every test here runs against `FakeLLMClient`, so the suite needs no model, no API key and
no network — which is the point of the provider seam existing at all.
"""

from __future__ import annotations

import pytest

from shared.schemas.science import (
    EvidenceSpan, ExperimentRecord, GoldBundle, IndicatorRecord, MeasurementRecord,
    PaperDocument,
)

from app.services.gold import prompt as gold_prompt
from app.services.gold.evidence import score_evidence
from app.services.gold.protocols import apply as apply_protocols

QUOTE = "samples of 100 g were stored at 4 c for 9 days"
INDEX = {"#/texts/3": f"materials and methods {QUOTE}"}


def _span(**overrides) -> EvidenceSpan:
    return EvidenceSpan(**{
        "field_name": "sample_weight_g", "docling_item_ref": "#/texts/3", "source_type": "prose",
        "method": "stated", "exact_text": QUOTE, **overrides,
    })


# ─── Confidence is an evaluation, not a claim ─────────────────────────────────

def test_a_quote_that_checks_out_scores_top():
    assert score_evidence(_span(), INDEX) == 1.0


def test_a_quote_that_is_not_there_scores_half():
    assert score_evidence(_span(exact_text="stored at 25 C for a year"), INDEX) == 0.5


def test_an_unresolvable_ref_scores_zero():
    """A citation the model was never shown is worth nothing, however confident it reads."""
    assert score_evidence(_span(docling_item_ref="#/texts/99"), INDEX) == 0.0


@pytest.mark.parametrize(("method", "expected"), [("derived", 0.7), ("inferred", 0.3)])
def test_derived_and_inferred_sit_below_stated(method, expected):
    span = _span(method=method, rationale="batch mass divided by sample count")
    assert score_evidence(span, INDEX) == expected


def test_a_value_read_off_a_chart_is_penalised():
    """A figure reading is an estimate however confidently it is stated."""
    span = _span(source_type="figure", exact_text=None, field_name="indicator_value")
    assert score_evidence(span, INDEX) == pytest.approx(0.5 * 0.6)


def test_a_non_stated_span_must_carry_a_rationale():
    with pytest.raises(ValueError):
        _span(method="inferred", rationale=None)


# ─── The prompt fits, at every rung ───────────────────────────────────────────

def _package(section_chars: int = 40000) -> dict:
    return {
        "paper_slug": "11",
        "methods_refs": ["#/texts/3"],
        "sections": [
            {"section_title": "Materials and Methods", "docling_item_ref": "#/texts/3",
             "content_markdown": "Samples were prepared. " * (section_chars // 22)},
            {"section_title": "Results", "docling_item_ref": "#/texts/9",
             "content_markdown": "Counts rose over storage. " * 400},
        ],
        "tables": [{"docling_item_ref": "#/tables/0", "caption": "Table 1",
                    "gate": {"axis_label": "Day", "axis_points": [0, 3, 6]},
                    "context_markdown": "surrounding prose " * 200, "observations": []}],
        "figures": [], "references": [],
    }


def _bundle() -> GoldBundle:
    record = ExperimentRecord(
        matrix_name="Ground beef",
        indicators=[IndicatorRecord(indicator_name="Total viable count",
                                    indicator_type="microbial", indicator_unit="log CFU/g")],
        measurements=[MeasurementRecord(day=day, indicator_name="Total viable count",
                                        indicator_type="microbial",
                                        indicator_unit="log CFU/g", indicator_value=4.0 + day)
                      for day in (0, 3, 6)],
    )
    return GoldBundle(paper=PaperDocument(title="A paper"), experiments=[record])


@pytest.mark.parametrize("budget", [24000, 8000, 4000, 2000])
def test_the_prompt_is_fitted_to_every_budget(budget):
    payload = gold_prompt.build_payload(_package(), _bundle())
    text = gold_prompt.fit_to_budget(payload, budget)
    assert len(text) <= budget


def test_the_methods_survive_the_ladder_longest():
    """Asset context and results prose are background; the methods are the question.

    Asserted as an ordering rather than at one budget: what matters is that the results
    section is gone while the methods are still there, at every budget where anything has
    been dropped at all.
    """
    for budget in (6000, 4000, 3000, 2000):
        payload = gold_prompt.build_payload(_package(section_chars=8000), _bundle())
        text = gold_prompt.fit_to_budget(payload, budget)
        assert "Materials and Methods" in text, budget
        assert "Counts rose over storage" not in text, budget


def test_the_methods_are_never_shredded_below_their_floor():
    """Past the floor the payload is truncated whole rather than the methods being cut to
    a fragment that no longer reads as a procedure."""
    payload = gold_prompt.build_payload(_package(section_chars=40000), _bundle())
    gold_prompt.fit_to_budget(payload, 3000)
    methods = [section for section in payload["sections"] if section["is_methods"]]
    assert all(len(section["content_markdown"]) >= gold_prompt.MIN_METHODS_SECTION_CHARS
               for section in methods)


def test_the_arms_are_always_shown():
    """A reply is joined back by `experiment_index`, so the arms cannot be trimmed away."""
    payload = gold_prompt.build_payload(_package(), _bundle())
    gold_prompt.fit_to_budget(payload, 2000)
    assert payload["experiments"][0]["experiment_index"] == 0


# ─── A malformed reply costs only itself ──────────────────────────────────────

def _three_arm_bundle() -> GoldBundle:
    return GoldBundle(
        paper=PaperDocument(title="A paper"),
        experiments=[
            ExperimentRecord(
                matrix_name="Ground beef",
                measurements=[MeasurementRecord(
                    day=0, indicator_name="Total viable count", indicator_type="microbial",
                    indicator_unit="log CFU/g", indicator_value=4.0)],
            ) for _ in range(3)
        ],
    )


def test_one_bad_entry_does_not_discard_the_others():
    bundle, summary = apply_protocols(_three_arm_bundle(), {
        "experiments": [
            {"experiment_index": 0, "treatment_description": "Stored at 4 C", "sample_weight_g": 100.0},
            {"experiment_index": 1, "sample_weight_g": -5.0},          # violates gt=0
            {"experiment_index": 2, "treatment_description": "Stored at 4 C"},
        ],
    })
    assert bundle.experiments[0].treatment_description == "Stored at 4 C"
    assert bundle.experiments[2].treatment_description == "Stored at 4 C"
    assert summary["entries_dropped"] == 1


def test_an_invented_arm_is_dropped():
    bundle, summary = apply_protocols(_three_arm_bundle(), {
        "experiments": [{"experiment_index": 7, "treatment_description": "Stored at 4 C"}],
    })
    assert all(record.treatment_description is None for record in bundle.experiments)
    assert summary["entries_dropped"] == 1


def test_a_shared_protocol_is_inherited_by_every_undescribed_arm():
    bundle, summary = apply_protocols(_three_arm_bundle(), {
        "protocol": "Packed in trays and stored at 4 C for 9 days.",
        "experimental_groups": 3,
        "experiments": [{"experiment_index": 0, "treatment_description": "Vacuum packed"}],
    })
    assert bundle.experiments[0].treatment_description == "Vacuum packed"
    assert bundle.experiments[1].treatment_description == "Packed in trays and stored at 4 C for 9 days."
    assert summary["inherited_shared_protocol"] == 2
    assert bundle.experimental_groups == 3


def test_a_reply_with_no_experiments_still_applies_the_shared_protocol():
    bundle, _ = apply_protocols(_three_arm_bundle(), {"protocol": "Stored at 4 C"})
    assert all(record.treatment_description == "Stored at 4 C" for record in bundle.experiments)


def test_a_malformed_shared_block_costs_only_itself():
    bundle, summary = apply_protocols(_three_arm_bundle(), {
        "experimental_groups": -1,                              # violates gt=0
        "experiments": [{"experiment_index": 0, "treatment_description": "Stored at 4 C"}],
    })
    assert bundle.experiments[0].treatment_description == "Stored at 4 C"
    assert bundle.experimental_groups is None
