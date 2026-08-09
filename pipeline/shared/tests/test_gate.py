"""The structural contract, pinned.

`fits_schema` decides what the pipeline can read out of a paper, so every change to it
changes what the corpus yields. These fixtures are the shapes that matter: the three
orientations it accepts, and the near-misses it must keep rejecting — a dose ladder in the
header reads exactly like an ascending axis, and a composition table exactly like a series
with one point per row.

No I/O, no database, no model: the gate is pure by design. It lives in `shared` because
extraction runs it during the workspace job and processing re-runs it once a model has
named the axis of a table the gate could not key — so its contract is tested here, where
both consumers can see it.
"""

from __future__ import annotations

import pytest

from shared.science.gate import (
    canonical_key, fits_schema, parse_dosed_label, parse_number, split_axis_from_label,
    split_label_and_unit,
)

# ─── Accepted shapes ──────────────────────────────────────────────────────────

LONG = (
    ["Treatment", "Day", "TVC (log CFU/g)", "TBARS (mg MDA/kg)"],
    [["Control", 0, "4.1 ± 0.2", "0.21"], ["Control", 3, "5.6", "0.35"],
     ["Control", 6, "7.2", "0.60"], ["EO 0.5%", 0, "4.0", "0.20"],
     ["EO 0.5%", 3, "4.9", "0.28"], ["EO 0.5%", 6, "5.8", "0.41"]],
)

WIDE = (
    ["Sample", "Day 0", "Day 3", "Day 6", "Day 9"],
    [["Control", "4.1", "5.6", "7.2", "8.4"], ["Treated", "4.0", "4.9", "5.8", "6.6"]],
)

KEYED = (
    ["Group", "TVC"],
    [["Control, 0 days", "4.1"], ["Control, 3 days", "5.6"], ["Control, 6 days", "7.2"],
     ["EO, 0 days", "4.0"], ["EO, 3 days", "4.9"], ["EO, 6 days", "5.8"]],
)


@pytest.mark.parametrize(("shape", "orientation"),
                         [(LONG, "long"), (WIDE, "wide"), (KEYED, "keyed")])
def test_accepts_each_orientation(shape, orientation):
    fit = fits_schema(*shape)
    assert fit.fits, fit.reason
    assert fit.orientation == orientation
    assert fit.observations


def test_long_axis_that_restarts_beats_a_wide_reading():
    """A day column that resets per arm is the strongest evidence there is, and must win
    even where the headers could also be read as an axis."""
    fit = fits_schema(*LONG)
    assert fit.orientation == "long"
    assert fit.axis_runs == 2
    assert fit.axis_values == [0.0, 3.0, 6.0]


def test_observations_carry_their_labels_unresolved():
    """The gate never names anything: `normalise` decides which label is the indicator."""
    fit = fits_schema(*LONG)
    first = fit.observations[0]
    assert first.axis_value == 0.0
    assert first.column_label == "TVC (log CFU/g)"
    assert first.row_labels == {"Treatment": "Control"}


# ─── Rejections ───────────────────────────────────────────────────────────────

REJECTIONS = {
    "too few axis points": (
        ["Day", "TVC"], [[0, "4.1"], [3, "5.6"]],
    ),
    "dose ladder in the headers": (
        ["Indicator", "0.5%", "1.0%", "1.5%"],
        [["TVC", "4.1", "4.0", "3.9"], ["TBARS", "0.2", "0.18", "0.15"],
         ["pH", "5.8", "5.9", "6.0"]],
    ),
    "composition catalogue": (
        ["Compound", "Peak area %"],
        [["Terpinen-4-ol", "28.4"], ["gamma-Terpinene", "11.2"],
         ["alpha-Terpinene", "7.9"], ["Sabinene", "5.1"]],
    ),
    "prose with digits, not a numeric column": (
        ["Step", "Description"],
        [["1", "Samples were washed for 30 s"], ["2", "Samples were drained"],
         ["3", "Samples were packed in trays"], ["4", "Samples were stored at 4 C"]],
    ),
    "an axis but nothing measured beside it": (
        ["Day", "Replicate"], [[0, 1], [3, 1], [6, 1], [9, 1]],
    ),
    "empty": ([], []),
}


@pytest.mark.parametrize("name", sorted(REJECTIONS))
def test_rejects(name):
    fit = fits_schema(*REJECTIONS[name])
    assert not fit.fits, f"{name} was accepted as {fit.orientation}: {fit.reason}"
    assert fit.reason


def test_a_named_axis_promotes_a_keyed_table():
    """What `review` does with the model's answer: the hint names a column, and the gate
    re-reads the table itself. The hint can only unlock a fit, never supply a value."""
    headers = ["Sample", "TVC"]
    rows = [["Control day 0", "4.1"], ["Control day 3", "5.6"], ["Control day 6", "7.2"],
            ["Treated day 0", "4.0"], ["Treated day 3", "4.9"], ["Treated day 6", "5.8"]]
    assert fits_schema(headers, rows).orientation == "keyed"

    hinted = fits_schema(headers, rows, prefer_axis=canonical_key("Sample"))
    assert hinted.fits and hinted.orientation == "keyed"
    assert hinted.axis_values == [0.0, 3.0, 6.0]


# ─── Cell and label parsing ───────────────────────────────────────────────────

@pytest.mark.parametrize(("cell", "expected"), [
    ("7.2 ± 0.3", 7.2),          # mean ± sd: the mean is the value
    ("7.2+/-0.3", 7.2),
    ("<0.01", 0.01),             # a detection limit is still a number
    ("1,234", 1234.0),           # thousands separator
    ("6,5", 6.5),                # decimal comma
    ("4.1a", 4.1),               # significance letter
    ("3.2†", 3.2),               # footnote mark
    ("55%", 55.0),
    ("−1.5", -1.5),              # unicode minus
    ("4.10 (0.21)", 4.10),       # parenthesised sd
    ("n.d.", None),
    ("", None),
    (None, None),
    (True, None),                # a bool is not a measurement
])
def test_parse_number(cell, expected):
    assert parse_number(cell) == expected


@pytest.mark.parametrize(("label", "substance", "amount", "unit"), [
    ("0.5% Moringa Extract", "Moringa Extract", 0.5, "%"),
    ("TEO 1%", "TEO", 1.0, "%"),
    ("200 ppm BHT", "BHT", 200.0, "ppm"),
    ("Vacuum + 1% TEO", "Vacuum + TEO", 1.0, "%"),
])
def test_parse_dosed_label(label, substance, amount, unit):
    dose = parse_dosed_label(label)
    assert dose is not None
    assert (dose.substance, dose.amount, dose.unit) == (substance, amount, unit)


def test_a_plain_name_carries_no_dose():
    assert parse_dosed_label("Control") is None


@pytest.mark.parametrize(("label", "name", "unit"), [
    ("TVC (log CFU/g)", "TVC", "log CFU/g"),
    ("pH", "pH", None),
    ("TBARS (mean ± SD)", "TBARS", None),      # a stats tail is not a unit
    ("Concentration (mg/kg)", "Concentration", "mg/kg"),
])
def test_split_label_and_unit(label, name, unit):
    assert split_label_and_unit(label) == (name, unit)


@pytest.mark.parametrize(("label", "position", "residue"), [
    ("control, 6 days", 6.0, "control"),
    ("Day 12 - treated", 12.0, "treated"),
    ("control", None, "control"),
])
def test_split_axis_from_label(label, position, residue):
    assert split_axis_from_label(label) == (position, residue)


@pytest.mark.parametrize(("text", "key"), [
    ("Total Viable Count", "total_viable_count"),
    ("α-Terpinene", "alpha_terpinene"),
    ("log CFU/g", "log_cfu_g"),
    ("  TVC  ", "tvc"),
])
def test_canonical_key(text, key):
    assert canonical_key(text) == key
