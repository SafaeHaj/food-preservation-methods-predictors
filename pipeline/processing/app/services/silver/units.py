"""Putting every dose on one scale: ppm, meaning mg of substance per kg of matrix.

Papers state doses in whatever their field prefers -- 3.2 % w/w, 500 mg/kg, 0.05 g/100 g,
2000 ppm -- and a model cannot sum or compare those. One scale is what makes
`total_dose_ppm` a feature rather than a category, and mass basis is the choice that makes
it meaningful for a solid food.

The factors live here rather than in `vocabulary.yaml` deliberately. The YAML is corpus
data, mountable per project and editable without a migration; a gram is none of those
things. A user who could redefine one would silently change every dose in the corpus.

Two kinds of unconvertible, and they are not the same fact:

    no factor        a volumetric or activity unit with no mass basis (IU/g, µL/L)
    not a dose       a relative composition (peak area %) that describes an extract's
                     make-up, not how much of it was applied

Both yield None, which is why `concentration_ppm` is nullable and why the reason is
reported rather than collapsed into a zero. A zero would say "none was added".
"""

from __future__ import annotations

import re
import unicodedata
from typing import NamedTuple, Optional

#: Multiply a value in the keyed unit by this to get ppm (mg/kg).
_MASS_FACTORS = {
    "%": 10_000.0, "% (w/w)": 10_000.0, "w/w": 10_000.0, "g/100g": 10_000.0,
    "g/100 g": 10_000.0, "percent": 10_000.0,
    "‰": 1_000.0, "g/kg": 1_000.0, "mg/g": 1_000.0,
    "ppm": 1.0, "mg/kg": 1.0, "µg/g": 1.0, "ug/g": 1.0, "μg/g": 1.0,
    "ppb": 0.001, "µg/kg": 0.001, "ug/kg": 0.001, "ng/g": 0.001,
}

#: Same, but only true where the matrix behaves as water (ρ ≈ 1 kg/L). A marinade or a
#: dipping solution usually does; a fat-rich mince does not. The conversion is kept because
#: dropping these would discard most dipping doses, and flagged because it is an assumption.
_VOLUME_FACTORS = {
    "% (v/v)": 10_000.0, "v/v": 10_000.0,
    "g/l": 1_000.0, "g/L": 1_000.0, "mg/ml": 1_000.0, "mg/mL": 1_000.0,
    "mg/l": 1.0, "mg/L": 1.0, "µg/ml": 1.0, "ug/ml": 1.0, "μg/ml": 1.0,
}

#: Units that are not a dose at all. Named separately so the report can say which it was:
#: "we cannot convert this" and "this was never an amount applied" are different problems,
#: and only the first is fixed by adding a factor.
_NOT_A_DOSE = {
    "peak area %", "area %", "relative %", "relative abundance", "% of total",
    "% composition", "% peak area",
}

#: The three codepoints that render as "micro". `µ` (U+00B5 micro sign) and `μ` (U+03BC
#: Greek mu) are visually identical and both appear in extracted text; `u` is what a paper
#: writes when it has no symbol at all.
_MICRO = str.maketrans({"µ": "u", "μ": "u"})

_PUNCTUATION = re.compile(r"[\s.\-_]+")


def unit_key(unit) -> str:
    """The form every unit lookup uses.

    Not `gate.canonical_key`, which exists for substance names and is wrong for units in
    two ways that both silently corrupt doses: it strips punctuation entirely, so `%` and
    `‰` both become the empty string and one overwrites the other in a factor table -- a
    thousand-fold error in every percentage dose. And it folds Greek to Latin by name, so
    `µg/g` keys as `mug_g` while `ug/g` keys as `ug_g`, leaving two spellings of one unit
    converting differently.

    Here `/` and `%` are meaning, not noise, so they survive; only spacing and separators
    are collapsed.
    """
    text = unicodedata.normalize("NFKC", str(unit or "")).translate(_MICRO).lower()
    return _PUNCTUATION.sub("", text).strip()


_KEYED_MASS = {unit_key(unit): factor for unit, factor in _MASS_FACTORS.items()}
_KEYED_VOLUME = {unit_key(unit): factor for unit, factor in _VOLUME_FACTORS.items()}
_KEYED_NOT_A_DOSE = {unit_key(unit) for unit in _NOT_A_DOSE}


class Conversion(NamedTuple):
    """What one dose became, and whether the answer rests on an assumption.

    `rationale` is not decoration: `ck_evidence_rationale_when_not_stated` forces a derived
    span to carry one, so this string is what makes the original unit and factor auditable
    without a column to store them in.
    """

    ppm: Optional[float]
    approximate: bool
    reason: str
    rationale: str


def _rounded(value: float) -> float:
    """Four decimals is past any dose a paper prints, and keeps 0.05 % from becoming
    499.99999999999994 ppm in the rationale."""
    return round(value, 4)


def to_ppm(amount: Optional[float], unit: Optional[str],
           canonical: Optional[str] = None) -> Conversion:
    """Convert one stated dose to ppm.

    `canonical` is the vocabulary's preferred spelling of the unit when it has one. It is
    tried second, not first: the YAML folds `mg/L` into `ppm`, which is the density
    assumption above and must stay flagged, so the raw unit gets the first look.
    """
    if amount is None:
        return Conversion(None, False, "no_amount", "no amount was stated for this arm")

    raw = str(unit or "").strip()
    if not raw and not canonical:
        return Conversion(None, False, "no_unit", f"{amount} was stated with no unit")

    for candidate in (raw, canonical):
        if not candidate:
            continue
        key = unit_key(candidate)
        if key in _KEYED_NOT_A_DOSE:
            return Conversion(
                None, False, "not_a_dose",
                f"{candidate} describes relative composition, not an amount applied")
        factor = _KEYED_MASS.get(key)
        if factor is not None:
            ppm = _rounded(amount * factor)
            return Conversion(ppm, False, "converted",
                              f"{amount} {candidate} = {ppm} ppm (mg/kg)")
        factor = _KEYED_VOLUME.get(key)
        if factor is not None:
            ppm = _rounded(amount * factor)
            return Conversion(
                ppm, True, "converted_assuming_density",
                f"{amount} {candidate} = {ppm} ppm (mg/kg), assuming a density of 1 kg/L")

    return Conversion(None, False, "no_factor",
                      f"{raw or canonical} has no mass basis, so it cannot become ppm")


def reconcile(links, vocabulary=None) -> dict:
    """Fill `concentration_ppm` on every link in place. Returns the run's unit report.

    Never raises and never drops a link: an unconvertible dose keeps its stated pair and
    leaves the ppm null, which is exactly the distinction the column is nullable for.
    """
    report: dict = {"converted": 0, "approximate": 0, "unconvertible": []}
    for link in links:
        canonical = (vocabulary.canonical_unit(link.concentration_unit)
                     if vocabulary and link.concentration_unit else None)
        result = to_ppm(link.concentration, link.concentration_unit, canonical)
        link.concentration_ppm = result.ppm
        if result.ppm is None:
            if result.reason != "no_amount":
                report["unconvertible"].append({
                    "ingredient": link.ingredient_name,
                    "concentration": link.concentration,
                    "unit": link.concentration_unit,
                    "reason": result.reason,
                })
            continue
        report["converted"] += 1
        report["approximate"] += int(result.approximate)
    return report
