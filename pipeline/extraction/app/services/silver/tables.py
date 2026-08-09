"""Deterministic table cleaning, before the gate looks at anything.

Docling exports a table as it found it, which for a published paper means positional
column names where the header spanned two rows, a footnote sitting in the last row as one
long cell, and whitespace everywhere. None of that is a data problem, but all of it makes
a table fail a structural test it should pass.

Polars rather than pandas: this is the notebook's tuned behaviour carried over intact, and
a rewrite is where a port acquires its bugs.
"""

from __future__ import annotations

import re
from typing import Any, Sequence

import polars as pl

from shared.science.gate import DUPLICATE_SUFFIX

_POSITIONAL_HEADER = re.compile(r"^(unnamed[:_ ]|column[_ ]?\d+$|\d+$|_duplicated_)", re.IGNORECASE)

#: Share of columns that must look positional before row 0 is treated as the real header.
HEADER_PROMOTION_RATIO = 0.6
#: A lone trailing cell longer than this is a footnote, not data.
FOOTNOTE_MIN_CHARS = 40


def dedupe_names(names: Sequence[Any]) -> list:
    """Make column names unique, first occurrence untouched: a two-row header repeats its
    group label, so lifting it collapses two columns onto one name."""
    seen: dict = {}
    unique = []
    for name in names:
        text = str(name)
        seen[text] = seen.get(text, 0) + 1
        unique.append(text if seen[text] == 1 else f"{text}{DUPLICATE_SUFFIX}{seen[text]}")
    return unique


def promote_header_row(frame: pl.DataFrame) -> pl.DataFrame:
    """Lift row 0 into the header when Docling left the columns positional."""
    if frame.height < 2:
        return frame
    threshold = max(1, int(HEADER_PROMOTION_RATIO * frame.width))
    if sum(1 for name in frame.columns if _POSITIONAL_HEADER.match(str(name))) < threshold:
        return frame
    first = [str(value).strip() if value is not None else "" for value in frame.row(0)]
    if sum(1 for value in first if value) < threshold:
        return frame

    promoted = frame.slice(1)
    promoted.columns = dedupe_names(new or old for old, new in zip(frame.columns, first))
    return promoted


def drop_footnote_rows(frame: pl.DataFrame) -> pl.DataFrame:
    """Drop trailing rows holding one long free-text cell — the shape of a footnote."""
    height = frame.height
    while height:
        filled = [str(value).strip() for value in frame.row(height - 1)
                  if value is not None and str(value).strip()]
        if len(filled) == 1 and len(filled[0]) > FOOTNOTE_MIN_CHARS:
            height -= 1
            continue
        break
    return frame if height == frame.height else frame.slice(0, height)


def clean_table_frame(frame: pl.DataFrame) -> pl.DataFrame:
    frame = promote_header_row(frame)
    frame.columns = dedupe_names(frame.columns)
    stripped = [pl.col(name).str.strip_chars()
                for name, dtype in zip(frame.columns, frame.dtypes) if dtype == pl.Utf8]
    if stripped:
        frame = frame.with_columns(stripped)
    frame = frame.select([name for name in frame.columns if not frame[name].is_null().all()])
    if frame.height and frame.width:
        frame = frame.filter(
            pl.any_horizontal([pl.col(name).is_not_null() for name in frame.columns])
        )
    return drop_footnote_rows(frame)


def read_table_csv(path) -> pl.DataFrame:
    """Load a Docling table CSV as text throughout.

    Inferred dtypes are the enemy here: a column of "7.2 ± 0.3" and "<0.01" is not a float
    column, and letting polars decide turns the cells it cannot parse into nulls before the
    gate's own parser ever sees them.
    """
    return pl.read_csv(
        path, infer_schema_length=0, truncate_ragged_lines=True, ignore_errors=True,
    )


def frame_to_records(frame: pl.DataFrame) -> tuple:
    """The (headers, rows) pair the gate consumes."""
    return list(frame.columns), [list(row) for row in frame.iter_rows()]


def as_markdown_table(headers: Sequence[Any], rows: Sequence[Sequence[Any]], limit: int = 5) -> str:
    """A small pipe table for prompts and previews, without pulling in tabulate."""
    def cell(value):
        return "" if value is None else str(value).replace("|", "\\|").strip()

    head = [cell(name) for name in headers]
    lines = ["| " + " | ".join(head) + " |", "| " + " | ".join("---" for _ in head) + " |"]
    for row in rows[:limit]:
        lines.append("| " + " | ".join(cell(value) for value in row) + " |")
    if len(rows) > limit:
        lines.append(f"_({len(rows) - limit} more rows)_")
    return "\n".join(lines)


def write_records_csv(headers: Sequence[Any], rows: Sequence[Sequence[Any]], path) -> None:
    """Persist a converted figure's table so the gate report and the UI can show it."""
    frame = pl.DataFrame(
        {str(name): [("" if row[index] is None else str(row[index])) if index < len(row) else ""
                     for row in rows]
         for index, name in enumerate(dedupe_names(headers))}
    )
    frame.write_csv(path)
