from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

ROOM_TEMPERATURE_C = 25.0

HERE = Path(__file__).parent
RAW_DIR = HERE.parent.parent / "data" / "raw"
OUTPUT_DIR = HERE / "data"

MEAT_CSV = RAW_DIR / "meat_shelf_life.csv"
SHRIMP_CSV = RAW_DIR / "shrimp_shelf_life.csv"

INGREDIENT_BLOCKS = 4
BLOCK_WIDTH = 6
BLOCK_START = 1

META = {
    "immersion": 25,
    "packaging": 26,
    "storage": 27,
    "matrix": 28,
    "part": 30,
    "treatment": 31,
    "combined_treatment": 32,
    "indicator": 33,
    "indicator_type": 34,
    "lower": 35,
    "upper": 36,
    "indicator_unit": 37,
    "initial": 38,
    "shelf_life": 46,
}


@dataclass(frozen=True)
class RawIngredient:
    name: str
    concentration: float | None
    unit: str | None
    normalized_percent: float | None
    chemical_composition: str | None
    source_category: str | None


@dataclass(frozen=True)
class Arm:
    arm_id: str
    study_id: str
    origin: str
    matrix_label: str | None
    part_of_product: str | None
    treatment_text: str
    packaging_text: str | None
    storage_text: str | None
    immersion_text: str | None
    ingredients: tuple[RawIngredient, ...]


@dataclass(frozen=True)
class Observation:
    arm_id: str
    indicator_label: str
    indicator_type: str | None
    indicator_unit: str | None
    lower_threshold: float | None
    upper_threshold: float | None
    initial_count: float | None
    shelf_life_days: float | None


def load_yaml(name: str) -> dict:
    return yaml.safe_load((HERE / name).read_text(encoding="utf-8"))


def text(value) -> str | None:
    if value is None or pd.isna(value):
        return None
    cleaned = str(value).replace("​", "").strip()
    return cleaned.lower() or None


def number(value) -> float | None:
    parsed = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(parsed) else float(parsed)


def first_number(raw: str | None, pattern: str) -> float | None:
    match = re.search(pattern, raw or "")
    return float(match.group(1)) if match else None


def parse_temperature(raw: str | None) -> float | None:
    if not raw:
        return None
    if "room" in raw:
        return ROOM_TEMPERATURE_C
    for pattern in (r"(-?\d+(?:\.\d+)?)\s*c.*after", r"^(-?\d+(?:\.\d+)?)\s*[±�]",
                    r"^(-?\d+(?:\.\d+)?)$"):
        value = first_number(raw, pattern)
        if value is not None:
            return value
    match = re.match(r"^(-?\d+(?:\.\d+)?)\s*[-–—]\s*(-?\d+(?:\.\d+)?)$", raw)
    return (float(match.group(1)) + float(match.group(2))) / 2 if match else None


def parse_minutes(raw: str | None) -> float | None:
    hours = first_number(raw, r"(\d+(?:\.\d+)?)\s*hour")
    return hours * 60 if hours else first_number(raw, r"(\d+(?:\.\d+)?)\s*min")


def parse_grams(raw: str | None) -> float | None:
    return first_number(raw, r"(\d+(?:\.\d+)?)\s*g\b")


def digest(*parts) -> str:
    joined = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.blake2s(joined.encode("utf-8"), digest_size=8).hexdigest()


def resolve_indicator(label: str | None, vocabulary: dict) -> dict | None:
    if label is None:
        return None
    for entry in vocabulary["indicators"].values():
        if label in entry["aliases"]:
            return entry
    return None


def _meat_frame() -> pd.DataFrame:
    frame = pd.read_csv(MEAT_CSV, na_values=["-"], encoding="utf-8-sig")
    frame = frame.loc[:, ~frame.columns.astype(str).str.contains("Unnamed")]
    return frame.dropna(how="all").reset_index(drop=True)


def _meat_ingredients(row: pd.Series) -> tuple[RawIngredient, ...]:
    ingredients = []
    for block in range(INGREDIENT_BLOCKS):
        start = BLOCK_START + block * BLOCK_WIDTH
        name = text(row.iloc[start])
        if name is None:
            continue
        ingredients.append(
            RawIngredient(
                name=name,
                concentration=number(row.iloc[start + 1]),
                unit=text(row.iloc[start + 2]),
                normalized_percent=number(row.iloc[start + 3]),
                chemical_composition=text(row.iloc[start + 4]),
                source_category=text(row.iloc[start + 5]),
            )
        )
    return tuple(ingredients)


def load_meat() -> tuple[list[Arm], list[Observation]]:
    frame = _meat_frame()
    arms: dict[str, Arm] = {}
    observations: list[Observation] = []

    for _, row in frame.iterrows():
        study_id = text(row.iloc[0]) or "unknown"
        ingredients = _meat_ingredients(row)
        meta = {key: text(row.iloc[index]) for key, index in META.items()}
        arm_id = digest(
            study_id,
            *(f"{item.name}:{item.concentration}:{item.unit}" for item in ingredients),
            meta["treatment"],
            meta["combined_treatment"],
            meta["packaging"],
            meta["storage"],
            meta["immersion"],
            meta["matrix"],
            meta["part"],
        )
        arms.setdefault(
            arm_id,
            Arm(
                arm_id=arm_id,
                study_id=study_id,
                origin="meat",
                matrix_label=meta["matrix"],
                part_of_product=meta["part"],
                treatment_text=" ".join(
                    part for part in (meta["treatment"], meta["combined_treatment"]) if part
                ),
                packaging_text=meta["packaging"],
                storage_text=meta["storage"],
                immersion_text=meta["immersion"],
                ingredients=ingredients,
            ),
        )
        observations.append(
            Observation(
                arm_id=arm_id,
                indicator_label=meta["indicator"] or "unknown",
                indicator_type=meta["indicator_type"],
                indicator_unit=meta["indicator_unit"],
                lower_threshold=number(row.iloc[META["lower"]]),
                upper_threshold=number(row.iloc[META["upper"]]),
                initial_count=number(row.iloc[META["initial"]]),
                shelf_life_days=number(row.iloc[META["shelf_life"]]),
            )
        )
    return list(arms.values()), observations


def _first_crossing(series: pd.DataFrame, column: str, threshold: float | None) -> float | None:
    if threshold is None:
        return None
    crossed = series[series[column] >= threshold]
    return None if crossed.empty else float(crossed.iloc[0]["day"])


def load_shrimp() -> tuple[list[Arm], list[Observation]]:
    config = load_yaml("shrimp_arms.yaml")
    vocabulary = load_yaml("vocabulary.yaml")

    frame = pd.read_csv(SHRIMP_CSV, encoding="utf-8-sig").dropna(subset=["Ingredient"])
    frame.columns = [name.strip().lower() for name in frame.columns]
    averaged = frame.groupby(["ingredient", "day"], as_index=False).mean(numeric_only=True)

    arms: list[Arm] = []
    observations: list[Observation] = []

    for code, definition in config["arms"].items():
        series = averaged[averaged["ingredient"] == code].sort_values("day")
        if series.empty:
            continue
        arm_id = digest(config["study_id"], code)
        arms.append(
            Arm(
                arm_id=arm_id,
                study_id=config["study_id"],
                origin="shrimp",
                matrix_label=config["matrix_label"],
                part_of_product=config["part_of_product"],
                treatment_text=config["treatment_text"],
                packaging_text=config["packaging_text"],
                storage_text=config["storage_text"],
                immersion_text=config["immersion_text"],
                ingredients=tuple(
                    RawIngredient(
                        name=item["name"],
                        concentration=item["concentration"],
                        unit=item["unit"],
                        normalized_percent=None,
                        chemical_composition=None,
                        source_category=None,
                    )
                    for item in definition["ingredients"]
                ),
            )
        )
        for column, indicator_key in config["indicator_columns"].items():
            entry = vocabulary["indicators"][indicator_key]
            measured = series[["day", column]].dropna()
            if measured.empty:
                continue
            observations.append(
                Observation(
                    arm_id=arm_id,
                    indicator_label=entry["canonical"],
                    indicator_type=entry["type"],
                    indicator_unit=entry["unit"],
                    lower_threshold=entry["lower_threshold"],
                    upper_threshold=entry["upper_threshold"],
                    initial_count=float(measured.iloc[0][column]),
                    shelf_life_days=_first_crossing(measured, column, entry["upper_threshold"]),
                )
            )
    return arms, observations


def load_all() -> tuple[dict[str, Arm], list[Observation]]:
    meat_arms, meat_observations = load_meat()
    shrimp_arms, shrimp_observations = load_shrimp()
    arms = {arm.arm_id: arm for arm in meat_arms + shrimp_arms}
    return arms, meat_observations + shrimp_observations


def write_outputs(table: pd.DataFrame, ingredients: pd.DataFrame, prefix: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUTPUT_DIR / f"{prefix}_data.csv", index=False)
    ingredients.to_csv(OUTPUT_DIR / f"{prefix}_ingredients.csv", index=False)


def report(prefix: str, table: pd.DataFrame, extra: dict) -> None:
    print(f"[{prefix}] rows={len(table)} arms={table['arm_id'].nunique()} "
          f"studies={table['study_id'].nunique()} labelled={int(table['crossed'].sum())}")
    for key, value in extra.items():
        print(f"[{prefix}] {key}: {value}")
