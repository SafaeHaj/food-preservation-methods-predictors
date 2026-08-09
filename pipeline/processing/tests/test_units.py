"""Every dose on one scale, and the ones that cannot be.

The conversion table is the kind of code that looks obviously right and is worth pinning
anyway: a factor off by a thousand does not raise, it produces a corpus where every dose is
a thousand times too large, and nothing downstream can tell.
"""

from __future__ import annotations

import pytest

from app.services.silver.units import to_ppm

#: (amount, unit, expected ppm) over every row of the mass table.
MASS_CASES = [
    (1.0, "%", 10_000.0),
    (3.2, "% (w/w)", 32_000.0),
    (0.05, "g/100g", 500.0),
    (2.0, "w/w", 20_000.0),
    (1.0, "g/kg", 1_000.0),
    (1.0, "mg/g", 1_000.0),
    (500.0, "ppm", 500.0),
    (500.0, "mg/kg", 500.0),
    (500.0, "µg/g", 500.0),
    (1000.0, "ppb", 1.0),
    (1000.0, "ng/g", 1.0),
]

#: Volumetric units, true only where the matrix behaves as water.
DENSITY_CASES = [
    (1.0, "% (v/v)", 10_000.0),
    (1.0, "g/L", 1_000.0),
    (1.0, "mg/mL", 1_000.0),
    (5.0, "mg/L", 5.0),
    (5.0, "µg/ml", 5.0),
]


@pytest.mark.parametrize(("amount", "unit", "expected"), MASS_CASES)
def test_a_mass_dose_converts_exactly(amount, unit, expected) -> None:
    result = to_ppm(amount, unit)
    assert result.ppm == pytest.approx(expected)
    assert not result.approximate


@pytest.mark.parametrize(("amount", "unit", "expected"), DENSITY_CASES)
def test_a_volumetric_dose_converts_and_says_it_assumed_a_density(amount, unit, expected):
    result = to_ppm(amount, unit)
    assert result.ppm == pytest.approx(expected)
    assert result.approximate, f"{unit} rests on rho=1 and must be flagged as approximate"
    assert "density" in result.rationale


@pytest.mark.parametrize("unit", ["µg/g", "ug/g", "μg/g"])
def test_the_three_micro_signs_are_one_unit(unit) -> None:
    """`µ` (micro sign) and `μ` (Greek mu) are different codepoints that render alike, and
    a paper may carry either. Keying on the raw string would convert one and drop the other."""
    assert to_ppm(1.0, unit).ppm == 1.0


@pytest.mark.parametrize("unit", ["peak area %", "area %", "relative %"])
def test_a_relative_composition_is_not_a_dose(unit) -> None:
    """A GC-MS peak area says what an extract is made of, not how much was applied."""
    result = to_ppm(42.0, unit)
    assert result.ppm is None
    assert result.reason == "not_a_dose"


def test_an_unknown_unit_yields_no_ppm_and_a_reason() -> None:
    result = to_ppm(500.0, "IU/g")
    assert result.ppm is None
    assert result.reason == "no_factor"


def test_no_amount_is_distinct_from_no_factor() -> None:
    """A paper naming an additive without a dose is not the same as one whose unit we
    cannot convert. Both give a null column; only the second is fixed by adding a factor."""
    assert to_ppm(None, "%").reason == "no_amount"
    assert to_ppm(1.0, None).reason == "no_unit"


def test_the_rationale_carries_the_original_unit_and_the_result() -> None:
    """`ck_evidence_rationale_when_not_stated` forces a rationale on a derived span, so this
    string is where the original dose survives -- there is no column for it."""
    rationale = to_ppm(3.2, "% (w/w)").rationale
    assert "3.2" in rationale and "% (w/w)" in rationale and "32000" in rationale


def test_a_canonical_unit_is_only_consulted_when_the_raw_one_is_unknown() -> None:
    """The vocabulary folds `mg/L` into `ppm`, which is the density assumption. Trying the
    raw unit first is what keeps that flagged rather than silently exact."""
    result = to_ppm(5.0, "mg/L", "ppm")
    assert result.ppm == pytest.approx(5.0)
    assert result.approximate
