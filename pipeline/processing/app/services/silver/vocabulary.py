"""The controlled vocabulary: data, not code.

Four closed sets — matrices, indicators, ingredients and units — loaded from
`config/vocabulary.yaml`. Everything reaching the database is one of these values or is
flagged for review, which is what lets the schema gate stay free of keywords: the gate
decides *shape*, this decides *name*, and neither has to know the other's rules.

`VOCABULARY_VERSION` is the file's digest. It goes into the Silver and completion cache
keys, so editing a term invalidates exactly the cached work that term could have changed
and nothing else.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml

from shared.config import get_processing_settings
from shared.schemas.science import (
    FUNCTIONAL_CLASSES, INDICATOR_TYPES, INGREDIENT_SOURCES, UNCLASSIFIED_CLASS,
    UNKNOWN_SOURCE,
)
from shared.science.gate import canonical_key, split_label_and_unit

logger = logging.getLogger(__name__)
_settings = get_processing_settings()

KINDS = ("indicator", "ingredient", "matrix")

#: Fields each kind of term must carry, and the one any of them may.
REQUIRED_FIELDS = {
    "indicator": ("indicator_type", "unit"),
    "ingredient": ("functional_class", "source"),
    "matrix": (),
}
OPTIONAL_FIELDS = ("threshold",)

#: What an indicator becomes when the paper measured something it never named, or named it
#: in a unit nobody declared. Both are visible in the review report rather than silent.
UNRESOLVED_INDICATOR = "unresolved indicator"
UNSPECIFIED_UNIT = "unspecified"

_CFU_UNIT = re.compile(r"\bcfu\b", re.IGNORECASE)


@dataclass(frozen=True)
class VocabularySource:
    """The YAML file, validated but not yet indexed."""

    terms: list
    units: dict
    discarded: list
    version: str

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
    missing = [field_name for field_name in REQUIRED_FIELDS[kind] if entry.get(field_name) is None]
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
            **{field_name: entry[field_name] for field_name in known - {"name", "kind", "aliases"}
               if entry.get(field_name) is not None}}


def load_yaml_vocabulary(path) -> VocabularySource:
    """Read and validate the file. Raises rather than skipping a malformed term: a
    vocabulary that silently loses half its indicators produces an extraction that looks
    like it worked."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"No vocabulary at {path}. It is the source of every term the pipeline "
            "resolves against, and nothing regenerates it.")
    raw = path.read_bytes()
    payload = yaml.safe_load(raw.decode("utf-8")) or {}
    units = payload.get("units") or {}
    if not isinstance(units, dict):
        raise ValueError(f"{path.name}: `units` maps a canonical unit to its aliases")
    return VocabularySource(
        terms=[_term(entry, position)
               for position, entry in enumerate(payload.get("terms") or [])],
        units={str(canonical): [str(alias) for alias in (aliases or [])]
               for canonical, aliases in units.items()},
        discarded=[str(name) for name in (payload.get("discarded") or [])],
        version=hashlib.sha256(raw).hexdigest()[:16],
    )


@dataclass(eq=False)
class Term:
    key: str
    name: str
    kind: str
    unit: Optional[str] = None
    threshold: Optional[float] = None
    functional_class: Optional[str] = None
    source: Optional[str] = None
    indicator_type: Optional[str] = None
    aliases: list = field(default_factory=list)


class Vocabulary:
    """Alias -> preferred term, and the ledger of what it changed.

    One instance per paper: the ledgers (`unresolved`, `changes`, `flags`, `discarded`) are
    that paper's normalisation report, and sharing an instance across papers would make
    them a running total nobody can attribute.
    """

    def __init__(self, source: VocabularySource) -> None:
        self.source = source
        self.version = source.version
        self._by_kind: dict[str, dict[str, Term]] = {kind: {} for kind in KINDS}
        self.unresolved: dict[str, dict[str, str]] = {kind: {} for kind in KINDS}
        self.changes: dict = {}
        self.flags: dict = {}
        self.discarded: Counter = Counter()
        self._pattern: dict = {}

        self._unit_canonical = {
            canonical_key(alias): preferred
            for preferred, aliases in source.units.items()
            for alias in [preferred, *aliases]
        }
        self._discarded_pattern = _alternation(
            canonical_key(name) for name in source.discarded
        )
        for entry in source.terms:
            self.add(Term(
                key=canonical_key(entry["name"]),
                name=entry["name"], kind=entry["kind"],
                unit=self.canonical_unit(entry.get("unit")),
                threshold=entry.get("threshold"),
                functional_class=entry.get("functional_class"), source=entry.get("source"),
                indicator_type=entry.get("indicator_type"), aliases=entry.get("aliases", []),
            ))

    # ── Units ─────────────────────────────────────────────────────────────────

    def canonical_unit(self, unit) -> Optional[str]:
        text = str(unit or "").strip()
        return self._unit_canonical.get(canonical_key(text), text) if text else None

    def known_units(self) -> set[str]:
        """Canonical keys of the units the vocabulary declares."""
        return {canonical_key(preferred) for preferred in self.source.units}

    def names_a_discarded_quantity(self, text) -> bool:
        """Whether a phrase names something the vocabulary deliberately does not keep —
        sensory scores, colour coordinates, cooking loss."""
        pattern = self._discarded_pattern
        return bool(pattern and pattern.search(canonical_key(text)))

    # ── Index ─────────────────────────────────────────────────────────────────

    def add(self, term: Term) -> None:
        table = self._by_kind.setdefault(term.kind, {})
        for key in [term.key, *(canonical_key(alias) for alias in term.aliases)]:
            taken = table.get(key)
            if taken is not None and taken.name != term.name:
                self.flag(term.kind, term.name, f"key {key!r} already claimed by {taken.name!r}")
            table[key] = term
        self._pattern.pop(term.kind, None)

    def _compile(self, kind):
        """One alternation per kind, longest alternative first so "aerobic plate count"
        beats "count". Per-alias regexes blow through Python's cache at this call rate."""
        self._pattern[kind] = _alternation(
            key for key in self._by_kind.get(kind, {}) if len(key) >= 2
        )
        return self._pattern[kind]

    def pattern(self, kind):
        return self._pattern[kind] if kind in self._pattern else self._compile(kind)

    def resolve(self, text, kind) -> Optional[Term]:
        return self._by_kind.get(kind, {}).get(canonical_key(text))

    def names_in(self, text, kind) -> set:
        """Every known term of `kind` appearing in a phrase, longest match per span."""
        key = canonical_key(text)
        pattern = self.pattern(kind) if key else None
        if pattern is None:
            return set()
        table = self._by_kind[kind]
        return {table[match.group(1)] for match in pattern.finditer(key)}

    def find_in(self, text, kind) -> Optional[Term]:
        """Longest known term appearing anywhere in a phrase, for captions and prose."""
        key = canonical_key(text)
        pattern = self.pattern(kind) if key else None
        if pattern is None:
            return None
        best = max((match.group(1) for match in pattern.finditer(key)), key=len, default=None)
        return self._by_kind[kind][best] if best else None

    def terms_of(self, kind) -> dict:
        return self._by_kind.get(kind, {})

    # ── Ledger ────────────────────────────────────────────────────────────────

    def note_unresolved(self, text, kind) -> None:
        text = str(text or "").strip()
        if text:
            self.unresolved.setdefault(kind, {})[canonical_key(text)] = text

    def note_change(self, kind, raw, canonical, **extra) -> None:
        raw = str(raw or "").strip()
        if raw:
            self.changes[(kind, canonical_key(raw))] = {
                "kind": kind, "raw": raw, "canonical": canonical, **extra}

    def flag(self, kind, value, reason) -> None:
        value = str(value or "").strip()
        if value:
            self.flags[(kind, value)] = reason

    def review(self) -> dict:
        """What this paper's vocabulary could not name, changed, or threw away.

        Goes onto the job result rather than a file: it is the answer to "why is this term
        missing from the output", and it belongs beside the run that produced it.
        """
        return {
            "unresolved": {kind: sorted(names.values())
                           for kind, names in self.unresolved.items() if names},
            "changes": sorted(self.changes.values(), key=lambda item: item["raw"]),
            "flags": [{"kind": kind, "value": value, "reason": reason}
                      for (kind, value), reason in sorted(self.flags.items())],
            "discarded": [{"kind": kind, "value": value, "occurrences": count}
                          for (kind, value), count in sorted(self.discarded.items())],
        }

    # ── The two decisions ─────────────────────────────────────────────────────

    def normalise_ingredient(self, raw) -> Optional[dict]:
        """Name, functional class and origin together: one decision, not three.

        An unknown substance returns None and is parked for review rather than guessed at
        — a class invented for it would be indistinguishable downstream from a real one.
        """
        text = str(raw or "").strip()
        term = self.resolve(text, "ingredient")
        if term is None:
            self.note_unresolved(text, "ingredient")
            self.discarded[("ingredient", text)] += 1
            return None
        klass = term.functional_class if term.functional_class in FUNCTIONAL_CLASSES else None
        origin = term.source if term.source in INGREDIENT_SOURCES else None
        for field_name, value in (("functional_class", klass), ("source", origin)):
            if value is None:
                self.flag("ingredient", term.name, f"{field_name} outside its vocabulary")
        resolved = {"name": term.name, "functional_class": klass or UNCLASSIFIED_CLASS,
                    "source": origin or UNKNOWN_SOURCE}
        self.note_change("ingredient", text, term.name,
                         **{key: value for key, value in resolved.items() if key != "name"})
        return resolved

    def normalise_indicator(self, raw_label) -> Optional[dict]:
        """Resolve a column label to a named indicator with a canonical unit.

        The unit is split off and canonicalised before anything is matched, then the
        vocabulary's unit wins. None means a discarded quantity — sensory scores, colour
        coordinates — and the caller drops the observation.

        An unknown indicator, unlike an unknown ingredient, keeps the paper's wording and
        is flagged: a measurement nobody has named is still a measurement, whereas an
        ingredient with a guessed class would be silently wrong.
        """
        raw_name, raw_unit = split_label_and_unit(raw_label)
        unit = self.canonical_unit(raw_unit)
        if not raw_name:
            return {"name": UNRESOLVED_INDICATOR, "indicator_type": "chemical",
                    "unit": UNSPECIFIED_UNIT, "threshold": None}
        if self._discarded_pattern and self._discarded_pattern.search(canonical_key(raw_name)):
            self.discarded[("indicator", raw_name)] += 1
            return None

        term = self.resolve(raw_name, "indicator")
        unit = (term.unit if term and term.unit else unit) or UNSPECIFIED_UNIT
        # CFU is the only unit that settles the category on its own.
        inferred = "microbial" if _CFU_UNIT.search(unit) else "chemical"
        if term is None:
            self.note_unresolved(raw_name, "indicator")
            self.flag("indicator", raw_name, f"not in vocabulary; type inferred {inferred!r}")
            return {"name": raw_name, "indicator_type": inferred, "unit": unit,
                    "threshold": None}

        indicator_type = term.indicator_type
        if indicator_type not in INDICATOR_TYPES:
            indicator_type = inferred
            self.flag("indicator", term.name, f"no valid indicator_type; inferred {inferred!r}")
        self.note_change("indicator", raw_label, term.name,
                         indicator_type=indicator_type, unit=unit)
        return {"name": term.name, "indicator_type": indicator_type, "unit": unit,
                "threshold": term.threshold}


def _alternation(keys) -> Optional[re.Pattern]:
    """One regex matching any of `keys` as a whole underscore-delimited span, longest
    first. None when there is nothing to match."""
    ordered = sorted({key for key in keys if key}, key=len, reverse=True)
    if not ordered:
        return None
    return re.compile("(?:^|_)(" + "|".join(re.escape(key) for key in ordered) + ")(?:_|$)")


@lru_cache(maxsize=1)
def load_source() -> VocabularySource:
    """The file, read once per process. Validation failures surface at worker startup."""
    source = load_yaml_vocabulary(_settings.vocabulary_file)
    logger.info(
        "Vocabulary %s: %d terms (%s), %d canonical units, %d discarded quantities",
        source.version, len(source.terms),
        ", ".join(f"{len(source.of_kind(kind))} {kind}" for kind in KINDS),
        len(source.units), len(source.discarded),
    )
    return source


def build_vocabulary() -> Vocabulary:
    """A fresh index over the cached source. One per paper — see `Vocabulary`."""
    return Vocabulary(load_source())


def vocabulary_version() -> str:
    """The digest that participates in every downstream cache key."""
    return load_source().version
