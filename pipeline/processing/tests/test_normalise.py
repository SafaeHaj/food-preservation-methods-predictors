"""Direct coverage of `_assign_roles` and `interpret_asset` — the "hard part" of Silver.

Until now this logic was only reached indirectly, through `test_pipeline.py`'s one fixture
package. These tests hand-build the `observation`/`lexicon` shapes `_assign_roles` actually
consumes, so each of its resolution rules is pinned on its own rather than through whatever
shape one fixture table happens to have.
"""

from __future__ import annotations

from shared.science.gate import canonical_key

from app.services.silver.normalise import (
    Treatment, _assign_roles, interpret_asset, split_indicator_and_treatment,
)
from app.services.silver.vocabulary import build_vocabulary


def _lexicon(*labels: str) -> dict:
    """A lexicon keyed as `build_treatment_lexicon` keys it: by `canonical_key(label)`,
    not by the label itself."""
    return {canonical_key(label): Treatment(key=canonical_key(label), label=label, condition=None)
            for label in labels}


# ─── split_indicator_and_treatment (rule 1) ────────────────────────────────────

def test_a_header_packed_column_splits_into_indicator_and_arm():
    lexicon = _lexicon("control1")
    head, tail = split_indicator_and_treatment("PBC (log CFU/g) - Control1", lexicon)
    assert head == "PBC (log CFU/g)"
    assert tail == "Control1"


def test_a_header_with_no_known_tail_does_not_split():
    lexicon = _lexicon("control1")
    head, tail = split_indicator_and_treatment("PBC (log CFU/g) - Unknown group", lexicon)
    assert tail is None
    assert head == "PBC (log CFU/g) - Unknown group"


# ─── _assign_roles: column-header rules (1-3) ──────────────────────────────────

def test_column_header_packs_indicator_and_arm():
    lexicon = _lexicon("control1")
    observation = {"column_label": "PBC (log CFU/g) - Control1", "row_labels": {}}
    indicator, arm = _assign_roles(observation, lexicon, [], set())
    assert indicator == "PBC (log CFU/g)"
    assert arm == "Control1"


def test_whole_header_is_a_known_arm():
    lexicon = _lexicon("1% thyme oil")
    observation = {"column_label": "1% Thyme Oil", "row_labels": {"indicator": "pH"}}
    indicator, arm = _assign_roles(observation, lexicon, ["indicator"], set())
    assert arm == "1% Thyme Oil"
    assert indicator == "pH"


def test_whole_header_is_the_indicator():
    lexicon = _lexicon("1% thyme oil")
    observation = {"column_label": "pH", "row_labels": {}}
    indicator, arm = _assign_roles(observation, lexicon, [], set())
    assert indicator == "pH"
    assert arm is None


# ─── _assign_roles: row-label rules ────────────────────────────────────────────

def test_a_single_row_label_matching_the_lexicon_is_the_arm():
    lexicon = _lexicon("control1")
    observation = {"column_label": None, "row_labels": {"group": "Control1"}}
    indicator, arm = _assign_roles(observation, lexicon, [], set())
    assert arm == "Control1"
    assert indicator is None


def test_a_single_row_label_named_by_an_indicator_column_is_the_indicator():
    lexicon = _lexicon("control1")
    observation = {"column_label": None, "row_labels": {"indicator": "TVC"}}
    indicator, arm = _assign_roles(observation, lexicon, ["indicator"], set())
    assert indicator == "TVC"
    assert arm is None


def test_a_single_unrecognised_row_label_is_taken_as_the_arm():
    lexicon = _lexicon("control1")
    observation = {"column_label": None, "row_labels": {"group": "Novel treatment X"}}
    indicator, arm = _assign_roles(observation, lexicon, [], set())
    assert arm == "Novel treatment X"


def test_two_competing_unrecognised_row_labels_are_flagged_not_guessed():
    """Neither label is a known arm or a declared indicator column: the first is still
    read as the arm (unchanged single-label behaviour), but the second is no longer
    silently discarded -- it is flagged for a curator instead of picked arbitrarily."""
    vocabulary = build_vocabulary()
    lexicon = _lexicon("control1")
    observation = {
        "column_label": None,
        "row_labels": {"group": "Novel treatment X", "batch": "Batch B"},
    }
    indicator, arm = _assign_roles(observation, lexicon, [], set(), vocabulary)

    assert arm == "Novel treatment X"
    flags = vocabulary.review()["flags"]
    assert any(flag["kind"] == "treatment" and "Batch B" in flag["value"] for flag in flags)


def test_a_single_unrecognised_row_label_is_not_flagged():
    """One unclaimed label is ordinary — only a second competitor is ambiguity."""
    vocabulary = build_vocabulary()
    lexicon = _lexicon("control1")
    observation = {"column_label": None, "row_labels": {"group": "Novel treatment X"}}
    _assign_roles(observation, lexicon, [], set(), vocabulary)
    assert vocabulary.review()["flags"] == []


# ─── interpret_asset: caption fallback (rule 4) ────────────────────────────────

def _asset(observations, caption=None, is_figure=False) -> dict:
    return {
        "docling_item_ref": "#/tables/0", "page_number": 1, "is_figure": is_figure,
        "caption": caption, "gate": {"label_columns": ["group"]},
        "context_markdown": "", "observations": observations,
    }


def test_caption_names_the_indicator_when_no_label_does():
    vocabulary = build_vocabulary()
    lexicon = _lexicon("control1")
    observation = {"axis_value": 3, "value": 4.2, "column_label": None,
                   "row_labels": {"group": "Control1"}}
    asset = _asset([observation],
                   caption="Figure 1. pH of ground beef during storage")
    measurements, note = interpret_asset(asset, lexicon, vocabulary, caption_name="pH")
    assert len(measurements) == 1
    assert measurements[0].indicator == "pH"
    assert measurements[0].arm_key == "control1"
