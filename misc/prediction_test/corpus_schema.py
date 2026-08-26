"""Convert the Docling/gate extraction output into the relational schema directly.

Reads ``data/extracted/<paper>/gate.json`` and writes the five schema tables
(papers, experiments, experiment_ingredients, indicators, measurements) as CSVs.
This bypasses the processing service: vocabulary resolution, arm inference and
unit conversion are done here deterministically from the gated observations.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
import yaml

HERE = Path(__file__).parent
EXTRACTED_DIR = HERE.parent.parent / "data" / "extracted"
OUTPUT_DIR = HERE / "data"

VOCABULARY = yaml.safe_load((HERE / "vocabulary.yaml").read_text(encoding="utf-8"))
REFERENCE = yaml.safe_load((HERE / "reference.yaml").read_text(encoding="utf-8"))

INDICATORS = VOCABULARY["indicators"]
MATRICES = REFERENCE["matrices"]
PERCENT_TO_PPM = 10000

# Indicators whose value rises as the product spoils, so the upper threshold is
# crossed from below. Failure time is only defined for these.
RISING_INDICATORS = {
    "tvc", "psychrotrophic", "lab", "enterobacteriaceae", "pseudomonas", "brochothrix",
    "fungal", "e_coli", "s_aureus", "salmonella", "listeria", "tbars", "pv", "tvbn",
    "tman", "hexanal", "weight_loss",
}

# Surface forms seen in the corpus that the curated vocabulary does not list.
CORPUS_INDICATOR_ALIASES = {
    "total aerobic microflora": "tvc",
    "total aerobic mesophilic": "tvc",
    "total aerobic bacteria": "tvc",
    "total mesophilic bacteria": "tvc",
    "mesophilic aerobic": "tvc",
    "aerobic plate count": "tvc",
    "total bacterial count": "tvc",
    "total microbial count": "tvc",
    "apc": "tvc",
    "tamc": "tvc",
    "tam": "tvc",
    "psychrotrophic bacteria": "psychrotrophic",
    "psychrophilic": "psychrotrophic",
    "mold and yeast": "fungal",
    "yeasts and moulds": "fungal",
    "yeast and mold": "fungal",
    "moulds and yeasts": "fungal",
    "molds": "fungal",
    "moulds": "fungal",
    "mold": "fungal",
    "mould": "fungal",
    "yeasts": "fungal",
    "tbras": "tbars",
    "tba-rs": "tbars",
    "thiobarbituric acid reactive": "tbars",
    "malondialdehyde": "tbars",
    "mda": "tbars",
    "peroxide": "pv",
    "listeria monocytogenes": "listeria",
    "salmonella typhimurium": "salmonella",
    "s. enterica": "salmonella",
    "staphylococcus": "s_aureus",
    "coliforms": "enterobacteriaceae",
    "total coliform": "enterobacteriaceae",
    "enterobacteria": "enterobacteriaceae",
    "trimethylamine": "tman",
    "total volatile basic": "tvbn",
}

MATRIX_KEYWORDS = {
    "chicken": "chicken", "broiler": "chicken", "poultry": "chicken",
    "beef": "beef", "cattle": "beef", "veal": "beef",
    "pork": "pork", "swine": "pork", "ham": "pork",
    "lamb": "lamb", "mutton": "lamb",
    "goat": "goat",
    "fish": "fish", "salmon": "fish", "trout": "fish", "carp": "fish", "tilapia": "fish",
    "shrimp": "shrimp", "prawn": "shrimp",
    "sausage": "mixed", "patty": "mixed", "patties": "mixed", "burger": "mixed",
    "meatball": "mixed", "nugget": "mixed",
}

CONTROL_LABELS = {
    "ctrl", "ck", "c", "nc", "con", "cont", "blank", "t0", "cs0", "c0", "kb",
}
CONTROL_SUBSTRINGS = ("control", "untreated", "uncoated", "unheated", "no treatment")

# A gated observation is only accepted for an indicator when its value is
# physically plausible for that indicator's unit. This is what rejects a
# day-axis table of particle sizes being read as a microbial count because the
# surrounding section happened to mention TVC.
PLAUSIBLE_RANGES = {
    "log_count": (0.0, 14.0),
    "tbars": (0.0, 30.0),
    "pv": (0.0, 200.0),
    "tvbn": (0.0, 250.0),
    "tman": (0.0, 100.0),
    "hexanal": (0.0, 300.0),
    "weight_loss": (0.0, 60.0),
    "ph": (3.0, 9.0),
    "water_activity": (0.5, 1.05),
    "colour": (-60.0, 120.0),
    "oxidation_index": (0.0, 10.0),
}


def plausible_range(indicator: str) -> tuple[float, float]:
    if INDICATORS[indicator]["type"] == "microbial":
        return PLAUSIBLE_RANGES["log_count"]
    return PLAUSIBLE_RANGES.get(indicator, (-1e6, 1e6))

DAY_AXIS_PATTERN = re.compile(
    r"day|storage\s*time|sampling\s*time|ripening\s*time|storage\s*\(d|storage\s*period", re.I
)
NON_DAY_UNIT_PATTERN = re.compile(r"\b(hr|hour|hours|min|minute|month|months|week|weeks)\b", re.I)
TEMPERATURE_PATTERN = re.compile(r"(-?\d{1,2}(?:\.\d)?)\s*(?:±\s*\d+(?:\.\d+)?\s*)?°?\s*C\b")
PERCENT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*%")
PPM_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(ppm|mg/kg|mg/g|g/kg|mg/ml|g/l)", re.I)

STORAGE_TEMPERATURE_RANGE = (-5.0, 30.0)
MIN_SERIES_POINTS = 3
# A day axis running past this is not a chilled-meat storage trial; it is an
# axis in other units that the gate labelled "storage time". Rejecting the whole
# asset is safer than truncating it, because the scale is wrong throughout.
MAX_STORAGE_DAY = 120.0


def normalise(text: str | None) -> str:
    if not text:
        return ""
    folded = unicodedata.normalize("NFKD", str(text)).lower()
    return re.sub(r"\s+", " ", folded).strip()


def _build_alias_index(pairs: dict[str, str]) -> list[str]:
    return sorted(pairs, key=len, reverse=True)


INDICATOR_ALIASES = {
    alias.lower(): key for key, entry in INDICATORS.items() for alias in entry["aliases"]
}
INDICATOR_ALIASES.update(CORPUS_INDICATOR_ALIASES)
INDICATOR_ALIAS_ORDER = _build_alias_index(INDICATOR_ALIASES)

INGREDIENT_ALIASES = {
    alias.lower(): name
    for name, entry in REFERENCE["ingredients"].items()
    for alias in entry["aliases"]
}
INGREDIENT_ALIAS_ORDER = _build_alias_index(INGREDIENT_ALIASES)


def match_alias(text: str | None, order: list[str], index: dict[str, str]) -> str | None:
    folded = normalise(text)
    if not folded:
        return None
    for alias in order:
        if re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", folded):
            return index[alias]
    return None


def match_indicator(text: str | None) -> str | None:
    return match_alias(text, INDICATOR_ALIAS_ORDER, INDICATOR_ALIASES)


def match_ingredient(text: str | None) -> str | None:
    return match_alias(text, INGREDIENT_ALIAS_ORDER, INGREDIENT_ALIASES)


def is_day_axis(gate: dict) -> bool:
    label = gate.get("axis_label") or ""
    if NON_DAY_UNIT_PATTERN.search(label) and not DAY_AXIS_PATTERN.search(label):
        return False
    if not DAY_AXIS_PATTERN.search(label):
        return False
    points = [p for p in (gate.get("axis_points") or []) if isinstance(p, (int, float))]
    return bool(points) and max(points) <= MAX_STORAGE_DAY


def paper_text(gate: dict) -> str:
    sections = " ".join(section.get("content_markdown") or "" for section in gate.get("sections", []))
    titles = " ".join(section.get("section_title") or "" for section in gate.get("sections", []))
    texts = " ".join(
        item.get("text", "") if isinstance(item, dict) else str(item)
        for item in gate.get("texts", [])
    )
    return f"{titles} {sections} {texts}"


def detect_matrix(blob: str) -> str | None:
    folded = normalise(blob)
    counts = Counter()
    for keyword, matrix in MATRIX_KEYWORDS.items():
        hits = len(re.findall(rf"(?<![a-z]){keyword}(?![a-z])", folded))
        if hits:
            counts[matrix] += hits
    return counts.most_common(1)[0][0] if counts else None


def detect_storage_temperature(blob: str) -> float | None:
    low, high = STORAGE_TEMPERATURE_RANGE
    candidates = [
        value for value in (float(match) for match in TEMPERATURE_PATTERN.findall(blob))
        if low <= value <= high
    ]
    return Counter(candidates).most_common(1)[0][0] if candidates else None


def detect_packaging(blob: str) -> str | None:
    folded = normalise(blob)
    counts = Counter()
    for atmosphere, keywords in VOCABULARY["packaging"]["atmosphere"].items():
        hits = sum(len(re.findall(rf"(?<![a-z]){keyword}(?![a-z])", folded)) for keyword in keywords)
        if hits:
            counts[atmosphere] += hits
    return counts.most_common(1)[0][0] if counts else None


def detect_treatment(blob: str) -> str | None:
    folded = normalise(blob)
    treatments = VOCABULARY["treatments"]
    counts = Counter({
        label: sum(folded.count(pattern) for pattern in patterns)
        for label, patterns in treatments["patterns"].items()
    })
    ranked = [label for label in treatments["types"] if counts[label]]
    return max(ranked, key=lambda label: counts[label], default=None)


def asset_contexts(asset: dict) -> list[str]:
    """Ordered most to least specific: a caption names the quantity, a section
    heading only says what the surrounding prose is about."""
    return [
        asset.get("caption") or "",
        " ".join(asset.get("headers") or []),
        asset.get("section_hint") or "",
    ]


JUNK_LABEL_PATTERN = re.compile(r"^(row\s*\d+|col\s*\d+|series|chart|\d+(\.\d+)?)$", re.I)
DESCRIPTOR_PATTERN = re.compile(
    r"(?<![a-z])(counts?|log|cfu|gr?|ml|value|values|content|index|mean|means|level|levels)"
    r"(?![a-z])", re.I
)
NON_LATIN_PATTERN = re.compile(r"[^\x00-\x7F]+")


def strip_indicator(label: str, indicator: str) -> str:
    """Remove the indicator's own name from a label so only the arm code is left."""
    residue = str(label)
    for alias in INDICATOR_ALIAS_ORDER:
        if INDICATOR_ALIASES[alias] != indicator:
            continue
        residue = re.sub(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", " ", residue, flags=re.I)
    return residue


def clean_arm_label(label: str, drop_descriptors: bool = False) -> str:
    stripped = re.sub(r"\(.*?\)", " ", str(label))
    stripped = re.sub(r"[*`±]", " ", stripped)
    if drop_descriptors:
        stripped = NON_LATIN_PATTERN.sub(" ", DESCRIPTOR_PATTERN.sub(" ", stripped))
    stripped = re.sub(r"^\s*(and|or|&)\b", " ", stripped, flags=re.I)
    stripped = re.sub(r"\s+", " ", stripped).strip(" .,-/_")[:60]
    return "" if JUNK_LABEL_PATTERN.match(stripped) else stripped


def arm_label_from(labels: list[str], indicator: str) -> str:
    """Labels that do not name the indicator identify the arm. Only when every
    label names the indicator does the arm code have to be recovered from what
    is left after the indicator's own name is removed."""
    arm_bearing = [label for label in labels if match_indicator(label) is None]
    if arm_bearing:
        parts = [clean_arm_label(label) for label in arm_bearing]
    else:
        parts = [
            clean_arm_label(strip_indicator(label, indicator), drop_descriptors=True)
            for label in labels
        ]
    return " / ".join(part for part in parts if part)


def is_control(label: str) -> bool:
    folded = normalise(label)
    return folded in CONTROL_LABELS or any(word in folded for word in CONTROL_SUBSTRINGS)


def parse_dose_ppm(label: str) -> float | None:
    percent = PERCENT_PATTERN.search(label)
    if percent:
        return float(percent.group(1)) * PERCENT_TO_PPM
    absolute = PPM_PATTERN.search(label)
    if not absolute:
        return None
    factor = VOCABULARY["units"]["ppm_factors"].get(absolute.group(2).lower(), 1)
    return float(absolute.group(1)) * factor


def read_measurements() -> pd.DataFrame:
    """One row per (paper, arm, indicator, day) gated observation."""
    records = []
    for paper_dir in sorted(EXTRACTED_DIR.iterdir()):
        gate_path = paper_dir / "gate.json"
        if not gate_path.exists():
            continue
        gate = json.loads(gate_path.read_text(encoding="utf-8"))
        for asset in gate.get("tables", []) + gate.get("figures", []):
            info = asset.get("gate") or {}
            if not is_day_axis(info):
                continue
            contexts = asset_contexts(asset)
            asset_indicator = next((m for c in contexts if (m := match_indicator(c))), None)
            for observation in asset.get("observations") or []:
                day, value = observation.get("axis_value"), observation.get("value")
                if day is None or value is None:
                    continue
                labels = [observation.get("column_label")]
                labels += list((observation.get("row_labels") or {}).values())
                labels = [label for label in labels if label]
                label_indicator = next((m for l in labels if (m := match_indicator(l))), None)
                indicator = label_indicator or asset_indicator
                if indicator is None:
                    continue
                low, high = plausible_range(indicator)
                if not low <= float(value) <= high:
                    continue
                arm_label = arm_label_from(labels, indicator)
                records.append({
                    "paper_id": paper_dir.name,
                    "arm_label": arm_label or "unlabelled",
                    "indicator_name": indicator,
                    "day": float(day),
                    "indicator_value": float(value),
                    "from_figure": bool(asset.get("is_figure")),
                })
    frame = pd.DataFrame(records)
    return (
        frame.groupby(["paper_id", "arm_label", "indicator_name", "day"], as_index=False)
        .agg(indicator_value=("indicator_value", "median"), from_figure=("from_figure", "max"))
    )


def read_papers() -> pd.DataFrame:
    records = []
    for paper_dir in sorted(EXTRACTED_DIR.iterdir()):
        gate_path = paper_dir / "gate.json"
        if not gate_path.exists():
            continue
        gate = json.loads(gate_path.read_text(encoding="utf-8"))
        blob = paper_text(gate)
        records.append({
            "paper_id": paper_dir.name,
            "meat_matrix": detect_matrix(blob),
            "storage_temperature_c": detect_storage_temperature(blob),
            "packaging_atmosphere": detect_packaging(blob),
            "treatment_type": detect_treatment(blob),
            "page_count": gate.get("page_count"),
        })
    return pd.DataFrame(records)


def keep_usable_series(measurements: pd.DataFrame) -> pd.DataFrame:
    """Drop series that cannot define a failure time."""
    thresholds = pd.Series(
        {key: entry["upper_threshold"] for key, entry in INDICATORS.items()}
    )
    usable_indicators = [
        name for name in RISING_INDICATORS if thresholds.get(name) is not None
    ]
    frame = measurements[measurements["indicator_name"].isin(usable_indicators)]
    sizes = frame.groupby(["paper_id", "arm_label", "indicator_name"])["day"].transform("size")
    spans = frame.groupby(["paper_id", "arm_label", "indicator_name"])["day"].transform(
        lambda days: days.max() - days.min()
    )
    return frame[(sizes >= MIN_SERIES_POINTS) & (spans > 0)].copy()


def build_experiments(measurements: pd.DataFrame, papers: pd.DataFrame) -> pd.DataFrame:
    arms = measurements[["paper_id", "arm_label"]].drop_duplicates().reset_index(drop=True)
    arms["arm_id"] = arms["paper_id"] + "::" + arms["arm_label"]
    arms["is_control"] = arms["arm_label"].map(is_control).astype(int)
    arms["ingredient_name"] = arms["arm_label"].map(match_ingredient)
    arms["concentration_ppm"] = arms["arm_label"].map(parse_dose_ppm)
    arms.loc[arms["is_control"] == 1, ["ingredient_name", "concentration_ppm"]] = [None, 0.0]
    merged = arms.merge(papers, on="paper_id", how="left")
    matrix_frame = pd.DataFrame(MATRICES).T.rename(columns=lambda c: f"matrix_{c}")
    return merged.merge(matrix_frame, left_on="meat_matrix", right_index=True, how="left")


def build_experiment_ingredients(experiments: pd.DataFrame) -> pd.DataFrame:
    dosed = experiments[experiments["ingredient_name"].notna()].copy()
    catalogue = pd.DataFrame(REFERENCE["ingredients"]).T
    catalogue.index.name = "ingredient_name"
    columns = ["functional_class", "source_category", "molecular_weight", "logp", "pka",
               "hbd_count", "hba_count"]
    catalogue = catalogue.reindex(columns=columns).reset_index()
    return (
        dosed[["arm_id", "paper_id", "ingredient_name", "concentration_ppm"]]
        .merge(catalogue, on="ingredient_name", how="left")
        .rename(columns={"source_category": "source"})
    )


def build_indicators(measurements: pd.DataFrame) -> pd.DataFrame:
    used = sorted(measurements["indicator_name"].unique())
    return pd.DataFrame([
        {
            "indicator_name": name,
            "indicator_type": INDICATORS[name]["type"],
            "indicator_unit": INDICATORS[name]["unit"],
            "indicator_threshold": INDICATORS[name]["upper_threshold"],
            "lower_threshold": INDICATORS[name]["lower_threshold"],
            "rises_with_spoilage": name in RISING_INDICATORS,
        }
        for name in used
    ])


def build() -> dict[str, pd.DataFrame]:
    raw_measurements = read_measurements()
    papers = read_papers()
    measurements = keep_usable_series(raw_measurements)
    measurements["arm_id"] = measurements["paper_id"] + "::" + measurements["arm_label"]

    experiments = build_experiments(measurements, papers)
    papers = papers[papers["paper_id"].isin(experiments["paper_id"])].reset_index(drop=True)
    return {
        "papers": papers,
        "experiments": experiments,
        "experiment_ingredients": build_experiment_ingredients(experiments),
        "indicators": build_indicators(measurements),
        "measurements": measurements[
            ["arm_id", "paper_id", "arm_label", "indicator_name", "day", "indicator_value",
             "from_figure"]
        ].sort_values(["arm_id", "indicator_name", "day"]).reset_index(drop=True),
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tables = build()
    for name, frame in tables.items():
        frame.to_csv(OUTPUT_DIR / f"corpus_{name}.csv", index=False)
        print(f"corpus_{name}.csv: {frame.shape[0]} rows x {frame.shape[1]} cols")

    measurements = tables["measurements"]
    experiments = tables["experiments"]
    series = measurements.groupby(["arm_id", "indicator_name"]).size()
    print()
    print(f"papers           {tables['papers'].shape[0]}")
    print(f"arms             {experiments.shape[0]} "
          f"({int(experiments['is_control'].sum())} controls)")
    print(f"series           {len(series)} (median {series.median():.0f} points)")
    print(f"resolved dose    {int(experiments['concentration_ppm'].notna().sum())} arms")
    print(f"resolved matrix  {int(experiments['meat_matrix'].notna().sum())} arms")
    print(f"resolved temp    {int(experiments['storage_temperature_c'].notna().sum())} arms")


if __name__ == "__main__":
    main()
