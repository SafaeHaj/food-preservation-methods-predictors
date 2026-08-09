from __future__ import annotations

import re
import unicodedata
from collections import Counter

import pandas as pd

from raw_sources import (
    Arm, RawIngredient, first_number, load_all, load_yaml, parse_grams, parse_minutes,
    parse_temperature, report, resolve_indicator, write_outputs,
)

PERCENT_TO_PPM = 10000

VOCABULARY = load_yaml("vocabulary.yaml")
REFERENCE = load_yaml("reference.yaml")
TREATMENTS = VOCABULARY["treatments"]
SCHEMA = VOCABULARY["schema"]
MOLECULAR_FIELDS = ("molecular_weight", "logp", "pka", "hbd_count", "hba_count")
INGREDIENT_SLOTS = SCHEMA["ingredient_slots"]
OVERRIDE_FACTOR = VOCABULARY["units"]["normalized_override_factor"]
INITIAL_COLUMNS = tuple(
    f"initial_{entry['canonical']}" for entry in VOCABULARY["indicators"].values()
)


def canonical_unit(raw: str | None) -> str | None:
    if not raw:
        return None
    folded = unicodedata.normalize("NFKD", raw).lower().strip()
    folded = folded.replace("μ", "u").replace("µ", "u")
    return re.sub(r"\s+(?:of\s+)?meat$", "", folded)


UNIT_ALIASES = {
    canonical_unit(k): canonical_unit(v) for k, v in VOCABULARY["units"]["aliases"].items()
}
PPM_FACTORS = {canonical_unit(k): v for k, v in VOCABULARY["units"]["ppm_factors"].items()}

INGREDIENT_INDEX = {
    alias: {"canonical_name": name, **entry}
    for name, entry in REFERENCE["ingredients"].items()
    for alias in entry["aliases"]
}
ALIASES_BY_LENGTH = sorted(INGREDIENT_INDEX, key=len, reverse=True)


def resolve_ingredient(name: str) -> dict | None:
    if name in INGREDIENT_INDEX:
        return INGREDIENT_INDEX[name]
    for alias in ALIASES_BY_LENGTH:
        if alias in name:
            return INGREDIENT_INDEX[alias]
    return None


def to_ppm(item: RawIngredient) -> tuple[float | None, str | None]:
    unit = canonical_unit(item.unit)
    factor = PPM_FACTORS.get(UNIT_ALIASES.get(unit, unit))
    from_unit = item.concentration * factor if factor and item.concentration is not None else None
    from_normalized = (
        item.normalized_percent * PERCENT_TO_PPM if item.normalized_percent is not None else None
    )

    if from_unit is None:
        return from_normalized, None if from_normalized is None else "normalized"
    if from_normalized and max(from_unit, from_normalized) > OVERRIDE_FACTOR * min(
        from_unit, from_normalized
    ):
        return from_normalized, "normalized_override"
    return from_unit, "unit"


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def best_match(text: str, patterns: dict, order: list) -> str | None:
    scores = Counter({
        label: sum(1 for pattern in keywords if pattern in text)
        for label, keywords in patterns.items()
    })
    return max(
        (label for label in order if scores[label]),
        key=lambda label: (scores[label], -order.index(label)),
        default=None,
    )


def classify_treatment(text: str) -> str | None:
    return best_match(text, TREATMENTS["patterns"], TREATMENTS["types"])


def classify_atmosphere(text: str | None) -> str | None:
    for atmosphere, keywords in VOCABULARY["packaging"]["atmosphere"].items():
        if any(re.search(rf"\b{keyword}\b", text or "") for keyword in keywords):
            return atmosphere
    return None


def classify_application(text: str, immersed: bool) -> str:
    matched = best_match(
        text, TREATMENTS["application_patterns"], TREATMENTS["application_methods"]
    )
    if matched:
        return matched
    return "Immersed" if immersed else TREATMENTS["unspecified_application"]


def dosed_ingredients(arm: Arm) -> list[dict]:
    rows = []
    for item in arm.ingredients:
        concentration_ppm, basis = to_ppm(item)
        entry = resolve_ingredient(item.name) or {}
        rows.append({
            "arm_id": arm.arm_id,
            "raw_name": item.name,
            "ingredient_name": entry.get("canonical_name") or item.name,
            "concentration_ppm": concentration_ppm,
            "conversion_basis": basis,
            "functional_class": entry.get("functional_class", SCHEMA["unclassified_class"]),
            "source": entry.get("source_category", SCHEMA["unknown_source"]),
            **{field: entry.get(field) for field in MOLECULAR_FIELDS},
        })
    return rows


def ingredient_slots(rows: list[dict]) -> dict:
    slots = {}
    for index in range(1, INGREDIENT_SLOTS + 1):
        row = rows[index - 1] if index <= len(rows) else {}
        slots[f"ingredient_{index}_name"] = row.get("ingredient_name")
        slots[f"ingredient_{index}_functional_class"] = row.get("functional_class")
        slots[f"ingredient_{index}_source"] = row.get("source")
        slots[f"ingredient_{index}_concentration_ppm"] = row.get("concentration_ppm")
    return slots


def weighted_mean(values: list[tuple[float, float]]) -> float | None:
    total = sum(weight for _, weight in values)
    if not values or total == 0:
        return None
    return sum(value * weight for value, weight in values) / total


def property_features(rows: list[dict]) -> dict:
    dosed = [row for row in rows if row["concentration_ppm"]]
    total_dose = sum(row["concentration_ppm"] for row in dosed)
    known = [row for row in dosed if row["molecular_weight"] is not None]

    def pairs(field: str) -> list[tuple[float, float]]:
        return [
            (row[field], row["concentration_ppm"])
            for row in known if row.get(field) is not None
        ]

    def maximum(field: str) -> float | None:
        values = [row[field] for row in known if row.get(field) is not None]
        return max(values) if values else None

    def total(field: str) -> float | None:
        values = [row[field] for row in known if row.get(field) is not None]
        return sum(values) if values else None

    features = {
        "total_dose_ppm": total_dose,
        "logp_wmean": weighted_mean(pairs("logp")),
        "pka_wmean": weighted_mean(pairs("pka")),
        "mw_wmean": weighted_mean(pairs("molecular_weight")),
        "mw_max": maximum("molecular_weight"),
        "logp_max": maximum("logp"),
        "hbd_total": total("hbd_count"),
        "hba_total": total("hba_count"),
        "property_coverage": (
            sum(row["concentration_ppm"] for row in known) / total_dose if total_dose else 0.0
        ),
    }
    for row in dosed:
        if row["functional_class"]:
            key = f"dose_{slug(row['functional_class'])}_ppm"
            features[key] = features.get(key, 0.0) + row["concentration_ppm"]
    return features


def arm_features(arm: Arm, rows: list[dict]) -> dict:
    matrix = REFERENCE["matrices"].get(arm.matrix_label, {})
    context = " ".join(
        part for part in (arm.treatment_text, arm.immersion_text, arm.packaging_text) if part
    )
    applied = " ".join([arm.treatment_text, *(item.name for item in arm.ingredients)])
    immersion_time_min = parse_minutes(arm.immersion_text)
    features = {
        "study_id": arm.study_id,
        "arm_id": arm.arm_id,
        "meat_matrix": arm.matrix_label,
        "matrix_moisture_percent": matrix.get("moisture_percent"),
        "matrix_protein_percent": matrix.get("protein_percent"),
        "matrix_fat_percent": matrix.get("fat_percent"),
        "matrix_salt_percent": matrix.get("salt_percent"),
        "matrix_ph": matrix.get("ph"),
        "matrix_water_activity": matrix.get("water_activity"),
        "weight_g": parse_grams(arm.part_of_product),
        "treatment_type": classify_treatment(applied),
        "application_method": classify_application(context, immersion_time_min is not None),
        "thermal_temperature_c": first_number(arm.treatment_text, r"(\d+(?:\.\d+)?)\s*°?\s*c\b"),
        "thermal_duration_min": first_number(arm.treatment_text, r"(\d+(?:\.\d+)?)\s*min"),
        "irradiation_dose_kgy": first_number(arm.treatment_text, r"irradiation\s*(\d+(?:\.\d+)?)"),
        "packaging_atmosphere": classify_atmosphere(arm.packaging_text),
        "storage_temperature_c": parse_temperature(arm.storage_text),
        "immersion_time_min": immersion_time_min,
    }
    features.update(ingredient_slots(rows))
    features.update(property_features(rows))
    return features


def build() -> tuple[pd.DataFrame, pd.DataFrame]:
    arms, observations = load_all()
    ingredient_rows = {arm_id: dosed_ingredients(arm) for arm_id, arm in arms.items()}
    features = {
        arm_id: arm_features(arm, ingredient_rows[arm_id]) for arm_id, arm in arms.items()
    }

    canonical = {
        observation.indicator_label: resolve_indicator(observation.indicator_label, VOCABULARY)
        or {"canonical": observation.indicator_label, "type": observation.indicator_type}
        for observation in observations
    }
    initials: dict[str, dict] = {}
    for observation in observations:
        name = canonical[observation.indicator_label]["canonical"]
        initials.setdefault(observation.arm_id, {})[f"initial_{name}"] = observation.initial_count

    table = pd.DataFrame([
        {
            **features[observation.arm_id],
            **{column: initials[observation.arm_id].get(column) for column in INITIAL_COLUMNS},
            "indicator_name": canonical[observation.indicator_label]["canonical"],
            "indicator_type": canonical[observation.indicator_label]["type"],
            "indicator_unit": observation.indicator_unit,
            "indicator_threshold": observation.upper_threshold,
            "initial_fraction_of_threshold": (
                observation.initial_count / observation.upper_threshold
                if observation.initial_count is not None and observation.upper_threshold
                else None
            ),
            "shelf_life_days": observation.shelf_life_days,
            "crossed": int(observation.shelf_life_days is not None),
        }
        for observation in observations
    ])
    dose_columns = [column for column in table.columns if column.startswith("dose_")]
    table[dose_columns] = table[dose_columns].fillna(0.0)

    ingredients = pd.DataFrame([row for rows in ingredient_rows.values() for row in rows])
    return table, ingredients


if __name__ == "__main__":
    table, ingredients = build()
    write_outputs(table, ingredients, "modified")
    basis = ingredients["conversion_basis"]
    unclassified = ingredients["functional_class"] == SCHEMA["unclassified_class"]
    report("modified", table, {
        "columns": table.shape[1],
        "dose classes": len([c for c in table.columns if c.startswith("dose_")]),
        "functional classes in closed set": set(ingredients["functional_class"])
        <= set(SCHEMA["functional_classes"] + [SCHEMA["unclassified_class"]]),
        "sources in closed set": set(ingredients["source"])
        <= set(SCHEMA["ingredient_sources"] + [SCHEMA["unknown_source"]]),
        "doses by basis": basis.value_counts(dropna=False).to_dict(),
        "doses overridden by normalized percent": sorted(
            ingredients.loc[basis == "normalized_override", "raw_name"].unique()
        ),
        "mean property coverage": round(table["property_coverage"].mean(), 3),
        "day-0 columns": f"{len(INITIAL_COLUMNS)}, each in one indicator's unit",
        "rows already spoiled at day 0": int(
            (table["initial_fraction_of_threshold"] >= 1).sum()
        ),
        "rows with no physical treatment": int(table["treatment_type"].isna().sum()),
        "treatment types found": sorted(table["treatment_type"].dropna().unique()),
        "unspecified application rows": int(
            (table["application_method"] == TREATMENTS["unspecified_application"]).sum()
        ),
        "matrix composition": "reference-derived for every row; no source reports a measured value",
        "unclassified ingredients": sorted(ingredients.loc[unclassified, "raw_name"].unique()),
    })
