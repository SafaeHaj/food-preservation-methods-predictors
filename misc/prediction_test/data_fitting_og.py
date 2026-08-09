from __future__ import annotations

import re

import pandas as pd
from rapidfuzz import fuzz, process

from raw_sources import (
    Arm, INGREDIENT_BLOCKS, load_all, load_yaml, parse_minutes, parse_temperature, report,
    write_outputs,
)

FUZZY_THRESHOLD = 92

INGREDIENT_METADATA = {
    "chlorine dioxide": ("mineral", "other natural sources"),
    "so2": ("mineral", "other natural sources"),
    "sodium benzoate": ("organic acid", "other natural sources"),
    "sodium ascorbate": ("organic acid", "plant"),
    "sodium chloride": ("mineral", "other natural sources"),
    "bha/bht": ("organic compound (antioxidant)", "other natural sources"),
    "activin": ("polyphenol", "plant"),
    "bha": ("organic compound (antioxidant)", "other natural sources"),
    "pycnogenol": ("polyphenol", "plant"),
    "rosemary": ("essential oil / polyphenol", "plant"),
    "roremary": ("essential oil / polyphenol", "plant"),
    "stpp": ("mineral", "other natural sources"),
    "tocopherol": ("vitamin", "plant"),
    "bht": ("organic compound (antioxidant)", "other natural sources"),
    "sodium erythorbate": ("organic acid", "microbial"),
    "nitrate": ("mineral", "other natural sources"),
    "edta": ("chelating agent (organic compound)", "other natural sources"),
    "thyme": ("essential oil", "plant"),
    "turmeric oil": ("essential oil", "plant"),
    "tumeric oil": ("essential oil", "plant"),
    "texturized soy": ("protein", "plant"),
    "texturized soya": ("protein", "plant"),
    "pea fi": ("fiber", "plant"),
    "lysozyme": ("protein", "enzyme"),
    "nisin": ("protein", "microbial"),
    "carvacrol": ("phenol", "plant"),
    "thymol": ("phenol", "plant"),
    "oregano": ("essential oil", "plant"),
    "organo": ("essential oil", "plant"),
    "control": ("none", "none"),
    "no ingredient": ("none", "none"),
}

VOCABULARY = load_yaml("vocabulary.yaml")
PACKAGING = VOCABULARY["packaging"]
TREATMENTS = VOCABULARY["og_treatments"]


def normalize_packaging_text(raw: str | None) -> str:
    if not raw:
        return ""
    cleaned = raw
    for wrong, right in PACKAGING["ocr_corrections"].items():
        cleaned = cleaned.replace(wrong, right)
    cleaned = re.sub(r"[/()\[\],]", " ", cleaned)
    cleaned = re.sub(r"\s*-\s*", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _ngrams(text: str, size: int) -> list[str]:
    tokens = text.split()
    return [" ".join(tokens[i:i + size]) for i in range(len(tokens) - size + 1)]


def match_ontology(text: str, ontology: dict, multi: bool = False) -> list[str]:
    keyword_to_label = {
        keyword: label for label, keywords in ontology.items() for keyword in keywords
    }
    matched = list(dict.fromkeys(
        label for keyword, label in keyword_to_label.items()
        if re.search(rf"\b{re.escape(keyword)}\b", text)
    ))

    if not matched:
        for keyword, label in keyword_to_label.items():
            candidates = _ngrams(text, len(keyword.split()))
            hit = process.extractOne(keyword, candidates, scorer=fuzz.WRatio)
            if hit and hit[1] >= FUZZY_THRESHOLD:
                matched.append(label)
        matched = list(dict.fromkeys(matched))

    return matched if multi else matched[:1]


def classify_packaging(raw: str | None) -> dict:
    text = normalize_packaging_text(raw)
    atmosphere = match_ontology(text, PACKAGING["atmosphere"])
    materials = match_ontology(text, PACKAGING["material"], multi=True)
    container = match_ontology(text, PACKAGING["container"])
    specials = match_ontology(text, PACKAGING["special"], multi=True)

    packaging_class = None
    if atmosphere:
        packaging_class = (
            "Active_Antimicrobial" if "Active packaging" in specials else atmosphere[0]
        )

    return {
        "packaging_class": packaging_class,
        "packaging_material": "|".join(materials) or None,
        "container_type": container[0] if container else None,
        "special_properties": "|".join(specials) or None,
    }


def decompose_treatment(text: str) -> dict:
    tokens = {
        token for token, patterns in TREATMENTS["patterns"].items()
        if any(re.search(pattern, text) for pattern in patterns)
    }
    dose = None
    match = re.search(r"irradiation\s*(\d+)", text)
    if match:
        tokens.add("irradiation")
        dose = int(match.group(1))

    physical = sorted(
        TREATMENTS["physical_hurdle"][token]
        for token in tokens if token in TREATMENTS["physical_hurdle"]
    )
    application = sorted(
        TREATMENTS["application"][token]
        for token in tokens if token in TREATMENTS["application"]
    )
    coordination = None if not tokens else ("Single" if len(tokens) == 1 else "Hybrid_Simultaneous")

    return {
        "physical_hurdle_tech": "+".join(physical) or None,
        "application_method": "+".join(application) or None,
        "hurdle_coordination": coordination,
        "irradiation_dose": dose,
    }


def fill_ingredient_metadata(name: str, chemical: str | None, source: str | None) -> tuple:
    for key, (known_chemical, known_source) in INGREDIENT_METADATA.items():
        if key in name:
            return chemical or known_chemical, source or known_source
    return chemical, source


def arm_features(arm: Arm) -> dict:
    features = {
        "study_id": arm.study_id,
        "arm_id": arm.arm_id,
        "data_source": "theoretical" if arm.origin == "meat" else "experimental",
        "meat_type": arm.matrix_label,
        "part_of_product": arm.part_of_product,
        "storage_temperature": parse_temperature(arm.storage_text),
        "immersion_time": parse_minutes(arm.immersion_text),
    }
    features.update(classify_packaging(arm.packaging_text))
    features.update(decompose_treatment(arm.treatment_text))

    for slot in range(1, INGREDIENT_BLOCKS + 1):
        item = arm.ingredients[slot - 1] if slot <= len(arm.ingredients) else None
        chemical, source = (
            fill_ingredient_metadata(item.name, item.chemical_composition, item.source_category)
            if item else (None, None)
        )
        features[f"ingredient_{slot}"] = item.name if item else None
        features[f"concentration_{slot}"] = item.concentration if item else None
        features[f"unit_of_concentration_{slot}"] = item.unit if item else None
        features[f"normalized_concentration_{slot}"] = item.normalized_percent if item else None
        features[f"chemical_composition_{slot}"] = chemical
        features[f"source_{slot}"] = source
    return features


def ingredient_rows(arm: Arm) -> list[dict]:
    rows = []
    for slot, item in enumerate(arm.ingredients, start=1):
        chemical, source = fill_ingredient_metadata(
            item.name, item.chemical_composition, item.source_category
        )
        rows.append({
            "arm_id": arm.arm_id,
            "slot": slot,
            "name": item.name,
            "concentration": item.concentration,
            "unit": item.unit,
            "normalized_percent": item.normalized_percent,
            "chemical_composition": chemical,
            "source_category": source,
        })
    return rows


def build() -> tuple[pd.DataFrame, pd.DataFrame]:
    arms, observations = load_all()
    features = {arm_id: arm_features(arm) for arm_id, arm in arms.items()}

    table = pd.DataFrame([
        {
            **features[observation.arm_id],
            "indicator": observation.indicator_label,
            "type_of_indicator": observation.indicator_type,
            "indicator_unit": observation.indicator_unit,
            "lower_threshold": observation.lower_threshold,
            "upper_threshold": observation.upper_threshold,
            "initial_count_day_0": observation.initial_count,
            "shelf_life_days": observation.shelf_life_days,
            "crossed": int(observation.shelf_life_days is not None),
        }
        for observation in observations
    ])

    ingredients = pd.DataFrame(
        [row for arm in arms.values() for row in ingredient_rows(arm)]
    )
    return table, ingredients


if __name__ == "__main__":
    table, ingredients = build()
    write_outputs(table, ingredients, "og")
    unresolved_packaging = table["packaging_class"].isna().sum()
    report("og", table, {
        "columns": table.shape[1],
        "ingredient rows": len(ingredients),
        "rows without packaging_class": unresolved_packaging,
        "rows without treatment axis": int(table["hurdle_coordination"].isna().sum()),
        "rows without storage temperature": int(table["storage_temperature"].isna().sum()),
        "chemical_composition still missing": int(ingredients["chemical_composition"].isna().sum()),
    })
