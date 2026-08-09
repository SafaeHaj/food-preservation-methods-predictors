from dataclasses import dataclass
from pathlib import Path

import yaml

__all__ = ["KINDS", "VocabularySource", "load_yaml_vocabulary"]

KINDS = ("indicator", "ingredient", "matrix")

REQUIRED_FIELDS = {
    "indicator": ("indicator_type", "unit"),
    "ingredient": ("functional_class", "source"),
    "matrix": (),
}
OPTIONAL_FIELDS = ("threshold",)


@dataclass(frozen=True)
class VocabularySource:
    terms: list
    units: dict
    discarded: list

    def of_kind(self, kind) -> list:
        return [term for term in self.terms if term["kind"] == kind]


def _term(entry, position) -> dict:
    where = f"terms[{position}]"
    if not isinstance(entry, dict):
        raise ValueError(f"{where} is {type(entry).__name__}, not a mapping")
    name, kind = entry.get("name"), entry.get("kind")
    if not name:
        raise ValueError(f"{where} has no name")
    if kind not in KINDS:
        raise ValueError(f"{where} ({name}) has kind {kind!r}; expected one of {list(KINDS)}")
    missing = [field for field in REQUIRED_FIELDS[kind] if entry.get(field) is None]
    if missing:
        raise ValueError(f"{where} ({name}) is a {kind} missing {', '.join(missing)}")

    aliases = entry.get("aliases") or []
    if not isinstance(aliases, list):
        raise ValueError(f"{where} ({name}) has aliases as {type(aliases).__name__}, not a list")
    known = {"name", "kind", "aliases", *REQUIRED_FIELDS[kind], *OPTIONAL_FIELDS}
    unknown = sorted(set(entry) - known)
    if unknown:
        raise ValueError(f"{where} ({name}) has fields no {kind} uses: {', '.join(unknown)}")
    return {"name": str(name), "kind": kind, "aliases": [str(alias) for alias in aliases],
            **{field: entry[field] for field in known - {"name", "kind", "aliases"}
               if entry.get(field) is not None}}


def load_yaml_vocabulary(path) -> VocabularySource:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"No vocabulary at {path}. It is the source of every term the pipeline "
            "resolves against, and nothing regenerates it.")
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    units = payload.get("units") or {}
    if not isinstance(units, dict):
        raise ValueError(f"{path.name}: `units` maps a canonical unit to its aliases")
    return VocabularySource(
        terms=[_term(entry, position)
               for position, entry in enumerate(payload.get("terms") or [])],
        units={str(canonical): [str(alias) for alias in (aliases or [])]
               for canonical, aliases in units.items()},
        discarded=[str(name) for name in (payload.get("discarded") or [])],
    )
