"""Build the model-ready tables from the schema tables.

Two tables, because the corpus supports two differently-posed questions:

``survival``  one row per (arm, indicator). Failure time is the first day the
              indicator reaches its spoilage threshold (report Eq. 1); series
              that never reach it are right-censored at their last observed day.

``hazard``    one row per (arm, indicator, day) -- the person-period form used
              in discrete-time survival analysis. The label is "has this arm
              crossed the threshold by day d". Features are restricted to what
              is knowable before storage begins, plus the query day itself, so
              sweeping d over a grid recovers the whole survival curve.

The spreadsheet arms carry no time series, so they contribute failure times to
``survival`` only.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

HERE = Path(__file__).parent
DATA_DIR = HERE / "data"

VOCABULARY = yaml.safe_load((HERE / "vocabulary.yaml").read_text(encoding="utf-8"))
INDICATORS = VOCABULARY["indicators"]

FEATURE_COLUMNS = [
    "source", "meat_matrix", "matrix_moisture_percent", "matrix_protein_percent",
    "matrix_fat_percent", "matrix_salt_percent", "matrix_ph", "matrix_water_activity",
    "storage_temperature_c", "packaging_atmosphere", "treatment_type", "is_control",
    "n_ingredients", "total_dose_ppm", "logp_wmean", "mw_wmean", "pka_wmean",
    "ingredient_name", "functional_class", "ingredient_source",
    "indicator_name", "indicator_type", "indicator_unit", "indicator_threshold",
    "initial_value", "initial_fraction_of_threshold",
]
KEY_COLUMNS = ["study_id", "arm_id"]
OUTCOME_COLUMNS = ["shelf_life_days", "event", "censor_day", "spoiled_at_start"]


def _read(name: str) -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / name)


def corpus_survival() -> pd.DataFrame:
    """Failure time per (arm, indicator) series from the extracted trajectories."""
    measurements = _read("corpus_measurements.csv")
    experiments = _read("corpus_experiments.csv")
    indicators = _read("corpus_indicators.csv").set_index("indicator_name")

    measurements = measurements.sort_values(["arm_id", "indicator_name", "day"])
    measurements["indicator_threshold"] = measurements["indicator_name"].map(
        indicators["indicator_threshold"]
    )
    reached = measurements[measurements["indicator_value"] >= measurements["indicator_threshold"]]

    grouped = measurements.groupby(["arm_id", "indicator_name"])
    summary = pd.DataFrame({
        "censor_day": grouped["day"].max(),
        "first_day": grouped["day"].min(),
        "initial_value": grouped["indicator_value"].first(),
        "n_points": grouped["day"].size(),
    })
    summary["failure_day"] = reached.groupby(["arm_id", "indicator_name"])["day"].min()
    summary = summary.reset_index()

    summary["event"] = summary["failure_day"].notna().astype(int)
    summary["spoiled_at_start"] = (summary["failure_day"] == summary["first_day"]).fillna(False)
    summary["shelf_life_days"] = summary["failure_day"]

    frame = summary.merge(experiments, on="arm_id", how="left")
    frame = frame.merge(indicators.reset_index(), on="indicator_name", how="left")
    frame["source"] = "corpus"
    frame["study_id"] = "P" + frame["paper_id"].astype(str)
    frame["n_ingredients"] = np.where(frame["is_control"] == 1, 0,
                                      frame["ingredient_name"].notna().astype(int))
    frame["total_dose_ppm"] = frame["concentration_ppm"]
    frame["ingredient_source"] = np.nan
    frame["functional_class"] = np.nan
    frame[["logp_wmean", "mw_wmean", "pka_wmean"]] = np.nan

    links = _read("corpus_experiment_ingredients.csv")
    if not links.empty:
        chemistry = links.set_index("arm_id")
        for column, target in [("logp", "logp_wmean"), ("molecular_weight", "mw_wmean"),
                               ("pka", "pka_wmean")]:
            frame[target] = frame["arm_id"].map(chemistry[column])
        frame["functional_class"] = frame["arm_id"].map(chemistry["functional_class"])
        frame["ingredient_source"] = frame["arm_id"].map(chemistry["source"])

    frame["initial_fraction_of_threshold"] = (
        frame["initial_value"] / frame["indicator_threshold"]
    )
    return frame


def spreadsheet_survival() -> pd.DataFrame:
    """Failure time per (arm, indicator) row from the curated spreadsheet."""
    frame = _read("modified_data.csv").copy()
    slot_names = [c for c in frame.columns if c.endswith("_name") and c.startswith("ingredient_")]

    frame["source"] = "spreadsheet"
    frame["n_ingredients"] = frame[slot_names].notna().sum(axis=1)
    frame["is_control"] = (
        (frame["ingredient_1_name"].fillna("").str.lower() == "control")
        | (frame["total_dose_ppm"].fillna(0) == 0)
    ).astype(int)
    frame["ingredient_name"] = frame["ingredient_1_name"]
    frame["functional_class"] = frame["ingredient_1_functional_class"]
    frame["ingredient_source"] = frame["ingredient_1_source"]

    initial_columns = {
        name: f"initial_{name}" for name in frame["indicator_name"].dropna().unique()
    }
    frame["initial_value"] = [
        row.get(initial_columns.get(row["indicator_name"]), np.nan)
        for _, row in frame.iterrows()
    ]
    frame["event"] = frame["crossed"].astype(int)
    frame["censor_day"] = np.nan
    frame["spoiled_at_start"] = frame["initial_fraction_of_threshold"].fillna(0) >= 1
    frame["n_points"] = np.nan
    return frame


def build_survival() -> pd.DataFrame:
    columns = KEY_COLUMNS + FEATURE_COLUMNS + OUTCOME_COLUMNS + ["n_points"]
    parts = []
    for frame in (corpus_survival(), spreadsheet_survival()):
        parts.append(frame.reindex(columns=columns))
    combined = pd.concat(parts, ignore_index=True)
    combined["is_control"] = combined["is_control"].fillna(0).astype(int)
    combined["spoiled_at_start"] = combined["spoiled_at_start"].fillna(False).astype(bool)
    return combined


def build_hazard(survival: pd.DataFrame) -> pd.DataFrame:
    """Person-period expansion of the corpus series.

    One row per observed (arm, indicator, day); the label says whether the
    threshold has been reached by that day. Only the corpus contributes, since
    the spreadsheet rows have no observation grid.
    """
    measurements = _read("corpus_measurements.csv")
    corpus = survival[survival["source"] == "corpus"]

    frame = measurements.merge(
        corpus, on=["arm_id", "indicator_name"], how="inner", suffixes=("", "_arm")
    )
    frame["spoiled"] = (
        frame["shelf_life_days"].notna() & (frame["day"] >= frame["shelf_life_days"])
    ).astype(int)
    frame["day_fraction_of_window"] = frame["day"] / frame["censor_day"].replace(0, np.nan)
    return frame


def relative_shelf_life(survival: pd.DataFrame) -> pd.DataFrame:
    """Shelf life divided by the control arm of the same study and indicator.

    This is the quantity the food scientists actually compare, and it removes
    the study-level offset that dominates the raw failure time.
    """
    events = survival[survival["event"] == 1].copy()
    controls = (
        events[events["is_control"] == 1]
        .groupby(["study_id", "indicator_name"])["shelf_life_days"]
        .mean()
        .rename("control_shelf_life_days")
    )
    merged = events.merge(controls, on=["study_id", "indicator_name"], how="left")
    merged["relative_shelf_life"] = (
        merged["shelf_life_days"] / merged["control_shelf_life_days"]
    )
    return merged


def main() -> None:
    survival = build_survival()
    hazard = build_hazard(survival)

    survival.to_csv(DATA_DIR / "survival.csv", index=False)
    hazard.to_csv(DATA_DIR / "hazard.csv", index=False)

    print(f"survival.csv  {survival.shape[0]} rows x {survival.shape[1]} cols")
    print(f"  by source:     {survival['source'].value_counts().to_dict()}")
    print(f"  studies:       {survival['study_id'].nunique()}")
    print(f"  arms:          {survival['arm_id'].nunique()}")
    print(f"  events:        {int(survival['event'].sum())} "
          f"({survival['event'].mean():.0%})")
    print(f"  already spoiled at day 0: {int(survival['spoiled_at_start'].sum())}")
    print()
    print(f"hazard.csv    {hazard.shape[0]} rows x {hazard.shape[1]} cols")
    print(f"  studies:       {hazard['study_id'].nunique()}")
    print(f"  spoiled rate:  {hazard['spoiled'].mean():.3f}")
    print(f"  day range:     {hazard['day'].min():.0f}-{hazard['day'].max():.0f}")
    print()
    relative = relative_shelf_life(survival)
    covered = relative["relative_shelf_life"].notna()
    print(f"relative shelf life defined for {int(covered.sum())} of {len(relative)} events")


if __name__ == "__main__":
    main()
