"""
Concentration unit normalization for the V6 specialist models.

The V6 datasets (data/raw/CHEESE_SHELF_LIFE_V6_*_SPECIALIST.csv) carry both the
originally-entered concentration (`primary_concentration`/`primary_concentration_unit`,
23 distinct unit spellings) and a normalized pair (`canonical_concentration_value`/
`canonical_concentration_unit`, 13 canonical units) that the specialist models are
trained on.

CONCENTRATION_UNIT_CONVERSION below was extracted empirically from every
(raw_unit, canonical_unit) pair actually present across all three V6 files --
each factor's standard deviation across every row sharing that pair is ~1e-14
or smaller (floating-point noise, not real variance), confirming the mapping
is a fixed, deterministic conversion rather than something inferred or
invented. Regenerate/re-verify with `python concentration_units.py --verify`.

Do not add a unit pair here that has not been empirically confirmed against
the training data this way -- to_canonical() deliberately raises on an
unrecognized unit rather than guessing a factor.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent

# raw_unit -> (canonical_unit, multiply_by_this_to_get_canonical_value)
CONCENTRATION_UNIT_CONVERSION: dict[str, tuple[str, float]] = {
    # Same-unit pairs (factor 1.0, canonical spelling === raw spelling already)
    "% w/v": ("% w/v", 1.0),
    "AU/g": ("AU/g", 1.0),
    "IU/g": ("IU/g", 1.0),
    "g": ("g", 1.0),
    "hr": ("hr", 1.0),
    "log CFU/g": ("log CFU/g", 1.0),
    "mg/L": ("mg/L", 1.0),
    "mg/kg": ("mg/kg", 1.0),
    "ml": ("ml", 1.0),
    "mmol/L": ("mmol/L", 1.0),
    "none": ("none", 1.0),
    # Notation-normalization pairs (factor 1.0, spelling differs)
    "%": ("% w/w", 1.0),
    "% ( v/v)": ("% v/v", 1.0),
    "% (v/v)": ("% v/v", 1.0),
    "%(w/v)": ("% w/v", 1.0),
    "(w/v) %": ("% w/v", 1.0),
    "(w/w) %": ("% w/w", 1.0),
    "ppm": ("mg/kg", 1.0),
    "wt %": ("% w/w", 1.0),
    # V7 uses this raw spelling directly (unlike V6's bare "%"/"wt %") --
    # verified empirically: ratio == 1.0, std == 0.0 across 17,662 V7 rows.
    "% w/w": ("% w/w", 1.0),
    # Real magnitude conversions
    "g/L": ("mg/L", 1000.0),
    "g/kg": ("% w/w", 0.1),
    "mg/5 ml": ("mg/L", 200.0),
    "mg/g": ("% w/w", 0.1),
    "mg/mL": ("mg/L", 1000.0),
}


class UnrecognizedConcentrationUnit(ValueError):
    """Raised when a (value, unit) pair has no verified conversion path.
    Deliberately fails loudly rather than guessing a factor -- see module
    docstring."""


def to_canonical(value: float | None, raw_unit: str | None) -> tuple[float | None, str | None]:
    """Convert a user-entered (value, unit) pair to the canonical units the
    V6 specialist models were trained on. Returns (None, None) for a
    no-treatment row (unit == 'none' or value is None)."""
    if raw_unit is None or value is None:
        return None, None
    raw_unit = str(raw_unit).strip()
    if raw_unit == "none":
        return 0.0, "none"
    if raw_unit not in CONCENTRATION_UNIT_CONVERSION:
        raise UnrecognizedConcentrationUnit(
            f"No verified conversion for concentration unit {raw_unit!r}. "
            f"Known units: {sorted(CONCENTRATION_UNIT_CONVERSION)}"
        )
    canonical_unit, factor = CONCENTRATION_UNIT_CONVERSION[raw_unit]
    return float(value) * factor, canonical_unit


def _verify() -> None:
    """Re-derive the table from the raw V6 + V7 CSVs and assert it matches
    what's hardcoded above (zero variance per pair, same canonical unit)."""
    import pandas as pd

    frames = [
        pd.read_csv(ROOT / "data" / "raw" / f"CHEESE_SHELF_LIFE_V6_{name}_SPECIALIST.csv")
        for name in ("SOFT", "SEMI_HARD", "HARD")
    ] + [
        pd.read_csv(ROOT / "data" / "raw" / f"CHEESE_SHELF_LIFE_V7_{name}_SPECIALIST_CORRECTED.csv")
        for name in ("SOFT", "SEMI_HARD", "HARD")
    ]
    all_rows = pd.concat(frames, ignore_index=True)
    pairs = all_rows.groupby(["primary_concentration_unit", "canonical_concentration_unit"]).size()
    seen_units = {str(raw) for raw, _canon in pairs.index}
    missing = seen_units - set(CONCENTRATION_UNIT_CONVERSION)
    if missing:
        raise AssertionError(f"Unit(s) present in data but missing from CONCENTRATION_UNIT_CONVERSION: {missing}")

    checked = 0
    for raw_unit, canon_unit in pairs.index:
        raw_unit, canon_unit = str(raw_unit), str(canon_unit)
        expected_canon, factor = CONCENTRATION_UNIT_CONVERSION[raw_unit]
        assert expected_canon == canon_unit, f"{raw_unit}: table says canonical={expected_canon}, data says {canon_unit}"
        sub = all_rows[
            (all_rows["primary_concentration_unit"] == raw_unit)
            & (all_rows["canonical_concentration_unit"] == canon_unit)
            & (all_rows["primary_concentration"] > 0)
        ]
        if len(sub) == 0:
            continue
        ratio = sub["canonical_concentration_value"] / sub["primary_concentration"]
        assert ratio.std() < 1e-6, f"{raw_unit}->{canon_unit}: non-deterministic ratio, std={ratio.std()}"
        assert abs(ratio.mean() - factor) < 1e-6, f"{raw_unit}->{canon_unit}: table factor {factor} != data factor {ratio.mean()}"
        checked += 1
    print(f"Verified {checked} unit-conversion pairs against {len(all_rows)} V6+V7 rows. OK.")


if __name__ == "__main__":
    import sys

    if "--verify" in sys.argv:
        _verify()
    else:
        print(f"{len(CONCENTRATION_UNIT_CONVERSION)} known concentration units. Run with --verify to check against data.")
