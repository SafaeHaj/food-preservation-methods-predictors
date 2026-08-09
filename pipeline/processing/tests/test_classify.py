"""Keyword classification, and the two cases that must defer to the model.

The valuable assertions here are the negative ones. A classifier that answers everything is
easy to write and produces a corpus where every arm was heat-treated; the point of this one
is that it declines on ambiguity rather than picking the longer match.
"""

from __future__ import annotations

import pytest

from shared.schemas.science import (
    APPLICATION_METHODS, TREATMENT_TYPES, UNCLASSIFIED_TREATMENT, UNSPECIFIED_APPLICATION,
)

from app.services.silver.classify import (
    application_or_sink, classify_application, classify_treatment, thermal_conditions,
    treatment_or_sink,
)

TREATMENT_CASES = [
    ("Samples were treated at 600 MPa for 5 min", "High-pressure processing"),
    ("Fillets were gamma-irradiated at 3 kGy", "Irradiation"),
    ("Exposed to UV-C light for 60 s", "UV treatment"),
    ("Sonicated in an ultrasonic bath", "Ultrasound"),
    ("Treated with cold plasma at atmospheric pressure", "Cold plasma"),
    ("Washed in ozonated water", "Ozone treatment"),
    ("Dipped in slightly acidic electrolyzed water", "Electrolyzed water treatment"),
    ("Carcasses were rinsed with water", "Water washing"),
    ("The surface was trimmed before packing", "Surface trimming"),
    ("Blanched at 85 C for 2 min", "Heat treatment"),
    ("Subjected to vacuum tumbling for 20 min", "Vacuum treatment"),
]


@pytest.mark.parametrize(("text", "expected"), TREATMENT_CASES)
def test_each_treatment_type_is_reachable_from_prose(text, expected) -> None:
    """One fixture per value. A type no sentence can reach is a type that never appears."""
    verdict = classify_treatment(text)
    assert verdict.value == expected
    assert verdict.confident


def test_high_pressure_carries_its_duration_but_invents_no_temperature() -> None:
    verdict = classify_treatment("Samples were treated at 600 MPa for 5 min")
    assert verdict.duration_min == 5.0
    assert verdict.temperature_c is None, "600 MPa is a pressure, not a temperature"


def test_two_matches_are_not_resolved_by_ranking() -> None:
    """"Blanched, then high-pressure treated" describes two things. Choosing one would be
    a guess; the Gold call is asked instead."""
    verdict = classify_treatment("Blanched at 85 C, then high-pressure treated at 500 MPa")
    assert verdict.value is None
    assert not verdict.confident
    assert len(verdict.matched) == 2


def test_no_match_is_not_the_sink() -> None:
    """An unmatched sentence defers to the model. Falling straight to the sink here would
    file every unusual protocol as "Other physical treatment" without ever asking."""
    verdict = classify_treatment("Samples were stored in the dark and sampled weekly")
    assert verdict.value is None
    assert verdict.matched == ()


def test_empty_prose_is_not_a_classification() -> None:
    assert classify_treatment(None).value is None
    assert classify_application("").value is None


APPLICATION_CASES = [
    ("The extract was added to the mince before forming", "Mixed"),
    ("Fillets were dipped for 120 s", "Dipped"),
    ("The solution was sprayed onto the surface", "Sprayed"),
    ("Samples were immersed for 10 min", "Immersed"),
    ("Brine injection was used", "Injected"),
    ("Packed under vacuum packaging", "Vacuum-packed"),
]


@pytest.mark.parametrize(("text", "expected"), APPLICATION_CASES)
def test_application_methods_are_read_from_prose(text, expected) -> None:
    verdict = classify_application(text)
    assert verdict.value == expected
    assert verdict.confident


def test_a_coating_dip_is_genuinely_ambiguous() -> None:
    """"dipped in the coating dispersion" is both, and the corpus is full of it. The
    classifier must not silently pick one."""
    verdict = classify_application("dipped in the coating dispersion for 120 s")
    assert verdict.value is None
    assert set(verdict.matched) == {"Coated", "Dipped"}


THERMAL_CASES = [
    ("at 85 C for 2 min", 85.0, 2.0),
    ("at 121 °C for 15 minutes", 121.0, 15.0),
    ("heated to 72 deg C for 30 s", 72.0, 0.5),
    ("held at 4 C throughout storage", 4.0, None),
    ("600 MPa for 5 min", None, 5.0),
]


@pytest.mark.parametrize(("text", "temperature", "duration"), THERMAL_CASES)
def test_thermal_conditions_are_read_without_the_degree_symbol(text, temperature, duration):
    """PDF extraction drops `°` often enough that requiring it would lose most stated
    temperatures."""
    assert thermal_conditions(text) == (temperature, duration)


@pytest.mark.parametrize("text", ["0.5 g Cinnamon was added", "treated with 2% Chitosan"])
def test_a_capital_c_in_a_substance_name_is_not_a_temperature(text) -> None:
    """The price of making `°` optional, and the reason `C` must stand as its own word."""
    assert thermal_conditions(text)[0] is None


def test_a_value_outside_the_closed_set_collapses_to_the_sink() -> None:
    """The model cannot widen either vocabulary: the reply is re-checked in Python."""
    assert treatment_or_sink("Sous-vide pasteurisation") == UNCLASSIFIED_TREATMENT
    assert treatment_or_sink(None) == UNCLASSIFIED_TREATMENT
    assert application_or_sink("Brushed on") == UNSPECIFIED_APPLICATION
    assert treatment_or_sink("Irradiation") == "Irradiation"
    assert application_or_sink("Dipped") == "Dipped"


def test_the_sinks_are_members_of_their_own_vocabularies() -> None:
    """Otherwise narrowing to the sink writes a value the CHECK constraint rejects."""
    assert UNCLASSIFIED_TREATMENT in TREATMENT_TYPES
    assert UNSPECIFIED_APPLICATION in APPLICATION_METHODS
