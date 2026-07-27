"""Concordance checks, run before loading extracted data into the database.

Every check reports the offending rows and the rule violated rather than raising, so a
caller sees the full picture in one pass. `raise_on_violation` is available for a hard stop.

One deliberate non-rule: an experiment with no rows in `experiment_ingredients` is NOT a
violation. That is an untreated control, the baseline the whole comparison rests on.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.core.config import Config
from app.core.exceptions import ConcordanceError
from app.database import columns as C

VIOLATION_COLUMNS = ["rule", "table", "key", "detail"]

#: Concentrations above this in "% (w/w)" are physically impossible.
_MAX_PERCENT_CONCENTRATION = 100.0


@dataclass(frozen=True)
class _Ctx:
    experiments: pd.DataFrame
    ingredients: pd.DataFrame
    experiment_ingredients: pd.DataFrame
    indicators: pd.DataFrame
    measurements: pd.DataFrame
    config: Config


def run_concordance_checks(
    experiments: pd.DataFrame,
    ingredients: pd.DataFrame,
    experiment_ingredients: pd.DataFrame,
    indicators: pd.DataFrame,
    measurements: pd.DataFrame,
    config: Config,
) -> pd.DataFrame:
    """Return one row per violation: ``rule``, ``table``, ``key``, ``detail``.

    An empty frame means the data is concordant.
    """
    ctx = _Ctx(
        experiments=experiments,
        ingredients=ingredients,
        experiment_ingredients=experiment_ingredients,
        indicators=indicators,
        measurements=measurements,
        config=config,
    )
    rows: list[dict] = []
    for check in (
        _check_experiment_pk,
        _check_ingredient_pk,
        _check_ingredient_name_unique,
        _check_indicator_pk,
        _check_bridge_pk,
        _check_measurement_pk,
        _check_not_null,
        _check_orphan_bridge_experiments,
        _check_orphan_bridge_ingredients,
        _check_orphan_measurement_experiments,
        _check_orphan_measurement_indicators,
        _check_concentrations,
        _check_day,
        _check_indicator_value,
        _check_functional_class,
    ):
        rows.extend(check(ctx))
    return pd.DataFrame(rows, columns=VIOLATION_COLUMNS)


def raise_on_violation(violations: pd.DataFrame) -> None:
    if not violations.empty:
        raise ConcordanceError(violations)


# -- primary keys -----------------------------------------------------------------------


def _check_experiment_pk(ctx: _Ctx) -> list[dict]:
    dupes = ctx.experiments[ctx.experiments[C.EXPERIMENT_ID].duplicated(keep=False)]
    return [
        {
            "rule": "experiment_id_must_be_unique",
            "table": "experiments",
            "key": str(eid),
            "detail": f"experiment_id appears {n} times",
        }
        for eid, n in dupes[C.EXPERIMENT_ID].value_counts().items()
    ]


def _check_ingredient_pk(ctx: _Ctx) -> list[dict]:
    dupes = ctx.ingredients[ctx.ingredients[C.INGREDIENT_ID].duplicated(keep=False)]
    return [
        {
            "rule": "ingredient_id_must_be_unique",
            "table": "ingredients",
            "key": str(iid),
            "detail": f"ingredient_id appears {n} times",
        }
        for iid, n in dupes[C.INGREDIENT_ID].value_counts().items()
    ]


def _check_ingredient_name_unique(ctx: _Ctx) -> list[dict]:
    dupes = ctx.ingredients[ctx.ingredients[C.INGREDIENT_NAME].duplicated(keep=False)]
    return [
        {
            "rule": "ingredient_name_must_be_unique",
            "table": "ingredients",
            "key": str(name),
            "detail": f"ingredient_name appears {n} times",
        }
        for name, n in dupes[C.INGREDIENT_NAME].value_counts().items()
    ]


def _check_indicator_pk(ctx: _Ctx) -> list[dict]:
    dupes = ctx.indicators[ctx.indicators[C.INDICATOR_ID].duplicated(keep=False)]
    return [
        {
            "rule": "indicator_id_must_be_unique",
            "table": "indicators",
            "key": str(iid),
            "detail": f"indicator_id appears {n} times",
        }
        for iid, n in dupes[C.INDICATOR_ID].value_counts().items()
    ]


def _check_bridge_pk(ctx: _Ctx) -> list[dict]:
    key = [C.EXPERIMENT_ID, C.INGREDIENT_ID]
    dupes = ctx.experiment_ingredients[
        ctx.experiment_ingredients.duplicated(subset=key, keep=False)
    ]
    return [
        {
            "rule": "experiment_ingredient_pair_must_be_unique",
            "table": "experiment_ingredients",
            "key": f"{eid}/{iid}",
            "detail": f"pair appears {len(grp)} times",
        }
        for (eid, iid), grp in dupes.groupby(key)
    ]


def _check_measurement_pk(ctx: _Ctx) -> list[dict]:
    key = [C.EXPERIMENT_ID, C.DAY, C.INDICATOR_ID]
    dupes = ctx.measurements[ctx.measurements.duplicated(subset=key, keep=False)]
    return [
        {
            "rule": "measurement_key_must_be_unique",
            "table": "measurements",
            "key": f"{eid}/{day}/{iid}",
            "detail": f"key appears {len(grp)} times",
        }
        for (eid, day, iid), grp in dupes.groupby(key)
    ]


# -- not null ---------------------------------------------------------------------------

#: Columns the schema marks NOT NULL, per table.
_NOT_NULL = {
    "experiments": [C.MEAT_MATRIX, C.TREATMENT],
    "ingredients": [C.INGREDIENT_NAME, C.FUNCTIONAL_CLASS, C.SOURCE],
    "experiment_ingredients": [C.CONCENTRATION_UNIT],
    "indicators": [C.INDICATOR_TYPE, C.INDICATOR_UNIT],
    "measurements": [C.INDICATOR_VALUE],
}


def _check_not_null(ctx: _Ctx) -> list[dict]:
    frames = {
        "experiments": ctx.experiments,
        "ingredients": ctx.ingredients,
        "experiment_ingredients": ctx.experiment_ingredients,
        "indicators": ctx.indicators,
        "measurements": ctx.measurements,
    }
    out: list[dict] = []
    for table, cols in _NOT_NULL.items():
        df = frames[table]
        for col in cols:
            if col not in df.columns:
                out.append(
                    {
                        "rule": "required_column_must_exist",
                        "table": table,
                        "key": col,
                        "detail": "column missing entirely",
                    }
                )
                continue
            for idx in df.index[df[col].isna()]:
                out.append(
                    {
                        "rule": "not_null_column_must_be_present",
                        "table": table,
                        "key": str(idx),
                        "detail": f"{col} is null",
                    }
                )
    return out


# -- foreign keys -----------------------------------------------------------------------


def _check_orphan_bridge_experiments(ctx: _Ctx) -> list[dict]:
    known = set(ctx.experiments[C.EXPERIMENT_ID])
    orphans = ctx.experiment_ingredients[
        ~ctx.experiment_ingredients[C.EXPERIMENT_ID].isin(known)
    ]
    return [
        {
            "rule": "no_orphan_experiments",
            "table": "experiment_ingredients",
            "key": str(eid),
            "detail": "experiment_id not present in experiments",
        }
        for eid in sorted(set(orphans[C.EXPERIMENT_ID]))
    ]


def _check_orphan_bridge_ingredients(ctx: _Ctx) -> list[dict]:
    known = set(ctx.ingredients[C.INGREDIENT_ID])
    orphans = ctx.experiment_ingredients[
        ~ctx.experiment_ingredients[C.INGREDIENT_ID].isin(known)
    ]
    return [
        {
            "rule": "no_orphan_ingredients",
            "table": "experiment_ingredients",
            "key": str(iid),
            "detail": "ingredient_id not present in ingredients",
        }
        for iid in sorted(set(orphans[C.INGREDIENT_ID]))
    ]


def _check_orphan_measurement_experiments(ctx: _Ctx) -> list[dict]:
    known = set(ctx.experiments[C.EXPERIMENT_ID])
    orphans = ctx.measurements[~ctx.measurements[C.EXPERIMENT_ID].isin(known)]
    return [
        {
            "rule": "no_orphan_experiments",
            "table": "measurements",
            "key": str(eid),
            "detail": "experiment_id not present in experiments",
        }
        for eid in sorted(set(orphans[C.EXPERIMENT_ID]))
    ]


def _check_orphan_measurement_indicators(ctx: _Ctx) -> list[dict]:
    known = set(ctx.indicators[C.INDICATOR_ID])
    orphans = ctx.measurements[~ctx.measurements[C.INDICATOR_ID].isin(known)]
    return [
        {
            "rule": "no_orphan_indicators",
            "table": "measurements",
            "key": str(iid),
            "detail": "indicator_id not present in indicators",
        }
        for iid in sorted(set(orphans[C.INDICATOR_ID]))
    ]


# -- values -----------------------------------------------------------------------------


def _check_concentrations(ctx: _Ctx) -> list[dict]:
    out: list[dict] = []
    bridge = ctx.experiment_ingredients
    conc = pd.to_numeric(bridge[C.CONCENTRATION], errors="coerce")

    for idx in bridge.index[conc.isna()]:
        out.append(
            {
                "rule": "concentration_must_be_present_and_numeric",
                "table": "experiment_ingredients",
                "key": _bridge_key(ctx, idx),
                "detail": f"non-numeric or null: {bridge.loc[idx, C.CONCENTRATION]!r}",
            }
        )
    for idx in bridge.index[conc < 0]:
        out.append(
            {
                "rule": "concentration_must_be_non_negative",
                "table": "experiment_ingredients",
                "key": _bridge_key(ctx, idx),
                "detail": f"negative concentration: {conc.loc[idx]}",
            }
        )
    for idx in bridge.index[np.isinf(conc.fillna(0.0))]:
        out.append(
            {
                "rule": "concentration_must_be_finite",
                "table": "experiment_ingredients",
                "key": _bridge_key(ctx, idx),
                "detail": "infinite concentration",
            }
        )
    # Range only means something once the unit is known: a percentage over 100 is
    # impossible, whereas ppm or mg/kg has no such ceiling.
    if C.CONCENTRATION_UNIT in bridge.columns:
        pct = bridge[C.CONCENTRATION_UNIT].astype(str).str.contains("%", na=False)
        for idx in bridge.index[pct & (conc > _MAX_PERCENT_CONCENTRATION)]:
            out.append(
                {
                    "rule": "percent_concentration_must_be_in_range",
                    "table": "experiment_ingredients",
                    "key": _bridge_key(ctx, idx),
                    "detail": f"{conc.loc[idx]} exceeds {_MAX_PERCENT_CONCENTRATION}%",
                }
            )
    return out


def _check_day(ctx: _Ctx) -> list[dict]:
    out: list[dict] = []
    for idx in ctx.measurements.index:
        val = ctx.measurements.loc[idx, C.DAY]
        try:
            ok = float(val) == int(val) and int(val) >= 0
        except (TypeError, ValueError):
            ok = False
        if not ok:
            out.append(
                {
                    "rule": "day_must_be_non_negative_integer",
                    "table": "measurements",
                    "key": _measurement_key(ctx, idx),
                    "detail": f"day={val!r}",
                }
            )
    return out


def _check_indicator_value(ctx: _Ctx) -> list[dict]:
    out: list[dict] = []
    value = pd.to_numeric(ctx.measurements[C.INDICATOR_VALUE], errors="coerce")
    for idx in ctx.measurements.index[value.isna()]:
        out.append(
            {
                "rule": "indicator_value_must_be_present_and_numeric",
                "table": "measurements",
                "key": _measurement_key(ctx, idx),
                "detail": f"non-numeric or null: {ctx.measurements.loc[idx, C.INDICATOR_VALUE]!r}",
            }
        )
    return out


def _check_functional_class(ctx: _Ctx) -> list[dict]:
    """functional_class must be in the configured vocabulary.

    Under `unmapped_policy: bucket` an unknown class is routed to the unmapped bucket
    downstream, so it is reported here only under `unmapped_policy: error`.
    """
    if ctx.config.pillars.unmapped_policy != "error":
        return []
    vocab = set(ctx.config.pillars.leaves)
    unknown = ctx.ingredients[~ctx.ingredients[C.FUNCTIONAL_CLASS].isin(vocab)]
    return [
        {
            "rule": "functional_class_must_be_in_vocabulary",
            "table": "ingredients",
            "key": str(row[C.INGREDIENT_ID]),
            "detail": f"{row[C.FUNCTIONAL_CLASS]!r} not in {sorted(vocab)}",
        }
        for _, row in unknown.iterrows()
    ]


def _bridge_key(ctx: _Ctx, idx: object) -> str:
    row = ctx.experiment_ingredients.loc[idx]
    return f"{row[C.EXPERIMENT_ID]}/{row[C.INGREDIENT_ID]}"


def _measurement_key(ctx: _Ctx, idx: object) -> str:
    row = ctx.measurements.loc[idx]
    return f"{row[C.EXPERIMENT_ID]}/{row[C.DAY]}/{row[C.INDICATOR_ID]}"
