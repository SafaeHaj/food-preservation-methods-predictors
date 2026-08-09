"""The schema gate: does this table hold values observed over an ordinal axis?

One structural contract for native tables and chart-converted figures alike. An asset
passes only if it has an ordered axis, labels, and numeric values that vary along it --
decided by shape, with no keyword list anywhere, so it survives a change of corpus. The
keyword heuristics in `asset_classifier` drive the curation screen; they do not decide
this, and merging the two would put a corpus-specific word list back into the one place
that deliberately has none.

Pure functions over headers and rows: no I/O, no database, no Docling. That is what makes
the contract testable directly, and what lets it live in `shared`: extraction runs it during
the workspace job, and processing re-runs it once a model has named the axis of a table the
gate could not key. Its fixtures are `shared/tests/test_gate.py`.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from functools import cached_property, lru_cache
from itertools import zip_longest
from typing import Any, NamedTuple, Optional, Sequence

#: Three is the smallest number of points that can show a trend rather than a pair.
MIN_AXIS_POINTS = 3
MIN_SERIES_POINTS = 3
#: Below this share of parseable cells a column is prose that happens to contain digits.
MIN_NUMERIC_RATIO = 0.6
#: How many rows a perfectly-ascending column needs before it reads as a row counter.
MIN_ENUMERATION_ROWS = 6
EPS = 1e-9

_SD_SPLIT = re.compile(r"\s*(?:±|\+/-|\+-)\s*")
_PAREN_TAIL = re.compile(r"\s*\([^)]*\)\s*$")
_LEAD_CMP = re.compile(r"^[<>≤≥~≈=]+\s*")
_TRAIL_MARK = re.compile(r"\s*(?:[*†‡§¶]+|[a-zA-Z]{1,3})$")
_THOUSANDS = re.compile(r"^[-+]?\d{1,3}(?:,\d{3})+$")
_DECIMAL_COMMA = re.compile(r"^[-+]?\d+,\d+$")


@lru_cache(maxsize=16384)
def _parse_number_text(value: str) -> Optional[float]:
    text = value.replace("−", "-").replace(" ", " ").strip()
    if not text:
        return None

    text = _SD_SPLIT.split(text, 1)[0].strip()
    text = _PAREN_TAIL.sub("", text).strip()
    text = _LEAD_CMP.sub("", text).strip()
    text = text.rstrip("%").strip()
    text = _TRAIL_MARK.sub("", text).strip()
    if not text:
        return None

    if _THOUSANDS.match(text):
        text = text.replace(",", "")
    elif _DECIMAL_COMMA.match(text):
        text = text.replace(",", ".")

    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def parse_number(value: Any) -> Optional[float]:
    """Parse a table cell to a float, or None.

    Handles what papers actually print: "7.2 ± 0.3", "<0.01", "1,234", "6,5", "4.1a" with
    a superscripted significance letter, and a trailing footnote dagger.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    return _parse_number_text(str(value).strip())


_MEAN_NOTATION = re.compile(
    r"±|\+/-|\+-|\bmeans?\b|\baverages?\b|\bsd\b|\bsem\b|\bstdev\b"
    r"|\(\s*\d+(?:\.\d+)?\s*\)\s*$",
    re.IGNORECASE,
)


def declares_mean(text: Any) -> bool:
    """True when a cell, a header or a caption says its numbers are already averaged."""
    return bool(_MEAN_NOTATION.search(str(text or "")))


_HEADER_NUMBER = re.compile(r"[-+]?\d*\.?\d+")
_ARTIFACT_HEADER = re.compile(
    r"^(unnamed[:_ ]|column[_ ]?\d+$|level[_ ]?\d+$|_duplicated_|index$)", re.IGNORECASE
)


def parse_axis_label(name: Any) -> Optional[float]:
    """The ordinal position a column *name* denotes, if any."""
    text = str(name).strip().replace("−", "-")
    if not text or _ARTIFACT_HEADER.match(text):
        return None
    match = _HEADER_NUMBER.search(text)
    if not match:
        return None
    number = float(match.group())
    return number if math.isfinite(number) else None


_LABEL_PARTS = re.compile(r"\s*[,;|]\s*|\s+-\s+|\s+–\s+|\s+—\s+")


@lru_cache(maxsize=16384)
def _split_axis(text: str) -> tuple:
    parts = [part for part in _LABEL_PARTS.split(text) if part and part.strip()]
    if not parts:
        return None, text
    for index, part in enumerate(parts):
        position = parse_axis_label(part)
        if position is not None:
            residue = " ".join(other.strip() for at, other in enumerate(parts) if at != index)
            return position, residue.strip(" -_,")
    return None, text


def split_axis_from_label(label: Any) -> tuple:
    """"control, 6 days" -> (6.0, "control").

    A label carrying no position comes back unchanged beside None, so a caller can tell
    "not keyed" from "keyed with no arm".
    """
    return _split_axis(str(label or "").strip())


_GREEK_TO_LATIN = str.maketrans({
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "epsilon",
    "ζ": "zeta", "η": "eta", "θ": "theta", "ι": "iota", "κ": "kappa",
    "λ": "lambda", "μ": "mu", "ν": "nu", "ξ": "xi", "ο": "omicron",
    "π": "pi", "ρ": "rho", "ς": "sigma", "σ": "sigma", "τ": "tau",
    "υ": "upsilon", "φ": "phi", "χ": "chi", "ψ": "psi", "ω": "omega",
})
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_UNDERSCORES = re.compile(r"_+")


@lru_cache(maxsize=32768)
def _canonical_key(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text).lower().translate(_GREEK_TO_LATIN)
    folded = folded.encode("ascii", "ignore").decode("ascii")
    return _UNDERSCORES.sub("_", _NON_ALNUM.sub("_", folded)).strip("_")


def canonical_key(text: Any) -> str:
    """The form every "same term?" comparison uses: ascii, lower, punctuation collapsed."""
    return _canonical_key(str(text or ""))


DUPLICATE_SUFFIX = "__dup"
_DUPLICATE_TAIL = re.compile(re.escape(DUPLICATE_SUFFIX) + r"\d+$")

_DOSE = re.compile(
    r"""^\s*
    (?P<lead>.*?)\s*
    (?P<amount>\d+(?:[.,]\d+)?)\s*
    (?P<unit>%|ppm|ppb|mg/(?:g|ml|kg|l)|g/(?:kg|l)|µg/g|ug/g|mm|mg|w/w|v/v|w/v)
    \s*(?P<trail>.*?)\s*$""",
    re.VERBOSE | re.IGNORECASE,
)


class Dose(NamedTuple):
    substance: Optional[str]
    amount: float
    unit: str


@lru_cache(maxsize=8192)
def _parse_dosed(text: str) -> Optional[Dose]:
    match = _DOSE.match(_DUPLICATE_TAIL.sub("", text))
    if not match:
        return None
    lead, digits = match.group("lead"), match.group("amount")
    while len(digits) > 1 and digits[0] == "0" and "." not in digits:
        lead, digits = lead + "0", digits[1:]
    substance = " ".join(part for part in (lead, match.group("trail")) if part).strip(" -_,")
    return Dose(substance or None, float(digits.replace(",", ".")), match.group("unit").lower())


def parse_dosed_label(label: Any) -> Optional[Dose]:
    """Split "0.5% Moringa Extract" into substance, amount and unit, or None."""
    return _parse_dosed(str(label or "").strip())


_TRAILING_UNIT = re.compile(r"^(?P<name>.*?)[\s_]*[\(\[\{](?P<unit>[^\)\]\}]{1,24})[\)\]\}]\s*$")

_STATS_TAIL = re.compile(
    r"\s*[\(\[\{][^\)\]\}]*"
    r"(?:±|\bmean\b|\bmedian\b|\bstdev\b|\bstd\b|\bsd\b|\bsem?\b|\bn\s*=)"
    r"[^\)\]\}]*[\)\]\}]\s*$",
    re.IGNORECASE,
)


def split_label_and_unit(label: Any) -> tuple:
    """Split "TVC (log CFU/g)" into ("TVC", "log CFU/g"). Unit is None if absent."""
    text = _DUPLICATE_TAIL.sub("", str(label or "").strip()).strip()
    while True:
        trimmed = _STATS_TAIL.sub("", text).strip()
        if trimmed == text or not trimmed:
            break
        text = trimmed
    if not text:
        return "", None
    match = _TRAILING_UNIT.match(text)
    if not match:
        return text, None
    name = match.group("name").strip(" _-")
    unit = match.group("unit").strip()
    if not name or not unit:
        return text, None
    return name, unit


@dataclass(slots=True)
class Observation:
    """One value at one axis point.

    `column_label` and `row_labels` stay apart because which one names the indicator is a
    semantic question, and the gate does not answer semantic questions.
    """

    axis_value: float
    value: float
    column_label: Optional[str] = None
    row_labels: dict = field(default_factory=dict)
    reports_mean: bool = False


@dataclass
class SchemaFit:
    fits: bool
    reason: str
    orientation: Optional[str] = None
    axis_label: Optional[str] = None
    axis_values: list = field(default_factory=list)
    axis_confidence: float = 0.0
    axis_runs: int = 0
    value_columns: list = field(default_factory=list)
    label_columns: list = field(default_factory=list)
    observations: list = field(default_factory=list)
    columns: list = field(default_factory=list, repr=False)

    def summary(self) -> dict:
        """What is worth persisting on the asset and showing in the gate report."""
        return {
            "fits": self.fits,
            "reason": self.reason,
            "orientation": self.orientation,
            "axis_label": self.axis_label,
            "axis_points": self.axis_values,
            "axis_confidence": round(self.axis_confidence, 2),
            "axis_runs": self.axis_runs,
            "value_columns": self.value_columns,
            "label_columns": self.label_columns,
            "observation_count": len(self.observations),
        }


@dataclass
class _Column:
    """Never mutated after `_columns` builds it, so the statistics below can be cached:
    gating compares every column against every other."""

    position: int
    name: str
    raw: list
    numeric: list

    @cached_property
    def values(self) -> list:
        return [value for value in self.numeric if value is not None]

    @cached_property
    def entries(self) -> list:
        """The non-empty cells, stripped — the denominator of every ratio below."""
        return [text for text in (("" if cell is None else str(cell).strip())
                                  for cell in self.raw) if text]

    @cached_property
    def numeric_ratio(self) -> float:
        return len(self.values) / len(self.entries) if self.entries else 0.0

    @cached_property
    def is_numeric(self) -> bool:
        return self.numeric_ratio >= MIN_NUMERIC_RATIO and len(self.values) >= MIN_AXIS_POINTS

    @cached_property
    def names_an_entity_per_row(self) -> bool:
        """A different entry on every row, over enough rows to be no coincidence."""
        return (len(self.entries) >= MIN_ENUMERATION_ROWS
                and len(set(self.entries)) == len(self.entries))

    @cached_property
    def keyed(self) -> list:
        """Per row, the axis position its label carries and what is left of the label:
        `[(6.0, 'control'), (None, 'treatments'), ...]`, aligned with `raw`."""
        return [split_axis_from_label(cell) if cell is not None else (None, "")
                for cell in self.raw]

    @cached_property
    def keys_an_axis(self) -> bool:
        """Enough rows carry a position, over enough distinct positions, to be an axis."""
        positions = [position for position, _ in self.keyed if position is not None]
        return (len(positions) >= MIN_SERIES_POINTS
                and len(set(positions)) >= MIN_AXIS_POINTS)


def _columns(headers: Sequence[Any], rows: Sequence[Sequence[Any]]) -> list:
    transposed = list(zip_longest(*rows, fillvalue=None)) if rows else []
    result = []
    for index, name in enumerate(headers):
        raw = list(transposed[index]) if index < len(transposed) else [None] * len(rows)
        result.append(_Column(position=index, name=str(name), raw=raw,
                              numeric=[parse_number(cell) for cell in raw]))
    return result


def _reports_mean(column: _Column, row_index: int) -> bool:
    return declares_mean(column.raw[row_index]) or declares_mean(column.name)


def _row_labels(row: Sequence[Any], label_columns: Sequence[_Column]) -> dict:
    """This row's entry in each qualifier column."""
    labels = {}
    for column in label_columns:
        cell = row[column.position] if column.position < len(row) else None
        text = "" if cell is None else str(cell).strip()
        if text:
            labels[column.name] = text
    return labels


def _runs(numeric: Sequence[Optional[float]]) -> list:
    """Maximal non-decreasing runs; a drop starts a new one.

    A time axis either climbs once or resets per group, and both are visible without
    reading what it measures.
    """
    runs, current = [], []
    for value in numeric:
        if value is None:
            continue
        if current and value < current[-1] - EPS:
            runs.append(current)
            current = [value]
        else:
            current.append(value)
    if current:
        runs.append(current)
    return runs


def _enumerates_rows(column: _Column, columns: Sequence[_Column]) -> bool:
    """A column that is just the row's position — "No.", "#" — climbing perfectly while
    measuring nothing. Both conditions are needed: either alone catches a daily series."""
    positioned = [(index, value) for index, value in enumerate(column.numeric) if value is not None]
    if len(positioned) < MIN_ENUMERATION_ROWS:
        return False
    if len({value - index for index, value in positioned}) != 1:
        return False
    return any(other.names_an_entity_per_row for other in columns
               if other.position != column.position and not other.is_numeric)


def _axis_quality(column: _Column, columns: Sequence[_Column]) -> Optional[dict]:
    """Score a numeric column as an ordinal axis, or None if it cannot be one."""
    values = column.values
    if len(values) < MIN_AXIS_POINTS:
        return None
    if _enumerates_rows(column, columns):
        return None
    if parse_dosed_label(column.name):
        return None

    runs = _runs(column.numeric)
    if not runs or min(len(set(run)) for run in runs) < MIN_AXIS_POINTS:
        return None

    distinct = sorted(set(values))
    if len(distinct) < MIN_AXIS_POINTS:
        return None

    repeat_ratio = 1.0 - (len(distinct) / len(values))
    return {
        "runs": len(runs),
        "distinct": distinct,
        "repeat_ratio": repeat_ratio,
        "confidence": min(1.0, 0.4 + 0.3 * (len(runs) > 1) + 0.3 * repeat_ratio),
    }


def _fit_long(columns: list, rows: Sequence[Sequence[Any]],
              prefer_axis: Optional[str] = None) -> SchemaFit:
    numeric_columns = [column for column in columns if column.is_numeric]
    if not numeric_columns:
        return SchemaFit(fits=False, reason="no column holds 3 or more numeric values")

    candidates = []
    for column in numeric_columns:
        quality = _axis_quality(column, columns)
        if quality:
            candidates.append((column, quality))

    forced = None
    if prefer_axis:
        forced = next(
            (column for column in numeric_columns if canonical_key(column.name) == prefer_axis),
            None,
        )
    if forced is not None and not any(column is forced for column, _ in candidates):
        candidates.append((forced, {
            "runs": 0,
            "distinct": sorted(set(forced.values)),
            "repeat_ratio": 0.0,
            "confidence": 0.3,
        }))

    if not candidates:
        return SchemaFit(fits=False, reason="no column orders the rows like an axis")

    if forced is not None:
        column, quality = next(pair for pair in candidates if pair[0] is forced)
    else:
        column, quality = max(
            candidates,
            key=lambda pair: (
                pair[1]["runs"],
                pair[1]["repeat_ratio"] if pair[1]["runs"] > 1 else 0.0,
                -pair[0].position,
            ),
        )

    value_columns = [
        other
        for other in numeric_columns
        if other.position != column.position
        and len(other.values) >= MIN_SERIES_POINTS
        and len(set(other.values)) >= 2
    ]
    if not value_columns:
        return SchemaFit(
            fits=False,
            reason="an axis but no varying measured column alongside it",
            orientation="long",
            axis_label=column.name,
            axis_values=quality["distinct"],
        )

    label_columns = [other for other in columns if not other.is_numeric and other.entries]

    observations = []
    axis_numeric = column.numeric
    for row_index, row in enumerate(rows):
        axis_value = axis_numeric[row_index]
        if axis_value is None:
            continue
        row_labels = _row_labels(row, label_columns)
        for measured in value_columns:
            value = measured.numeric[row_index]
            if value is not None:
                observations.append(
                    Observation(axis_value=axis_value, value=value,
                                column_label=measured.name, row_labels=row_labels,
                                reports_mean=_reports_mean(measured, row_index))
                )

    return SchemaFit(
        fits=True,
        reason="long: one axis column, measured values in sibling columns",
        orientation="long",
        axis_label=column.name,
        axis_values=quality["distinct"],
        axis_confidence=quality["confidence"],
        axis_runs=quality["runs"],
        value_columns=[measured.name for measured in value_columns],
        label_columns=[label.name for label in label_columns],
        observations=observations,
    )


def _fit_wide(columns: list, rows: Sequence[Sequence[Any]]) -> SchemaFit:
    axis_columns = []
    for column in columns:
        position = parse_axis_label(column.name)
        if position is not None:
            axis_columns.append((position, column))

    if len(axis_columns) < MIN_AXIS_POINTS:
        return SchemaFit(fits=False, reason="fewer than 3 column names denote an axis position")

    positions = [position for position, _ in axis_columns]
    if any(later <= earlier for earlier, later in zip(positions, positions[1:])):
        return SchemaFit(fits=False, reason="axis-like column names do not increase left to right")

    if sum(1 for _, column in axis_columns if parse_dosed_label(column.name)) >= 2:
        return SchemaFit(fits=False, reason="column names are a dose ladder, not an axis")

    parseable = sum(len(column.values) for _, column in axis_columns)
    total = sum(len(column.entries) for _, column in axis_columns)
    if not total or parseable / total < MIN_NUMERIC_RATIO:
        return SchemaFit(fits=False, reason="cells under the axis columns are not numeric")

    axis_positions = {column.position for _, column in axis_columns}
    label_columns = [column for column in columns
                     if column.position not in axis_positions and column.entries]

    observations = []
    rows_used = 0
    for row_index, row in enumerate(rows):
        points = [
            (position, column)
            for position, column in axis_columns
            if column.numeric[row_index] is not None
        ]
        if len(points) < MIN_SERIES_POINTS:
            continue
        rows_used += 1
        row_labels = _row_labels(row, label_columns) or {"row": f"row {row_index + 1}"}
        for position, column in points:
            observations.append(
                Observation(axis_value=position, value=column.numeric[row_index],
                            column_label=None,
                            row_labels=row_labels,
                            reports_mean=_reports_mean(column, row_index))
            )

    if not rows_used:
        return SchemaFit(
            fits=False,
            reason="no row carries 3 or more points across the axis",
            orientation="wide",
        )

    return SchemaFit(
        fits=True,
        reason="wide: axis in the column names, one series per row",
        orientation="wide",
        axis_label="|".join(column.name for _, column in axis_columns),
        axis_values=positions,
        axis_confidence=0.9,
        axis_runs=1,
        value_columns=[column.name for _, column in axis_columns],
        label_columns=[label.name for label in label_columns],
        observations=observations,
    )


KEYED_LABEL = "row label"


def column_label(name: Any) -> str:
    """The name a column is known by."""
    return str(name or "").strip() or KEYED_LABEL


def _fit_keyed(columns: list, rows: Sequence[Sequence[Any]],
               prefer_axis: Optional[str] = None) -> SchemaFit:
    """The axis is inside a text label, one cell per row: "control, 6 days".

    The label's residue is carried as a row label under the column's own name, which is
    where the interpretation stage already looks for an arm.
    """
    candidates = [column for column in columns
                  if not column.is_numeric and column.keys_an_axis]
    if prefer_axis:
        named = [column for column in columns
                 if not column.is_numeric
                 and canonical_key(column_label(column.name)) == prefer_axis]
        candidates = named or candidates
    if not candidates:
        return SchemaFit(fits=False, reason="no label column carries an axis position")

    value_columns = [column for column in columns
                     if column.is_numeric and len(set(column.values)) >= 2]
    if not value_columns:
        return SchemaFit(fits=False, reason="a keyed axis but no varying measured column",
                         orientation="keyed")

    column = max(candidates, key=lambda item: (
        len({position for position, _ in item.keyed if position is not None}), -item.position))

    keyed = column.keyed
    arms_present = any(position is not None and residue for position, residue in keyed)

    other_labels = [item for item in columns
                    if item is not column and not item.is_numeric and item.entries]
    axis_name = column_label(column.name)
    observations = []
    used = set()
    for row_index, row in enumerate(rows):
        position, residue = keyed[row_index]
        if position is None or (arms_present and not residue):
            continue
        used.add(position)
        row_labels = _row_labels(row, other_labels)
        if residue:
            row_labels[axis_name] = residue
        for measured in value_columns:
            value = measured.numeric[row_index]
            if value is not None:
                observations.append(
                    Observation(axis_value=position, value=value,
                                column_label=measured.name, row_labels=row_labels,
                                reports_mean=_reports_mean(measured, row_index))
                )

    if len(used) < MIN_AXIS_POINTS:
        return SchemaFit(fits=False, reason="fewer than 3 axis positions survive keying",
                         orientation="keyed")

    positions = [position for position, _ in keyed if position is not None]
    return SchemaFit(
        fits=True,
        reason="keyed: the axis is inside a row label, measured values alongside",
        orientation="keyed",
        axis_label=axis_name,
        axis_values=sorted(used),
        axis_confidence=0.7,
        axis_runs=len(_runs(positions)),
        value_columns=[measured.name for measured in value_columns],
        label_columns=[item.name for item in other_labels] + [axis_name],
        observations=observations,
    )


def fits_schema(headers: Sequence[Any], rows: Sequence[Sequence[Any]],
                prefer_axis: Optional[str] = None) -> SchemaFit:
    """Does this table hold values observed over an ordinal axis?

    Every orientation is fitted and the stronger evidence wins: a long axis that
    *restarts*, then one spelled out in the column names, then a long axis that climbs
    once, then one keyed out of a row label. Wide cannot go first — a dose ladder in the
    header reads as a perfectly good ascending axis — and keyed goes last, because reading
    a number out of prose is the weakest evidence here.

    `prefer_axis` is the canonical key of a column an operator or the review call named as
    the axis. It is a hint about *which* column orders the rows, never a value: the gate
    still extracts every number itself.
    """
    if not headers or not rows:
        return SchemaFit(fits=False, reason="empty table")

    columns = _columns(headers, rows)

    if prefer_axis and any(not column.is_numeric
                           and canonical_key(column_label(column.name)) == prefer_axis
                           for column in columns):
        fit = _fit_keyed(columns, rows, prefer_axis=prefer_axis)
        fit.columns = columns
        return fit

    long = _fit_long(columns, rows, prefer_axis=prefer_axis)
    wide = keyed = None
    if not (long.fits and (long.axis_runs > 1 or prefer_axis)):
        wide = _fit_wide(columns, rows)
    if not (long.fits or (wide is not None and wide.fits)):
        keyed = _fit_keyed(columns, rows, prefer_axis=prefer_axis)

    if wide is not None and wide.fits:
        fit = wide
    elif long.fits:
        fit = long
    elif keyed is not None and keyed.fits:
        fit = keyed
    elif wide is not None and wide.orientation:
        fit = wide
    else:
        fit = long

    fit.columns = columns
    return fit


def observation_payload(fit: SchemaFit) -> list[dict]:
    """Serialise a fit's observations with their labels still unresolved.

    The gate decides shape; naming happens against the vocabulary, in the processing
    service. Resolving here would put a corpus-specific term inside the one module built to
    have none. Both consumers need this: extraction writes it into the package, and
    processing rewrites it after a model has named an axis the gate missed.
    """
    return [
        {
            "axis_value": observation.axis_value,
            "value": observation.value,
            "column_label": observation.column_label,
            "row_labels": observation.row_labels,
            "reports_mean": observation.reports_mean,
        }
        for observation in fit.observations
    ]
