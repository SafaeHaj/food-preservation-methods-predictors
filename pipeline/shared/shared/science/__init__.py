"""Domain logic with two consumers, and therefore no service to live in.

`gate.py` is the schema gate: pure functions over headers and rows that decide whether a
table holds values observed along an ordinal axis. Extraction runs it during the workspace
job; processing re-runs it in `silver/review`, once a model has named the axis column of a
table the gate could not key.

It lives here for the same reason `shared.schemas.science` does — stated in that module's
docstring: two things must agree on it, and `shared` cannot depend on a service. Extraction
still owns the gate's *behaviour*; only its address is shared.
"""

from shared.science.gate import (
    DUPLICATE_SUFFIX,
    KEYED_LABEL,
    MIN_AXIS_POINTS,
    MIN_ENUMERATION_ROWS,
    MIN_NUMERIC_RATIO,
    MIN_SERIES_POINTS,
    Dose,
    Observation,
    SchemaFit,
    canonical_key,
    column_label,
    declares_mean,
    fits_schema,
    observation_payload,
    parse_axis_label,
    parse_dosed_label,
    parse_number,
    split_axis_from_label,
    split_label_and_unit,
)

__all__ = [
    "DUPLICATE_SUFFIX",
    "Dose",
    "KEYED_LABEL",
    "MIN_AXIS_POINTS",
    "MIN_ENUMERATION_ROWS",
    "MIN_NUMERIC_RATIO",
    "MIN_SERIES_POINTS",
    "Observation",
    "SchemaFit",
    "canonical_key",
    "column_label",
    "declares_mean",
    "fits_schema",
    "observation_payload",
    "parse_axis_label",
    "parse_dosed_label",
    "parse_number",
    "split_axis_from_label",
    "split_label_and_unit",
]
