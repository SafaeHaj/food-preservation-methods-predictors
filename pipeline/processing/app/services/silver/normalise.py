"""The only place names are resolved.

Silver hands Gold a package where the matrix, the arms, their concentrations, the
indicator names, types and units, and every ingredient's class and origin are already
decided. Gold assembles records and resolves nothing — which is what keeps the two
separable, and what makes the vocabulary a single edit point rather than a rule scattered
across an assembler.

The hard part is not naming an indicator; it is deciding, for one number in one cell,
which of its labels names the quantity and which names the arm it was measured on. Papers
put either in either place, so `_assign_roles` works from the paper's own vocabulary of
arms (built from the dose ladders it prints) rather than from any fixed rule.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from itertools import chain
from typing import Optional

from shared.config import get_processing_settings
from shared.science.gate import (
    DUPLICATE_SUFFIX, MIN_NUMERIC_RATIO, Dose, canonical_key, declares_mean,
    parse_dosed_label, parse_number, split_label_and_unit,
)

from app.services.silver.vocabulary import build_vocabulary

logger = logging.getLogger(__name__)
_settings = get_processing_settings()

_DUPLICATE_TAIL = re.compile(re.escape(DUPLICATE_SUFFIX) + r"\d+$")

_LABEL_SEPARATORS = (" - ", " – ", " — ", ": ", " | ", " _ ")

#: Characters of a label kept when it is recorded as evidence for where a term came from.
EVIDENCE_LABEL_CHARS = 80
CAPTION_SUMMARY_CHARS = 60


# ─── Arms ─────────────────────────────────────────────────────────────────────

_OCR_DIGITS = {"0": "o", "1": "l", "5": "s"}
_OCR_IN_WORD = re.compile(r"(?<=[A-Za-z])[015](?=[A-Za-z]|$|[+/&\s])")


def unfold_ocr_digits(text: str) -> str:
    """"THYME 0IL" -> "THYME OIL". Only inside a word, so "TEO 1%" keeps its dose."""
    return _OCR_IN_WORD.sub(lambda match: _OCR_DIGITS[match.group()], text)


@dataclass
class Treatment:
    """One arm.

    `ingredients` is the additive dimension — empty means a control — and `condition` is
    whatever else the label names: the factor a study crosses with its doses, "Vacuum" in
    "Vacuum + 1% TEO".
    """

    key: str
    label: str
    condition: Optional[str]
    ingredients: list = field(default_factory=list)

    @property
    def dosed(self) -> bool:
        return bool(self.ingredients)


def _dosed_ingredients(dose: Optional[Dose], vocabulary) -> tuple:
    """(substances the label names with their concentration, the parts that named none).

    The second is the arm's condition: no vocabulary decides it, so a factorial dimension
    nobody thought to seed still separates two arms.
    """
    if not (dose and dose.substance):
        return [], []
    found, unmatched = [], []
    for part in re.split(r"\s*[+&]\s*", unfold_ocr_digits(dose.substance)):
        part = part.strip(" -_,")
        if not part:
            continue
        resolved = vocabulary.normalise_ingredient(part) if vocabulary else None
        if resolved:
            found.append({**resolved, "amount": dose.amount, "unit": dose.unit})
        else:
            unmatched.append(part)
    return found, unmatched


def _dose_key(ingredients) -> str:
    """What separates one rung of a dose ladder from the next."""
    return "|".join(f"{item['name']}={item['amount']}{item['unit']}"
                    for item in sorted(ingredients, key=lambda item: item["name"]))


def parse_treatment(label, vocabulary=None) -> Treatment:
    """Read one arm: its substances, their concentrations, and its condition.

    The dose rides on each ingredient rather than entering a name, so it lands in
    `concentration` instead of becoming part of a term. The condition is in the key because
    two arms sharing a dose ladder and differing only in how they were packed are two arms.
    """
    text = _DUPLICATE_TAIL.sub("", str(label or "").strip())
    dose = parse_dosed_label(text)
    ingredients, unmatched = _dosed_ingredients(dose, vocabulary)
    condition = " ".join(unmatched) or None
    if vocabulary is not None and dose and not ingredients:
        vocabulary.flag("ingredient", text,
                        "dosed arm whose substance is not in the vocabulary — reads as a "
                        "control, and the substance is keying the arm as a condition")
    substances = " + ".join(item["name"] for item in ingredients)
    return Treatment(
        key=canonical_key(f"{condition or ''}|{substances}|{_dose_key(ingredients)}")
            or canonical_key(text) or "unspecified",
        label=text, condition=condition, ingredients=ingredients)


def _has_separator(label) -> bool:
    return any(separator in label for separator in _LABEL_SEPARATORS)


def split_indicator_and_treatment(label, lexicon) -> tuple:
    """Split "PBC (log cfu/g) - Control1" when the tail is a known arm."""
    text = str(label or "").strip()
    for separator in _LABEL_SEPARATORS:
        if separator in text:
            head, _, tail = text.rpartition(separator)
            if canonical_key(tail) in lexicon:
                return head.strip(), tail.strip()
    return text, None


def _candidate_columns(asset) -> list:
    """Labels that could name an arm, in two groups: value column headers, and the row
    labels a keyed table leaves behind.

    They stay apart because `_collect_arms` treats a dose anywhere in a group as evidence
    about the whole group.
    """
    gate = asset.get("gate") or {}
    axis = {canonical_key(part) for part in str(gate.get("axis_label") or "").split("|")}

    def keep(names):
        return [name for name in names if canonical_key(name) not in axis]

    headers = keep(str(name) for name in gate.get("value_columns", []))
    labels, seen = [], set()
    for observation in asset.get("observations", []):
        for value in (observation.get("row_labels") or {}).values():
            if value not in seen:
                seen.add(value)
                labels.append(str(value))
    return [headers, keep(labels)]


def _collect_arms(columns_per_asset, vocabulary, parsed) -> dict:
    """An arm carries a dose, or stands beside one.

    Recurrence alone is not enough: a paper measuring pH in two tables makes "pH" recur
    exactly like an arm would.
    """
    arms, dosed, siblings = {}, set(), set()
    for columns in columns_per_asset:
        keyed = []
        for name in columns:
            key = canonical_key(name)
            if key not in parsed:
                parsed[key] = parse_treatment(name, vocabulary)
            keyed.append((key, parsed[key]))
        has_dose = any(arm.dosed for _, arm in keyed)
        for key, arm in keyed:
            arms.setdefault(key, arm)
            if arm.dosed:
                dosed.add(key)
            elif has_dose:
                siblings.add(key)
    return {key: arm for key, arm in arms.items() if key in dosed or key in siblings}


def build_treatment_lexicon(assets, vocabulary=None) -> dict:
    """The paper's arms, keyed by the label as printed.

    Plain headers first, then "PBC (log cfu/g) - Teo1%" unpacked using them — otherwise
    that reads as one arm per indicator, with the unit inside a substance name.
    """
    columns = [group for asset in assets for group in _candidate_columns(asset)]
    parsed: dict = {}
    lexicon = _collect_arms(
        [[name for name in group if not _has_separator(name)] for group in columns],
        vocabulary, parsed)
    lexicon.update(_collect_arms([
        [split_indicator_and_treatment(name, lexicon)[1] or name
         for name in group if _has_separator(name)]
        for group in columns], vocabulary, parsed))
    return lexicon


# ─── The paper's own facts ────────────────────────────────────────────────────

_CAPTION_PREFIX = re.compile(r"^\s*(?:fig(?:ure)?|table|scheme|chart)\s*\.?\s*\d+\s*[.:)-]*\s*",
                             re.IGNORECASE)


def _paper_texts(package):
    """Title, methods and captions, in document order."""
    for section in package.get("sections", []):
        where = f"section:{section['section_title']}"[:EVIDENCE_LABEL_CHARS]
        yield where, section["section_title"]
        yield where, section["content_markdown"][:_settings.SECTION_SCAN_CHARS]
    for asset in chain(package.get("tables", []), package.get("figures", [])):
        if asset.get("caption"):
            yield asset.get("docling_item_ref") or "caption", asset["caption"]


def resolve_matrix(package, vocabulary) -> dict:
    """The food the paper studied, from the first text that names one."""
    for where, text in _paper_texts(package):
        term = vocabulary.find_in(text, "matrix")
        if term:
            return {"name": term.name, "evidence": where}
    return {"name": None, "evidence": None}


def caption_indicator(caption, vocabulary) -> Optional[str]:
    term = vocabulary.find_in(_CAPTION_PREFIX.sub("", str(caption or "").strip()), "indicator")
    return term.name if term else None


def caption_is_discarded(caption, vocabulary) -> bool:
    """The whole asset measures something we do not keep.

    Only stands when nothing in the caption is a known indicator: "Changes in Hardness, pH,
    ... and APC" names both kinds, and dropping it would cost five columns to avoid one.
    """
    text = _CAPTION_PREFIX.sub("", str(caption or "").strip())
    if not vocabulary.names_a_discarded_quantity(text):
        return False
    return caption_indicator(text, vocabulary) is None


def context_indicator(context, vocabulary) -> Optional[str]:
    """For a captionless figure, and only when the surrounding text names exactly one
    known quantity: picking one of several would misattribute real numbers."""
    found = {term.name for term in vocabulary.names_in(context, "indicator")}
    return found.pop() if len(found) == 1 else None


# ─── Interpretation ───────────────────────────────────────────────────────────

@dataclass(slots=True)
class Measurement:
    """One resolved reading: what was measured, on which arm, at which point."""

    axis_value: float
    condition: Optional[str]
    arm_key: str
    indicator: str
    indicator_type: str
    unit: str
    threshold: Optional[float]
    value: float
    is_figure: bool
    item_ref: Optional[str]
    page_number: Optional[int]
    reports_mean: bool = False
    ingredients: list = field(default_factory=list)


def _assign_roles(observation, lexicon, indicator_columns, strategies) -> tuple:
    """Which label names the quantity and which names the arm."""
    column = observation.get("column_label")
    indicator_label = treatment_label = None
    if column:
        head, tail = split_indicator_and_treatment(column, lexicon)
        if tail is not None:
            indicator_label, treatment_label = head, tail
            strategies.add("indicator and arm packed into the column header")
        elif canonical_key(column) in lexicon:
            treatment_label = column
            strategies.add("value columns are arms")
        else:
            indicator_label = column
            strategies.add("value columns are indicators")
    for name, value in (observation.get("row_labels") or {}).items():
        if canonical_key(value) in lexicon or canonical_key(name) in lexicon:
            treatment_label = treatment_label or value
            strategies.add("row labels are arms")
        elif name in indicator_columns and indicator_label is None:
            indicator_label = value
            strategies.add("row labels name the indicator")
        elif treatment_label is None:
            treatment_label = value
            strategies.add("row labels qualify the arm")
    return indicator_label, treatment_label


def _asset_note(item_ref, caption, how, measurements=()) -> dict:
    """What one asset contributed — the per-asset half of the normalisation report."""
    return {
        "item_ref": item_ref,
        "caption": caption,
        "how": how,
        "indicators": sorted({item.indicator for item in measurements}),
        "conditions": sorted({item.condition for item in measurements if item.condition}),
        "arms": len({item.arm_key for item in measurements}),
    }


def _named_by_text(asset, vocabulary, caption_name, claimed) -> tuple:
    """The indicator the asset's own text names, and whether that came from prose rather
    than from the caption."""
    if caption_name is not None:
        return caption_name, False
    guess = context_indicator(asset.get("context_markdown"), vocabulary)
    if guess and canonical_key(guess) not in claimed:
        return guess, True
    return None, False


def interpret_asset(asset, lexicon, vocabulary, *, caption_name=None, claimed=()) -> tuple:
    gate = asset.get("gate") or {}
    observations = asset.get("observations", [])
    if caption_is_discarded(asset.get("caption"), vocabulary):
        name = _CAPTION_PREFIX.sub("", str(asset.get("caption")).strip())[:CAPTION_SUMMARY_CHARS]
        vocabulary.discarded[("indicator", name)] = len(observations)
        return [], _asset_note(
            asset.get("docling_item_ref"), name,
            ["discarded: caption names a sensory or gravimetric quantity"])

    caption_name, from_context = _named_by_text(asset, vocabulary, caption_name, claimed)
    labels = [str(name) for name in gate.get("label_columns", [])]
    indicator_columns = [name for name in labels if canonical_key(name) not in lexicon]
    is_figure = bool(asset.get("is_figure"))
    item_ref = asset.get("docling_item_ref")
    page_number = asset.get("page_number")
    caption_means = declares_mean(asset.get("caption"))
    measurements, strategies, dropped = [], set(), 0

    for observation in observations:
        indicator_label, treatment_label = _assign_roles(
            observation, lexicon, indicator_columns, strategies)
        if indicator_label is None and caption_name:
            indicator_label = caption_name
            strategies.add("indicator inferred from nearby text" if from_context
                           else "indicator taken from the caption")
        resolved = vocabulary.normalise_indicator(indicator_label)
        if resolved is None:
            dropped += 1
            continue
        arm = lexicon.get(canonical_key(treatment_label)) if treatment_label else None
        measurements.append(Measurement(
            axis_value=float(observation["axis_value"]),
            condition=arm.condition if arm else None,
            arm_key=arm.key if arm else canonical_key(treatment_label or "unspecified"),
            indicator=resolved["name"], indicator_type=resolved["indicator_type"],
            unit=resolved["unit"], threshold=resolved["threshold"],
            value=float(observation["value"]), is_figure=is_figure,
            item_ref=item_ref, page_number=page_number,
            reports_mean=bool(observation.get("reports_mean")) or caption_means,
            ingredients=arm.ingredients if arm else [],
        ))

    if dropped:
        strategies.add(f"{dropped} observations of discarded indicators dropped")
    return measurements, _asset_note(
        item_ref, (asset.get("caption") or "")[:EVIDENCE_LABEL_CHARS],
        sorted(strategies) or ["no labels to resolve"], measurements)


def interpret_paper(assets, lexicon, vocabulary) -> tuple:
    """Captions are read across the paper first: an indicator another figure claimed by
    caption is evidence against a captionless one guessing the same name from prose."""
    caption_names = [caption_indicator(asset.get("caption"), vocabulary) for asset in assets]
    claimed = {canonical_key(name) for name in caption_names if name}
    measurements, notes = [], []
    for asset, caption_name in zip(assets, caption_names):
        found, note = interpret_asset(asset, lexicon, vocabulary,
                                      caption_name=caption_name, claimed=claimed)
        measurements.extend(found)
        notes.append(note)
    return measurements, notes


# ─── Reference tables -> ingredients ──────────────────────────────────────────

_PROPORTION_UNITS = ("%", "peak area %", "area %", "w/w", "v/v", "g/100g")
_CATALOGUE_TOTALS = {"total", "sum", "others", "other", "unknown"}


def _column_is_numeric(rows, index) -> bool:
    """The same test the gate applies to a column, over raw rows rather than a fit."""
    filled = [row[index] for row in rows
              if index < len(row) and row[index] is not None and str(row[index]).strip()]
    if not filled:
        return False
    parsed = sum(parse_number(cell) is not None for cell in filled)
    return parsed / len(filled) >= MIN_NUMERIC_RATIO


def _proportion_unit(header, vocabulary) -> Optional[str]:
    """A unit, or nothing.

    The bracket at the end of a header is not always one: "Concentration (mean ± Stdev)"
    gave `concentration_unit = "mean ± Stdev"`.
    """
    _, unit = split_label_and_unit(header)
    candidate = vocabulary.canonical_unit(unit) if unit else None
    if candidate and canonical_key(candidate) in vocabulary.known_units():
        return candidate
    return next((token for token in _PROPORTION_UNITS
                 if token in str(header or "").lower()), None)


def ingredients_from_reference(asset, vocabulary) -> list:
    """A composition table's rows are substances, so they belong in `ingredients`.

    Only rows the vocabulary can name survive. The column group prefix
    ("TEO.Concentration") is kept as the preparation; `source` is the biological origin and
    comes from the vocabulary, never from the table.
    """
    headers = [str(name) for name in asset.get("headers", [])]
    rows = asset.get("rows") or []
    if not headers or not rows:
        return []
    numeric = [_column_is_numeric(rows, index) for index in range(len(headers))]
    name_columns = [index for index, flag in enumerate(numeric) if not flag]
    amount_columns = [index for index, name in enumerate(headers)
                      if numeric[index]
                      and any(token in name.lower() for token in _PROPORTION_UNITS)]
    caption = asset.get("caption")
    item_ref = asset.get("docling_item_ref")
    found = []
    for name_index in name_columns:
        header = headers[name_index]
        prefix = header.split(".")[0].strip() if "." in header else None
        partner = next((index for index in amount_columns
                        if prefix and headers[index].startswith(prefix + ".")),
                       amount_columns[0] if amount_columns else None)
        unit = _proportion_unit(headers[partner], vocabulary) if partner is not None else None
        preparation = prefix or caption or "composition table"
        for row in rows:
            raw = str(row[name_index] or "").strip() if name_index < len(row) else ""
            if not raw or canonical_key(raw) in _CATALOGUE_TOTALS:
                continue
            resolved = vocabulary.normalise_ingredient(raw)
            if resolved is None:
                continue
            found.append({
                **resolved,
                "preparation": preparation,
                "amount": (parse_number(row[partner])
                           if partner is not None and partner < len(row) else None),
                "unit": unit,
                "item_ref": item_ref,
            })
    return found


# ─── Entry point ──────────────────────────────────────────────────────────────

def normalise(package: dict, vocabulary=None) -> dict:
    """Resolve one gated package in place, and return its reading.

    Everything is decided here — the matrix, the arms and their concentrations, the
    indicator names, types and units, every ingredient's class and origin.
    """
    vocabulary = vocabulary or build_vocabulary()
    assets = package.get("tables", []) + package.get("figures", [])
    lexicon = build_treatment_lexicon(assets, vocabulary)
    measurements, notes = interpret_paper(assets, lexicon, vocabulary)
    reading = {
        "matrix": resolve_matrix(package, vocabulary),
        "catalogue": [item for reference in package.get("references", [])
                      for item in ingredients_from_reference(reference, vocabulary)],
        "lexicon": lexicon,
        "measurements": measurements,
        "notes": notes,
        "vocabulary_review": vocabulary.review(),
    }
    package["reading"] = reading
    return reading
