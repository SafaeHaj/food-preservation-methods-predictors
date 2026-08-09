"""Reading a protocol sentence into a closed value, from keywords where that is enough.

Most treatments announce themselves. "Samples were treated at 600 MPa for 5 min" contains
`mpa`; "gamma-irradiated at 3 kGy" contains both `irradiat` and `kgy`. A keyword table
answers those for free, and the model is left with the residue -- the sentences that matched
nothing, and the ones that matched two things and so are genuinely ambiguous.

That split is the point. Sending every arm to a model would cost a call per paper to
rediscover what a substring test already knows, and would make the no-model path useless.
Sending none of them would file every unusual protocol under the sink.

Ambiguity is not resolved by ranking. Two matches means the sentence really does describe
two things ("blanched, then high-pressure treated") or that one keyword is a false friend,
and picking the longer match would be a guess dressed as a rule.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import NamedTuple, Optional

import yaml

from shared.config import get_processing_settings
from shared.schemas.science import (
    APPLICATION_METHODS, TREATMENT_TYPES, UNCLASSIFIED_TREATMENT, UNSPECIFIED_APPLICATION,
)
from shared.science.gate import canonical_key

logger = logging.getLogger(__name__)

#: "600 MPa for 5 min", "at 121 °C for 15 minutes" -- the two numbers a physical treatment
#: is qualified by. A number must be followed by a Celsius marker to count as a temperature:
#: a bare "60" beside "min" is a duration, and reading it as a temperature would invent a
#: thermal step.
#:
#: The degree symbol is optional because it frequently is not there. PDF text extraction
#: drops it often enough that requiring it would silently lose most stated temperatures --
#: "chilled at 4 C" is what a converted methods section actually looks like. A bare `C`
#: still has to stand as its own word, so "0.5 g Cinnamon" cannot match.
_TEMPERATURE = re.compile(
    r"(-?\d+(?:[.,]\d+)?)\s*(?:°|º|\bdeg(?:rees)?\.?\s*)?\s*C\b",
)
_DURATION = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(h|hr|hrs|hour|hours|min|mins|minute|minutes|s|sec|secs|seconds)\b",
    re.IGNORECASE,
)
_TO_MINUTES = {"h": 60.0, "hr": 60.0, "hrs": 60.0, "hour": 60.0, "hours": 60.0,
               "min": 1.0, "mins": 1.0, "minute": 1.0, "minutes": 1.0,
               "s": 1 / 60, "sec": 1 / 60, "secs": 1 / 60, "seconds": 1 / 60}


class Classification(NamedTuple):
    """What the keywords could tell. `confident` is false when nothing matched or more than
    one did -- both are cases the model is asked about, for opposite reasons."""

    value: Optional[str]
    confident: bool
    matched: tuple
    temperature_c: Optional[float] = None
    duration_min: Optional[float] = None


def _number(text: str) -> Optional[float]:
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


@lru_cache(maxsize=1)
def _patterns() -> dict:
    """The two pattern sections, keyed by section name.

    Read straight from the YAML rather than through `VocabularySource`, which indexes terms
    -- substances and indicators -- and has no room for a keyword table. Keys are validated
    against the declared tuples here as well as in the test suite: a typo that survives to
    runtime would make one treatment type permanently unreachable, in silence.
    """
    path = get_processing_settings().vocabulary_file
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sections = {}
    for section, declared in (("treatment_patterns", TREATMENT_TYPES),
                              ("application_patterns", APPLICATION_METHODS)):
        table = payload.get(section) or {}
        unknown = [key for key in table if key not in declared]
        if unknown:
            raise ValueError(
                f"{section} in {path} has keys that are not declared values: {unknown}. "
                f"A key outside {list(declared)} can never be returned.")
        sections[section] = {key: [canonical_key(pattern) for pattern in patterns]
                             for key, patterns in table.items()}
    return sections


def _matches(text: str, table: dict) -> tuple:
    key = canonical_key(text)
    return tuple(sorted(value for value, patterns in table.items()
                        if any(pattern in key for pattern in patterns)))


def thermal_conditions(text) -> tuple:
    """(temperature_c, duration_min) from a protocol sentence, either may be None."""
    raw = str(text or "")
    temperature = None
    match = _TEMPERATURE.search(raw)
    if match:
        temperature = _number(match.group(1))

    duration = None
    match = _DURATION.search(raw)
    if match:
        amount = _number(match.group(1))
        if amount is not None:
            duration = round(amount * _TO_MINUTES[match.group(2).lower()], 4)
    return temperature, duration


def classify_treatment(text) -> Classification:
    """The physical treatment a sentence describes, where the keywords are decisive."""
    if not str(text or "").strip():
        return Classification(None, False, ())
    matched = _matches(text, _patterns()["treatment_patterns"])
    temperature, duration = thermal_conditions(text)
    if len(matched) == 1:
        return Classification(matched[0], True, matched, temperature, duration)
    return Classification(None, False, matched, temperature, duration)


def classify_application(text) -> Classification:
    """How an additive was applied, where the keywords are decisive."""
    if not str(text or "").strip():
        return Classification(None, False, ())
    matched = _matches(text, _patterns()["application_patterns"])
    if len(matched) == 1:
        return Classification(matched[0], True, matched)
    return Classification(None, False, matched)


def narrow(value, declared, sink):
    """Force a model's answer back into the closed set.

    The reply is already validated by `ProtocolRecord`, whose validators return None for an
    unknown value. This is the second half of that: None becomes the sink, so the column is
    never null on a field whose CHECK constraint has one.
    """
    return value if value in declared else sink


def treatment_or_sink(value) -> str:
    return narrow(value, TREATMENT_TYPES, UNCLASSIFIED_TREATMENT)


def application_or_sink(value) -> str:
    return narrow(value, APPLICATION_METHODS, UNSPECIFIED_APPLICATION)


def report(classifications) -> dict:
    """What the keyword pass could and could not answer, for the job result."""
    total = len(classifications)
    confident = sum(1 for item in classifications if item.confident)
    ambiguous = [item.matched for item in classifications if len(item.matched) > 1]
    return {
        "arms": total,
        "classified_by_keyword": confident,
        "ambiguous": len(ambiguous),
        "unmatched": total - confident - len(ambiguous),
    }
