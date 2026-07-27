"""Shared time/event label construction from measurements vs indicator thresholds.

This is the single source the scenario joins build on. It implements the exact CTE the
project agreed on: an experiment's failure time is the earliest day *any* indicator breaches
its threshold; experiments that never breach are right-censored at their last observed day.

The threshold *direction* is the one thing the schema does not encode, so it is an explicit
parameter. `upper` (breach = value >= threshold) fits spoilage indicators that rise (TVC,
TVB-N, TMA-N, PV, TBARS); `lower` (breach = value <= threshold) fits a beneficial compound
dropping below a floor. Indicators with a NULL threshold never breach (SQL comparison to
NULL is never true) and so only contribute to the observation window.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

# direction -> the breach comparison operator applied as `indicator_value <op> threshold`.
_DIRECTION_OP = {"upper": ">=", "lower": "<="}


def label_cte(direction: str = "upper") -> str:
    """The `WITH ... labels AS (...)` block, ready to prepend to a scenario SELECT.

    Emits four CTEs -- `breach_events`, `first_breach`, `observation_window`, `labels` --
    with the breach operator chosen by `direction`. The operator comes from a fixed
    whitelist, never string interpolation of caller input, so this is injection-safe.
    """
    if direction not in _DIRECTION_OP:
        raise ValueError(f"direction must be one of {sorted(_DIRECTION_OP)}, got {direction!r}")
    op = _DIRECTION_OP[direction]
    return f"""
WITH breach_events AS (
    SELECT m.experiment_id, m.day, m.indicator_id
    FROM measurements m
    JOIN indicators i ON i.indicator_id = m.indicator_id
    WHERE m.indicator_value {op} i.indicator_threshold
),
first_breach AS (
    SELECT experiment_id, MIN(day) AS breach_day
    FROM breach_events
    GROUP BY experiment_id
),
observation_window AS (
    SELECT experiment_id, MAX(day) AS last_observed_day
    FROM measurements
    GROUP BY experiment_id
),
labels AS (
    SELECT
        ow.experiment_id,
        COALESCE(fb.breach_day, ow.last_observed_day) AS time,
        CASE WHEN fb.breach_day IS NOT NULL THEN 1 ELSE 0 END AS event
    FROM observation_window ow
    LEFT JOIN first_breach fb ON fb.experiment_id = ow.experiment_id
)"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open a read-only-ish sqlite connection to a schema-conforming DB."""
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"database not found: {db_path}")
    return sqlite3.connect(str(db_path))


def load_labels(conn: sqlite3.Connection, direction: str = "upper") -> pd.DataFrame:
    """Return one row per experiment: `experiment_id`, `time`, `event`."""
    return pd.read_sql_query(label_cte(direction) + "\nSELECT * FROM labels;", conn)


def indicator_breach_counts(conn: sqlite3.Connection, direction: str = "upper") -> pd.DataFrame:
    """Per indicator: how many measurements breach, so a caller can flag inert indicators.

    An indicator whose measurements never breach contributes no events and cannot influence
    the label -- worth surfacing (a wrong threshold, a wrong unit, or a genuinely stable
    indicator all look like this).
    """
    if direction not in _DIRECTION_OP:
        raise ValueError(f"direction must be one of {sorted(_DIRECTION_OP)}, got {direction!r}")
    op = _DIRECTION_OP[direction]
    sql = f"""
SELECT i.indicator_id,
       SUM(CASE WHEN m.indicator_value {op} i.indicator_threshold THEN 1 ELSE 0 END) AS breaches,
       COUNT(*) AS n_measurements
FROM measurements m
JOIN indicators i ON i.indicator_id = m.indicator_id
GROUP BY i.indicator_id
ORDER BY i.indicator_id;"""
    return pd.read_sql_query(sql, conn)
