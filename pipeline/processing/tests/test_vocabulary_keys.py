"""The YAML's pattern keys must be values the schema actually accepts.

`config/vocabulary.yaml` is corpus data and is meant to be edited without a migration. Its
two protocol sections are the exception that needs guarding: the keys are not free text,
they are members of `TREATMENT_TYPES` and `APPLICATION_METHODS`, which back CHECK
constraints and pydantic `Literal`s.

A misspelled key -- "Heat Treatment", "Vacuum packed" -- is invisible at runtime. The
classifier simply never returns that value, every arm falls to the sink, and the only
symptom is a corpus where nothing was ever heat-treated. This test turns that into a
failure on the commit that introduces it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from shared.schemas.science import (
    APPLICATION_METHODS, TREATMENT_TYPES, UNCLASSIFIED_TREATMENT, UNSPECIFIED_APPLICATION,
)

VOCABULARY_PATH = Path(__file__).resolve().parents[1] / "config" / "vocabulary.yaml"

SECTIONS = {
    "treatment_patterns": (TREATMENT_TYPES, UNCLASSIFIED_TREATMENT),
    "application_patterns": (APPLICATION_METHODS, UNSPECIFIED_APPLICATION),
}


def _vocabulary() -> dict:
    return yaml.safe_load(VOCABULARY_PATH.read_text(encoding="utf-8"))


def _keys(section: str) -> list[str]:
    return list(_vocabulary().get(section) or {})


@pytest.mark.parametrize("section", sorted(SECTIONS))
def test_vocabulary_keys_are_declared(section: str) -> None:
    declared, _ = SECTIONS[section]
    unknown = [key for key in _keys(section) if key not in declared]
    assert not unknown, (
        f"{section} in vocabulary.yaml has keys that are not declared values: {unknown}. "
        f"Keys must be members of {list(declared)} -- an undeclared one never matches and "
        "the failure is silent."
    )


@pytest.mark.parametrize("section", sorted(SECTIONS))
def test_the_sink_carries_no_patterns(section: str) -> None:
    """The catch-all is what a value falls to, never what it matches into."""
    _, sink = SECTIONS[section]
    assert sink not in _keys(section), (
        f"{sink!r} is the sink for {section}: it is assigned when nothing matched, so "
        "giving it patterns of its own makes it compete with the real values."
    )


@pytest.mark.parametrize("section", sorted(SECTIONS))
def test_patterns_are_lowercase_and_non_empty(section: str) -> None:
    """Matching lowercases the text, so an uppercase pattern can never fire."""
    offenders = {
        key: [pattern for pattern in patterns
              if not pattern or pattern != pattern.lower().strip()]
        for key, patterns in (_vocabulary().get(section) or {}).items()
    }
    offenders = {key: bad for key, bad in offenders.items() if bad}
    assert not offenders, f"{section} has patterns that cannot match: {offenders}"
