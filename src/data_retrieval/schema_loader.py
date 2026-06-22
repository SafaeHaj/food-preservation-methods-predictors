"""
Loads matrix schema YAML and dynamically builds a Pydantic extraction model.

The key design: LLM outputs use human-readable aliases as JSON keys. Pydantic
accepts those via validation_alias and stores values under db_key attribute names.
Every extracted field is wrapped in EvidencedValue so the LLM always returns
{"value": ..., "evidence": "<verbatim quote>"} per field.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Generic, Optional, TypeVar

import yaml
from pydantic import BaseModel, Field, create_model
from pydantic.config import ConfigDict

T = TypeVar("T")

_TYPE_MAP: dict[str, type] = {
    "string": str,
    "number": float,
    "integer": int,
}


class EvidencedValue(BaseModel, Generic[T]):
    value: T
    evidence: str


class _AliasBase(BaseModel):
    """Base class that allows construction by either db_key or alias."""
    model_config = ConfigDict(populate_by_name=True)


def _resolve_type(type_spec: Any) -> type:
    if isinstance(type_spec, list):
        non_null = [t for t in type_spec if t != "null"]
        base = _TYPE_MAP.get(non_null[0], str) if non_null else str
        return Optional[base]
    return _TYPE_MAP.get(type_spec, str)


def load_schema(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_extraction_model(schema: dict) -> type[BaseModel]:
    """
    Dynamically create a Pydantic model from the schema YAML.

    - Field attribute name  = db_key  (used in final JSON output)
    - validation_alias      = alias   (what the LLM writes in its JSON response)
    - Every field is wrapped in EvidencedValue[T]
    - system_computed_fields are excluded entirely
    """
    computed = set(schema.get("system_computed_fields", []))
    required_keys = set(schema.get("required", []))
    aliases = schema.get("aliases", {})
    properties = schema.get("properties", {})

    field_defs: dict[str, tuple] = {}

    for db_key, prop in properties.items():
        if db_key in computed:
            continue

        py_type = _resolve_type(prop.get("type", "string"))
        alias = aliases.get(db_key, db_key)
        desc = prop.get("description", "")

        # Wrap in EvidencedValue so the LLM always supplies evidence
        ev_type = EvidencedValue[py_type]

        if db_key in required_keys:
            field_defs[db_key] = (
                ev_type,
                Field(validation_alias=alias, description=desc),
            )
        else:
            field_defs[db_key] = (
                Optional[ev_type],
                Field(default=None, validation_alias=alias, description=desc),
            )

    return create_model("ExtractionRecord", __base__=_AliasBase, **field_defs)


def to_db_dict(record: BaseModel) -> dict:
    """
    Serialize using db_keys (not aliases).
    EvidencedValue dicts are preserved as {"value": ..., "evidence": ...}
    for downstream auditability.
    """
    return record.model_dump(by_alias=False)


def get_anchor_concepts(schema: dict) -> list[dict]:
    return schema.get("anchor_concepts", [])
