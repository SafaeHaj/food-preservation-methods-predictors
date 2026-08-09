"""Silver to Gold on one paper, and the contract that survives a change of provider.

The provider-independence test is the one that proves the architecture: the same package
run through two clients answering completely differently must produce identical matrices,
arms, doses, indicators, days and values. Only `treatment`, `weight_g` and
`experimental_groups` may move, because those are the only things the model is asked for.

If anything else differs, the "backend assembles, model only reads prose" contract has a
leak, and this is where it surfaces.
"""

from __future__ import annotations

import pytest

from shared.science.gate import fits_schema, observation_payload

from app.services.gold import build as gold_build
from app.services.gold import validate as gold_validate
from app.services.gold.evidence import reference_text_index
from app.services.llm import FakeLLMClient
from app.services.silver import normalise as silver_normalise
from app.services.silver.vocabulary import build_vocabulary

HEADERS = ["Storage day", "Control", "TEO 0.5%", "TEO 1%"]
ROWS = [[0, "4.1", "4.0", "4.0"], [3, "5.6", "4.9", "4.7"],
        [6, "7.2", "5.8", "5.4"], [9, "8.4", "6.6", "6.0"]]

METHODS = ("Ground beef samples of 100 g were packed in polystyrene trays and stored "
           "at 4 C for 9 days.")


@pytest.fixture
def package() -> dict:
    fit = fits_schema(HEADERS, ROWS)
    return {
        "paper_slug": "11",
        "source_name": "11.pdf",
        "methods_refs": ["#/texts/3"],
        "sections": [{"section_title": "Materials and Methods",
                      "docling_item_ref": "#/texts/3", "content_markdown": METHODS}],
        "tables": [{
            "docling_item_ref": "#/tables/0", "page_number": 4, "is_figure": False,
            "caption": "Table 1. Total viable count (log CFU/g) of ground beef during storage",
            "headers": HEADERS, "gate": fit.summary(),
            "observations": observation_payload(fit),
            "context_markdown": "", "preview_markdown": "",
        }],
        "figures": [], "references": [], "review": [], "rejected": [],
        "gate_report": {"observations": len(fit.observations), "review": 0},
    }


def _client(protocol: str, weight: float | None, groups: int | None) -> FakeLLMClient:
    return FakeLLMClient({"default": {
        "protocol": protocol,
        "experimental_groups": groups,
        "evidence": [{"field_name": "treatment_description", "docling_item_ref": "#/texts/3",
                      "source_type": "prose", "method": "stated",
                      "exact_text": "stored at 4 C for 9 days"}],
        "experiments": [{"experiment_index": index, "treatment_description": None,
                         "sample_weight_g": weight,
                         "evidence": [{"field_name": "sample_weight_g",
                                       "docling_item_ref": "#/texts/3",
                                       "source_type": "prose", "method": "stated",
                                       "exact_text": "samples of 100 g"}]}
                        for index in range(3)],
    }})


def _build(package: dict, client) -> tuple:
    vocabulary = build_vocabulary()
    silver_normalise.normalise(package, vocabulary)
    index = reference_text_index(package)
    bundle, _ = gold_build.build(package, client, index)
    return bundle, index, vocabulary


# ─── Silver resolves everything before Gold assembles ─────────────────────────

def test_the_vocabulary_resolves_matrix_arms_and_indicators(package):
    reading = silver_normalise.normalise(package, build_vocabulary())

    assert reading["matrix"]["name"] == "Ground beef"
    # The dose ladder becomes three arms, and the dose lands on the ingredient rather than
    # in its name.
    doses = sorted((item["name"], item["amount"], item["unit"])
                   for arm in reading["lexicon"].values() for item in arm.ingredients)
    assert doses == [("Thyme essential oil", 0.5, "%"), ("Thyme essential oil", 1.0, "%")]

    first = reading["measurements"][0]
    assert (first.indicator, first.indicator_type, first.unit) == (
        "Total viable count", "microbial", "log CFU/g")
    assert first.threshold == 7.0


def test_every_reading_becomes_a_measurement(package):
    bundle, _, _ = _build(package, _client(METHODS, 100.0, 3))
    assert len(bundle.experiments) == 3
    assert sum(len(record.measurements) for record in bundle.experiments) == 12
    assert {record.sample_weight_g for record in bundle.experiments} == {100.0}


def test_an_assembled_bundle_is_internally_consistent(package):
    bundle, index, vocabulary = _build(package, _client(METHODS, 100.0, 3))
    assert gold_validate.validate(bundle, index, vocabulary) == []


def test_a_mismatched_group_count_is_reported(package):
    """The gate finds arms in the tables, the methods say how many groups there were, and
    neither side sees the difference alone."""
    bundle, index, vocabulary = _build(package, _client(METHODS, 100.0, 5))
    rules = {item["rule"] for item in gold_validate.validate(bundle, index, vocabulary)}
    assert "experiment_count_must_match_the_study" in rules


def test_a_placeholder_treatment_is_reported(package):
    bundle, index, vocabulary = _build(package, _client("not specified", 100.0, 3))
    rules = {item["rule"] for item in gold_validate.validate(bundle, index, vocabulary)}
    assert "treatment_must_not_be_a_placeholder" in rules


# ─── The contract ─────────────────────────────────────────────────────────────

def _deterministic_half(fingerprint: dict) -> list:
    """Everything the pipeline decided for itself: arms, doses, days and values."""
    return [{key: record[key] for key in ("matrix_name", "ingredients", "measurements")}
            for record in fingerprint["experiments"]]


def test_the_provider_moves_only_the_two_prose_fields(package):
    """Two clients, answering completely differently, over the same package."""
    first, _, _ = _build(dict(package), _client(METHODS, 100.0, 3))
    second, _, _ = _build(dict(package), _client("Stored under vacuum at 2 C.", 250.0, 4))

    one, two = gold_validate.fingerprint(first), gold_validate.fingerprint(second)

    assert _deterministic_half(one) == _deterministic_half(two)
    assert one["experimental_groups"] != two["experimental_groups"]
    assert ({record["treatment_description"] for record in one["experiments"]}
            != {record["treatment_description"] for record in two["experiments"]})
    assert ({record["sample_weight_g"] for record in one["experiments"]}
            != {record["sample_weight_g"] for record in two["experiments"]})


def test_the_pipeline_still_produces_data_with_no_model(package):
    """A client that answers nothing costs the two prose fields and nothing else. This is
    what makes a deployment with no provider configured degrade rather than fail."""
    bundle, _, _ = _build(package, FakeLLMClient({"default": {}}))

    assert len(bundle.experiments) == 3
    assert sum(len(record.measurements) for record in bundle.experiments) == 12
    assert all(record.treatment_description is None for record in bundle.experiments)
    assert all(record.sample_weight_g is None for record in bundle.experiments)
