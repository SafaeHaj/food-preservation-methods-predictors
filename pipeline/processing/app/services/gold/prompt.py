"""What the model is asked, and how the question is made to fit.

The prompt shows the arms the gate already assembled, what the pipeline has already
established, and the methods prose — and asks for exactly two fields back. It deliberately
does **not** show the values: one paper sent 480 observations across 11 assets, about 70%
of a prompt that then did not fit the context window, to answer a question about prose.

`fit_to_budget` is the ladder that shrinks an over-budget prompt in the order that costs
the answer least: asset detail first, then other sections, then the methods themselves —
which are the one thing the question is actually about, so they go last and never below a
floor where they stop being readable.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Callable, Optional

from shared.config import get_processing_settings
from shared.schemas.science import APPLICATION_METHODS, GoldBundle, TREATMENT_TYPES

logger = logging.getLogger(__name__)
_settings = get_processing_settings()

#: A methods section is the point of the prompt, so it gets room; everything else is
#: context and is trimmed hard from the start.
MAX_METHODS_SECTION_CHARS = 12000
MAX_OTHER_SECTION_CHARS = 800
#: Below this the methods stop being a procedure and become a fragment; the ladder drops
#: whole sections rather than shredding them past this point.
MIN_METHODS_SECTION_CHARS = 600
MAX_METHODS_FIT_PASSES = 4
MAX_RESOLVED_VALUES = 12

_TEMPERATURE_C = re.compile(r"(-?\d{1,3}(?:[.,]\d+)?)\s*(?:°|º|\bdeg(?:rees)?\.?\s*)\s*C\b",
                            re.IGNORECASE)
_DURATION_DAYS = re.compile(r"\b(\d{1,3})\s*(?:d|days?)\b(?!\s*[-–]?\s*\d)", re.IGNORECASE)


GOLD_SYSTEM_PROMPT = """\
You extract protocol metadata from the METHODS section of a food-science paper.

Each experiment arm is already resolved with matrix, ingredients, concentrations,
indicators, and measurements. Do not repeat those fields.

`resolved` holds what the software has already established: the matrix, how many arms
there are, the storage days measured, the indicators, and every temperature and duration
stated in the METHODS. Treat those as given. Do not re-derive them, do not contradict
them, and do not spend reasoning on establishing them again.

Extract:
- treatment_description for every experiment arm
- treatment_type and application_method, chosen from the closed lists below
- sample_weight_g and storage_temperature_c for every experiment arm
- evidence supporting each field

## treatment_description

Extract what the Methods say was **done to the food sample and how it was stored**.

Use only the Preparation / Materials and Methods section. Use the paper's own terms and keep the same order as the paper. Do not invent, reorganize, or label the procedure.

Include:

* sample preparation or handling
* processing or physical treatment
* packaging
* storage conditions or location
* storage duration
* sampling during storage

### Where to put it

**Shared procedure:**
If the same procedure was done to **all arms**, put it in `protocol`. Set every arm's `treatment_description` to `null`.

**Arm-specific procedure:**
If a procedure was done to **only one arm**, put it in that arm's `treatment_description`.

**No procedure:**
Use `null` only if the Methods describe **no sample handling or storage at all**. Storage alone is not `null`; describe the storage.

### Exclude

Do not include:

* ingredient names
* concentrations, doses, or percentages
* arm/group names
* comparisons between groups

Describe **what was done**, not which group received which treatment.

GOOD:
"Fillets were washed, drained and portioned, dipped twice in the coating dispersion for 120 s, packed in polystyrene trays overwrapped with PVC film, and stored at 4 °C for 15 days."

BAD:
"Samples received 0%, 1% and 2% thyme oil coatings."

## treatment_type and application_method

Both are closed lists. Choose exactly one value, copied character-for-character. If none
fits, choose the last value in the list — do not invent a value and do not return a value
that is merely similar to one of these.

treatment_type — the physical process the FOOD went through. `null` if the Methods
describe no physical treatment; most arms in this corpus had none, and `null` is the
honest answer, not the sink value.

{treatment_types}

application_method — how the ADDITIVES were applied to the food.

{application_methods}

When a treatment is thermal, also return `thermal_temperature_c` and
`thermal_duration_min` for that treatment step only. Storage temperature is not a thermal
treatment: it belongs in `storage_temperature_c`.

## sample_weight_g

Return the mass in grams of ONE experimental sample unit.

Priority:
1. directly stated by the paper
2. calculated from explicit values in the paper
3. inferred from explicit contextual information in the paper
4. null

Inference is allowed only when the paper provides enough information to support it.

Allowed examples:
- batch mass and number of samples are stated
- dimensions and density are stated
- preparation details constrain the mass

Do not infer from:
- typical food sizes
- external knowledge
- other papers
- unstated assumptions

For inferred values, explain the reasoning in evidence and mark:
"method": "inferred"

## evidence

Provide evidence for every field, including null values.

Each evidence object:

{
  "field_name": "treatment_description" | "sample_weight_g" | "treatment_type",
  "docling_item_ref": REQUIRED, and copied from `valid_docling_item_refs`,
  "page_number": integer | null,
  "source_type": "prose" | "table" | "figure",
  "source_label": string | null,
  "exact_text": REQUIRED for stated prose evidence,
  "method": "stated" | "derived" | "inferred",
  "rationale": REQUIRED for derived or inferred values
}

## the reply

"protocol" is the handling every arm went through, and is where the answer belongs when
the METHODS describe one procedure for all groups. "experimental_groups" is how many
groups the METHODS define, which may differ from the number of arms listed below.

Return exactly one "experiments" object per experiment_index provided.

Return ONLY valid JSON:

{
  "protocol": "..." | null,
  "experimental_groups": integer | null,
  "evidence": [ ... supporting "protocol", with "field_name": "treatment_description" ... ],
  "experiments": [
    {
      "experiment_index": 0,
      "treatment_description": "..." | null,
      "treatment_type": "..." | null,
      "application_method": "..." | null,
      "thermal_temperature_c": 121.0 | null,
      "thermal_duration_min": 15.0 | null,
      "sample_weight_g": 25.0 | null,
      "storage_temperature_c": 4.0 | null,
      "evidence": [...]
    }
  ]
}
"""


def _closed_list(values) -> str:
    return "\n".join(f"- {value}" for value in values)


# Substituted rather than `.format()`ed: the prompt is full of literal JSON braces, and
# every one of them would have to be doubled to survive a format call.
GOLD_SYSTEM_PROMPT = (
    GOLD_SYSTEM_PROMPT
    .replace("{treatment_types}", _closed_list(TREATMENT_TYPES))
    .replace("{application_methods}", _closed_list(APPLICATION_METHODS))
)


# ─── The parts ────────────────────────────────────────────────────────────────

def build_asset_prompt(asset: dict, kind: str) -> dict:
    """What the model is told an asset is, never what is in it.

    The reply carries `treatment` and `weight_g` out of methods prose and nothing else, so
    the values themselves are dead weight here. What is left is enough to cite the asset
    and to know what it measured.
    """
    gate = asset.get("gate", {})
    return {
        "kind": kind, "docling_item_ref": asset.get("docling_item_ref"),
        "page_number": asset.get("page_number"), "caption": asset.get("caption"),
        "section_hint": asset.get("section_hint"), "axis_label": gate.get("axis_label"),
        "axis_points": gate.get("axis_points"), "value_columns": gate.get("value_columns"),
        "label_columns": gate.get("label_columns"), "orientation": gate.get("orientation"),
        "values_are_approximate": kind == "figure",
        "observation_count": len(asset.get("observations", [])),
        "nearby_text": (asset.get("context_markdown") or "")[:_settings.FIGURE_CONTEXT_CHARS],
    }


def _section_prompt(package: dict) -> tuple:
    methods_refs = set(package.get("methods_refs") or ())
    shown, methods_count = [], 0
    for section in package.get("sections", []):
        is_methods = section.get("docling_item_ref") in methods_refs
        methods_count += is_methods
        budget = MAX_METHODS_SECTION_CHARS if is_methods else MAX_OTHER_SECTION_CHARS
        shown.append({"docling_item_ref": section.get("docling_item_ref"),
                      "section_title": section["section_title"],
                      "page_number": section.get("page_number"),
                      "is_methods": is_methods,
                      "content_markdown": section["content_markdown"][:budget]})
    return shown, methods_count


def _methods_prose(package: dict) -> str:
    refs = set(package.get("methods_refs") or ())
    sections = package.get("sections", [])
    chosen = [section for section in sections
              if section.get("docling_item_ref") in refs] or sections
    return "\n".join(section.get("content_markdown", "") for section in chosen)


def _numbers_in(pattern, text) -> list:
    found = set()
    for match in pattern.finditer(text):
        try:
            found.add(float(match.group(1).replace(",", ".")))
        except ValueError:
            continue
    return sorted(found)[:MAX_RESOLVED_VALUES]


def resolved_facts(package: dict, bundle: GoldBundle) -> dict:
    """What the pipeline already knows, handed over as settled rather than left to be
    inferred: the matrix and the arms from the vocabulary, the storage days and indicators
    from the gated tables, the temperatures and durations from the methods."""
    methods = _methods_prose(package)
    measured = [record for record in bundle.experiments if record.measurements]
    return {
        "matrix_name": bundle.experiments[0].matrix_name if bundle.experiments else None,
        "arms_total": len(bundle.experiments),
        "arms_measured": len(measured),
        "storage_days": sorted({item.day for record in measured
                                for item in record.measurements}),
        "indicators": sorted({f"{item.indicator_name} ({item.indicator_unit})"
                              for record in measured for item in record.indicators}),
        "temperatures_c_stated_in_methods": _numbers_in(_TEMPERATURE_C, methods),
        "durations_days_stated_in_methods": _numbers_in(_DURATION_DAYS, methods),
    }


def arm_prompt(bundle: GoldBundle) -> list:
    """The arms as the model sees them, each under the index that joins its reply back.

    Doses are shown so it can tell them apart, not so it can return them.
    """
    return [{
        "experiment_index": index,
        "matrix_name": record.matrix_name,
        "ingredients": [{"ingredient_name": link.ingredient_name,
                         "concentration": link.concentration,
                         "concentration_unit": link.concentration_unit}
                        for link in record.experiment_ingredients],
        "days": sorted({item.day for item in record.measurements}),
        "indicators": sorted({item.indicator_name for item in record.measurements}),
    } for index, record in enumerate(bundle.experiments)]


def build_payload(package: dict, bundle: GoldBundle) -> dict:
    """Everything the user message carries, before it is fitted to a budget."""
    sections, methods_count = _section_prompt(package)
    assets = (
        [build_asset_prompt(asset, "table") for asset in package.get("tables", [])]
        + [build_asset_prompt(asset, "figure") for asset in package.get("figures", [])]
        + [build_asset_prompt(asset, "reference table")
           for asset in package.get("references", [])]
    )
    return {
        "paper_slug": package["paper_slug"],
        "resolved": resolved_facts(package, bundle),
        "methods_sections_found": methods_count,
        "sections": sections,
        "assets": assets,
        "experiments": arm_prompt(bundle),
        "valid_docling_item_refs": sorted(
            {section["docling_item_ref"] for section in sections
             if section.get("docling_item_ref")}
            | {asset["docling_item_ref"] for asset in assets
               if asset.get("docling_item_ref")}
        ),
    }


# ─── Fitting it to the window ─────────────────────────────────────────────────

def serialise(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def _trim_asset_context(payload: dict, factor: float) -> None:
    for asset in payload.get("assets", []):
        text = asset.get("nearby_text") or ""
        asset["nearby_text"] = text[:max(0, int(len(text) * factor))]


def _trim_other_sections(payload: dict, factor: float) -> None:
    for section in payload.get("sections", []):
        if section.get("is_methods"):
            continue
        text = section.get("content_markdown") or ""
        section["content_markdown"] = text[:max(0, int(len(text) * factor))]


def _drop_asset_context(payload: dict) -> None:
    for asset in payload.get("assets", []):
        asset.pop("nearby_text", None)


def _drop_reference_tables(payload: dict) -> None:
    payload["assets"] = [asset for asset in payload.get("assets", [])
                         if asset.get("kind") != "reference table"]


def _drop_other_sections(payload: dict) -> None:
    payload["sections"] = [section for section in payload.get("sections", [])
                           if section.get("is_methods")]


def _drop_asset_detail(payload: dict) -> None:
    payload["assets"] = [
        {key: asset[key] for key in ("kind", "docling_item_ref", "caption", "page_number")
         if key in asset}
        for asset in payload.get("assets", [])
    ]


#: In order of what each costs the answer. Asset context and non-methods prose are
#: background; the methods are the question, so they are the last thing touched.
TRIM_LADDER: tuple[Callable[[dict], None], ...] = (
    lambda payload: _trim_asset_context(payload, 0.5),
    lambda payload: _trim_other_sections(payload, 0.5),
    _drop_asset_context,
    _drop_reference_tables,
    _drop_other_sections,
    _drop_asset_detail,
)

PROMPT_LAST_RESORT = (
    "The methods prose alone exceeded the budget and was truncated; the reply may be "
    "based on an incomplete procedure."
)


def _fit_methods_to_budget(payload: dict, budget: int) -> str:
    """Shrink the methods sections themselves, proportionally, down to a floor.

    Only reached when everything else has already gone. Sections are trimmed together
    rather than one at a time so a paper with three methods subsections does not lose the
    third entirely while the first keeps its full length.
    """
    for _ in range(MAX_METHODS_FIT_PASSES):
        text = serialise(payload)
        if len(text) <= budget:
            return text
        methods = [section for section in payload.get("sections", [])
                   if section.get("is_methods")]
        if not methods:
            return text
        longest = max(len(section["content_markdown"]) for section in methods)
        if longest <= MIN_METHODS_SECTION_CHARS:
            payload["note"] = PROMPT_LAST_RESORT
            return serialise(payload)[:budget]
        target = max(MIN_METHODS_SECTION_CHARS, int(longest * 0.6))
        for section in methods:
            section["content_markdown"] = section["content_markdown"][:target]
    return serialise(payload)[:budget]


def fit_to_budget(payload: dict, budget: int) -> str:
    """The user message, at or under `budget` characters.

    Mutates `payload`, which the caller owns and rebuilds for a retry.
    """
    text = serialise(payload)
    if len(text) <= budget:
        return text

    for rung in TRIM_LADDER:
        rung(payload)
        text = serialise(payload)
        if len(text) <= budget:
            logger.info("Prompt fitted to %d chars after %s", len(text), rung)
            return text

    return _fit_methods_to_budget(payload, budget)
