"""Infer a project schema from an uploaded spreadsheet's columns.

The heuristics (plausible ranges, unit hints, what counts as a dropdown) live in
`config/schema_inference.yaml`, not in this module: they are domain knowledge that a food
scientist should be able to extend without touching Python.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any

import yaml

from shared.errors import ValidationError
from shared.schemas.projects import SchemaField

logger = logging.getLogger(__name__)

SERVICE_ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = SERVICE_ROOT / "config" / "schema_inference.yaml"

SPREADSHEET_SUFFIXES = (".xlsx", ".xls")


@lru_cache
def _rules() -> dict[str, Any]:
    if not RULES_PATH.exists():
        logger.warning("No schema inference rules at %s; falling back to bare types", RULES_PATH)
        return {}
    return yaml.safe_load(RULES_PATH.read_text(encoding="utf-8")) or {}


def _first_match(entries: list[dict], name: str) -> dict | None:
    for entry in entries:
        if any(keyword in name for keyword in entry.get("keywords", [])):
            return entry
    return None


def _validation_for(name: str) -> dict | None:
    match = _first_match(_rules().get("numeric_ranges", []), name)
    if not match:
        return None
    bounds = {key: match[key] for key in ("min", "max") if key in match}
    return bounds or None


def _unit_for(name: str) -> str | None:
    match = _first_match(_rules().get("units", []), name)
    return match.get("unit") if match else None


def infer_fields(filename: str, content: bytes) -> list[SchemaField]:
    """Infer schema fields from the columns of an Excel workbook."""
    if not filename.lower().endswith(SPREADSHEET_SUFFIXES):
        raise ValidationError(
            "Only .xlsx and .xls files can be used for schema inference",
            details={"filename": filename},
        )

    import pandas as pd

    rules = _rules()
    try:
        frame = pd.read_excel(BytesIO(content), nrows=rules.get("sample_rows", 50))
    except Exception as exc:
        raise ValidationError(
            "That spreadsheet could not be read", details={"reason": str(exc)}
        ) from exc

    select_rules = rules.get("select_detection", {})
    min_distinct = select_rules.get("min_distinct", 2)
    max_distinct = select_rules.get("max_distinct", 8)
    max_options = select_rules.get("max_options", 10)

    fields: list[SchemaField] = []
    for column in frame.columns:
        raw_name = str(column)
        normalized = raw_name.lower().replace(" ", "_")
        dtype = frame[column].dtype

        options: list[str] | None = None
        validation: dict | None = None

        if dtype in ("int64", "float64"):
            field_type = "number"
            validation = _validation_for(normalized)
        elif dtype == "bool":
            field_type = "boolean"
        else:
            distinct = frame[column].dropna().unique().tolist()
            is_select = (
                min_distinct <= len(distinct) <= max_distinct
                and all(isinstance(value, str) for value in distinct)
            )
            field_type = "select" if is_select else "text"
            if is_select:
                options = [str(value) for value in distinct[:max_options]]

        fields.append(
            SchemaField(
                name=normalized,
                label=raw_name.replace("_", " ").title(),
                type=field_type,
                unit=_unit_for(normalized),
                required=False,
                validation=validation,
                options=options,
            )
        )

    return fields
