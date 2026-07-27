"""Scenario A / E join+pivot design tables, built on the shared label CTE.

Both scenarios keep SQL's job to producing a clean per-experiment table (labels + either raw
ingredient concentrations or per-class doses); the wide pivot happens in pandas so the column
set is discovered from the data and grows with the catalog -- no query regeneration.

Scenario A (A1): one column per ``ingredient_name``. Each ingredient keeps its own column, so
mixed units across ingredients are harmless -- every column is standardized independently
downstream.

Scenario E: one column per ``functional_class``, the per-experiment SUM of member
concentrations. Summing is only meaningful when a class shares a unit; `class_unit_report`
surfaces any class that mixes units so the caller can decide, rather than silently summing
mg/kg + % into garbage.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

import pandas as pd

from app.prediction.labels import label_cte

META_COLS = ["experiment_id", "meat_matrix", "treatment", "time", "event"]


@dataclass
class Design:
    """A per-experiment design table: meta columns + feature columns, one row per experiment."""

    name: str                 # "scenario_a" | "scenario_e"
    frame: pd.DataFrame       # indexed 0..n-1; contains META_COLS + feature_cols
    feature_cols: list[str]
    meta_cols: list[str]

    @property
    def n_experiments(self) -> int:
        return len(self.frame)


def _slug(text: str) -> str:
    return re.sub(r"[^0-9a-z]+", "_", str(text).strip().lower()).strip("_")


def _meta(conn: sqlite3.Connection, direction: str) -> pd.DataFrame:
    """One row per experiment: the context + label, before any feature columns."""
    sql = label_cte(direction) + """
SELECT e.experiment_id, e.meat_matrix, e.treatment, l.time, l.event
FROM experiments e
JOIN labels l ON l.experiment_id = e.experiment_id
ORDER BY e.experiment_id;"""
    meta = pd.read_sql_query(sql, conn)
    return meta


def _attach(meta: pd.DataFrame, wide: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    """Left-join a wide feature block onto meta, filling absent experiments (controls) with 0."""
    wide = wide.reindex(index=meta["experiment_id"], columns=feature_cols, fill_value=0.0)
    wide = wide.reset_index(drop=True)
    out = pd.concat([meta.reset_index(drop=True), wide], axis=1)
    return out


def scenario_a(conn: sqlite3.Connection, direction: str = "upper") -> Design:
    """Wide ingredient-concentration matrix (one column per ingredient)."""
    meta = _meta(conn, direction)
    long = pd.read_sql_query(
        label_cte(direction) + """
SELECT e.experiment_id, i.ingredient_name, ei.concentration
FROM experiments e
JOIN labels l ON l.experiment_id = e.experiment_id
LEFT JOIN experiment_ingredients ei ON ei.experiment_id = e.experiment_id
LEFT JOIN ingredients i ON i.ingredient_id = ei.ingredient_id
ORDER BY e.experiment_id;""",
        conn,
    )
    conc = long.dropna(subset=["ingredient_name"]).copy()
    conc["col"] = "conc_" + conc["ingredient_name"].map(_slug)
    wide = conc.pivot_table(
        index="experiment_id", columns="col", values="concentration",
        aggfunc="sum", fill_value=0.0,
    )
    feature_cols = sorted(wide.columns)
    frame = _attach(meta, wide, feature_cols)
    return Design("scenario_a", frame, feature_cols, META_COLS)


def scenario_e(conn: sqlite3.Connection, direction: str = "upper") -> Design:
    """Wide functional-class dose matrix (one column per functional_class)."""
    meta = _meta(conn, direction)
    doses = pd.read_sql_query(
        label_cte(direction) + """,
class_doses AS (
    SELECT ei.experiment_id, i.functional_class, SUM(ei.concentration) AS class_dose
    FROM experiment_ingredients ei
    JOIN ingredients i ON i.ingredient_id = ei.ingredient_id
    GROUP BY ei.experiment_id, i.functional_class
)
SELECT e.experiment_id, cd.functional_class, cd.class_dose
FROM experiments e
JOIN labels l ON l.experiment_id = e.experiment_id
LEFT JOIN class_doses cd ON cd.experiment_id = e.experiment_id
ORDER BY e.experiment_id;""",
        conn,
    )
    cd = doses.dropna(subset=["functional_class"]).copy()
    cd["col"] = "dose_" + cd["functional_class"].map(_slug)
    wide = cd.pivot_table(
        index="experiment_id", columns="col", values="class_dose",
        aggfunc="sum", fill_value=0.0,
    )
    feature_cols = sorted(wide.columns)
    frame = _attach(meta, wide, feature_cols)
    return Design("scenario_e", frame, feature_cols, META_COLS)


def class_unit_report(conn: sqlite3.Connection) -> pd.DataFrame:
    """Per functional_class: the distinct units it mixes.

    A class with >1 unit makes Scenario E's raw SUM meaningless (add a unit-conversion pass
    before aggregating). One unit per class means the SUM is safe as-is.
    """
    df = pd.read_sql_query(
        """
SELECT i.functional_class, ei.concentration_unit
FROM experiment_ingredients ei
JOIN ingredients i ON i.ingredient_id = ei.ingredient_id;""",
        conn,
    )
    rep = (
        df.groupby("functional_class")["concentration_unit"]
        .agg(lambda s: sorted(set(s)))
        .reset_index()
    )
    rep["n_units"] = rep["concentration_unit"].map(len)
    rep["unit_safe"] = rep["n_units"] == 1
    return rep
