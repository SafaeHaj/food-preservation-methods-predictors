"""
model_service.py — the ONLY place prediction logic lives. Loads the local
artifacts saved by train_models.py and serves predictions; NEVER retrains.
app.py imports and uses this module exclusively.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
ARTIFACTS_DIR = ROOT / "artifacts"
MODELS_DIR = ARTIFACTS_DIR / "models"
DATA_PATH = ROOT / "data" / "raw" / "CHEESE_SHELF_LIFE_REVISED_READY_TO_TRAIN.xlsx"
DATA_SHEET = "training_data"

logger = logging.getLogger("shelf_life.model_service")

SPLIT_FRACTIONS = {"train": 0.70, "validation": 0.15, "test": 0.15}


def make_context_splits(df: pd.DataFrame, seed: int = 42) -> dict[str, pd.DataFrame]:
    """Leakage-safe split: group by context_id (never split a context across
    train/val/test), stratified by whether the context contains any real
    (non-synthetic) row, so the small real-data subset is represented in
    every split rather than left to chance. Lives here (not train_models.py)
    so both training and the dashboard's lookup-building reconstruct the
    exact same train split deterministically from the same seed."""
    context_has_real = df.groupby("context_id")["data_origin"].apply(lambda s: (s == "real_paper_derived").any())
    rng = np.random.default_rng(seed)
    split_context_ids: dict[str, list] = {"train": [], "validation": [], "test": []}
    for stratum_value in (True, False):
        ctx_ids = context_has_real[context_has_real == stratum_value].index.to_numpy()
        rng.shuffle(ctx_ids)
        n = len(ctx_ids)
        n_train = int(round(n * SPLIT_FRACTIONS["train"]))
        n_val = int(round(n * SPLIT_FRACTIONS["validation"]))
        split_context_ids["train"].extend(ctx_ids[:n_train])
        split_context_ids["validation"].extend(ctx_ids[n_train:n_train + n_val])
        split_context_ids["test"].extend(ctx_ids[n_train + n_val:])
    return {
        split: df[df["context_id"].isin(ids)].reset_index(drop=True)
        for split, ids in split_context_ids.items()
    }

MATRIX_DESCRIPTOR_COLUMNS = [
    "cheese_category", "matrix_ph", "matrix_water_activity",
    "matrix_moisture_pct", "matrix_fat_pct", "matrix_protein_pct", "matrix_salt_pct",
    "matrix_ripening_days",
]
# This dataset version has no ingredient-level numeric descriptors (molecular
# weight, logP, solubility, thermal stability, descriptor-available flag) --
# only the ingredient's family. Kept as a dict (not a bare string) so the
# dashboard's "auto-filled, still editable" pattern still works uniformly.
INGREDIENT_DESCRIPTOR_COLUMNS = ["primary_ingredient_family"]
NONE_INGREDIENT_DESCRIPTORS = {"primary_ingredient_family": "none"}


def build_matrix_lookup(train_df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """One row of descriptor defaults per unique food_matrix, from the train
    split only. Categorical -> mode, numeric -> median. Built once at startup
    (see ModelService.__init__)."""
    lookup: dict[str, dict[str, Any]] = {}
    for matrix, g in train_df.groupby("food_matrix"):
        entry: dict[str, Any] = {
            "cheese_category": str(g["cheese_category"].mode(dropna=True).iat[0]),
        }
        for c in ("matrix_ph", "matrix_water_activity", "matrix_moisture_pct", "matrix_fat_pct",
                  "matrix_protein_pct", "matrix_salt_pct", "matrix_ripening_days"):
            entry[c] = float(g[c].median())
        lookup[str(matrix)] = entry
    return lookup


def build_ingredient_lookup(train_df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """One row of descriptor defaults (just the ingredient family) per unique
    primary_ingredient_name, from the train split only."""
    lookup: dict[str, dict[str, Any]] = {}
    for name, g in train_df.groupby("primary_ingredient_name"):
        name = str(name)
        if name == "none":
            lookup[name] = dict(NONE_INGREDIENT_DESCRIPTORS)
            continue
        lookup[name] = {"primary_ingredient_family": str(g["primary_ingredient_family"].mode(dropna=True).iat[0])}
    return lookup

class FrameImputer:
    """Leakage-safe imputer for EBM: keeps native dtypes/category names so
    EBM's own global/local explanations stay human-readable. Fit on train
    only. Defined here (not in train_models.py) so joblib pickles a stable,
    importable reference (`model_service.FrameImputer`) instead of binding
    to whichever script happened to be `__main__` at training time."""

    def __init__(self, numeric_cols: list[str], categorical_cols: list[str]):
        self.numeric_cols = list(numeric_cols)
        self.categorical_cols = list(categorical_cols)
        self.medians_: dict[str, float] = {}

    def fit(self, df: pd.DataFrame) -> "FrameImputer":
        for c in self.numeric_cols:
            self.medians_[c] = float(pd.to_numeric(df[c], errors="coerce").median())
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame(index=df.index)
        for c in self.numeric_cols:
            out[c] = pd.to_numeric(df[c], errors="coerce").fillna(self.medians_[c])
        for c in self.categorical_cols:
            out[c] = df[c].astype("string").fillna("missing").astype(str)
        return out[self.numeric_cols + self.categorical_cols]


MODEL_LABELS = {
    "random_forest": "Random Forest",
    "lightgbm": "LightGBM",
    "xgboost": "XGBoost",
    "ebm": "Explainable Boosting Machine",
    "lstm": "LSTM (experimental tabular benchmark)",
}
BEST_MODEL_KEY = "best_validation_model"


class ModelService:
    """Loads every artifact once and serves predictions from memory.

    Parameterized so the same class serves both the legacy single-model app
    (defaults below, unchanged) and each V6 specialist (constructed with its
    own artifacts_v6/{category}/{task}/ directory and CSV source -- see
    specialist_registry.py). data_sheet=None means "read data_path as CSV";
    a non-None value means "read as Excel with this sheet name," matching
    the legacy XLSX workbook vs the V6 CSV files respectively.
    """

    def __init__(
        self,
        artifacts_dir: Path = ARTIFACTS_DIR,
        data_path: Path = DATA_PATH,
        data_sheet: str | None = DATA_SHEET,
    ) -> None:
        models_dir = artifacts_dir / "models"
        self.schema = _read_json(artifacts_dir / "schema.json")
        self.metrics = _read_json(artifacts_dir / "metrics.json")
        self.feature_importance = _read_json(artifacts_dir / "feature_importance.json")
        self.curves = _read_json(artifacts_dir / "curves.json")
        self.uncertainty = _read_json(artifacts_dir / "uncertainty.json")
        self.category_errors = _read_json(artifacts_dir / "category_errors.json")
        self.manifest = _read_json(artifacts_dir / "training_manifest.json")
        self.predictions = pd.read_parquet(artifacts_dir / "predictions.parquet")

        self.numeric_cols: list[str] = self.schema["numeric_columns"]
        self.categorical_cols: list[str] = self.schema["categorical_columns"]
        self.binary_cols: list[str] = self.schema["binary_columns"]
        self.numeric_and_binary: list[str] = self.numeric_cols + self.binary_cols
        self.feature_cols: list[str] = self.schema["all_feature_columns"]
        self.best_model: str = self.manifest["best_model_by_validation_rmse"]
        self.lstm_available: bool = self.manifest.get("lstm_available", False)

        self.tree_pre = joblib.load(models_dir / "preprocessor_tree.joblib")
        self.ebm_pre = joblib.load(models_dir / "preprocessor_ebm.joblib")

        self.models: dict[str, Any] = {
            "random_forest": joblib.load(models_dir / "random_forest.joblib"),
            "lightgbm": joblib.load(models_dir / "lightgbm.joblib"),
            "xgboost": joblib.load(models_dir / "xgboost.joblib"),
            "ebm": joblib.load(models_dir / "ebm.joblib"),
        }
        if self.lstm_available and (models_dir / "lstm.keras").exists():
            import tensorflow as tf
            self.models["lstm"] = tf.keras.models.load_model(models_dir / "lstm.keras")
            self.lstm_scaler = joblib.load(models_dir / "preprocessor_lstm_scaler.joblib")

        # Dashboard-only lookups for auto-filling the prediction form. Built once
        # here from the exact same train split train_models.py (or
        # train_specialists.py) fit on (same seed, same make_context_splits) --
        # never recomputed per-interaction; do not affect training, artifacts,
        # or the prediction formulas below.
        if data_sheet is not None:
            self.full_df = pd.read_excel(data_path, sheet_name=data_sheet)
        else:
            self.full_df = pd.read_csv(data_path)
        train_df = make_context_splits(self.full_df, seed=self.manifest.get("random_seed", 42))["train"]
        self.matrix_lookup = build_matrix_lookup(train_df)
        self.ingredient_lookup = build_ingredient_lookup(train_df)

    @property
    def available_models(self) -> list[str]:
        return list(self.models.keys())

    def resolve_model_name(self, name: str) -> str:
        return self.best_model if name == BEST_MODEL_KEY else name

    def model_label(self, name: str) -> str:
        resolved = self.resolve_model_name(name)
        return MODEL_LABELS.get(resolved, resolved)

    # ── Row construction ─────────────────────────────────────────────────────

    def build_control_row(self, shared: dict[str, Any]) -> dict[str, Any]:
        row = dict(shared)
        row.update(self.schema["control_template"])
        return row

    def default_row(self) -> dict[str, Any]:
        row: dict[str, Any] = {}
        for c in self.numeric_and_binary:
            row[c] = self.schema["numeric_ranges"][c]["median"]
        for c in self.categorical_cols:
            opts = self.schema["categorical_options"].get(c, [])
            row[c] = opts[0] if opts else "missing"
        return row

    def _row_to_frame(self, row: dict[str, Any]) -> pd.DataFrame:
        full = {c: row.get(c) for c in self.feature_cols}
        return pd.DataFrame([full])

    # ── Support assessment ───────────────────────────────────────────────────
    #
    # Replaces the old flat warning-string list with a structured, honest
    # assessment the caller (backend + any validation script) must act on
    # differently depending on level -- an unseen category or an
    # out-of-range numeric no longer silently produces a "normal"-looking
    # prediction with just a string attached; the level is explicit and
    # machine-checkable. Reused identically by /api/v6/predict and
    # specialist_registry.assess_prediction_support -- never reimplemented
    # separately for validation (see project audit, item #10).

    def assess_support(self, row: dict[str, Any]) -> dict[str, Any]:
        # A missing value arrives as None from a live JSON request, but as
        # NaN when a row is built from a CSV (e.g. an external test file
        # with incomplete lab measurements) -- both mean "not provided",
        # neither should be reported as an unseen category or an
        # out-of-range number.
        def _is_missing(v: Any) -> bool:
            return v is None or (isinstance(v, float) and np.isnan(v))

        unseen_categoricals: list[dict[str, str]] = []
        for c in self.categorical_cols:
            v = row.get(c)
            if _is_missing(v):
                continue
            options = self.schema["categorical_options"].get(c, [])
            if str(v) not in options:
                unseen_categoricals.append({"feature": c, "value": str(v)})

        extrapolations: list[dict[str, Any]] = []
        conditional = self.schema.get("numeric_ranges_conditional", {})
        for c in self.numeric_and_binary:
            v = row.get(c)
            if _is_missing(v):
                continue
            try:
                v = float(v)
            except (TypeError, ValueError):
                continue

            # Prefer the range conditioned on the row's actual categorical
            # context (e.g. indicator_threshold given THIS row's specific
            # indicator_type + indicator_unit) over the flat pooled range,
            # which can mix incompatible scales together (verified: e.g.
            # canonical_concentration_value pooled 0.02-495 across 6
            # different units before this fix). Falls back to the pooled
            # range only when no conditional statistic exists for c.
            rng, conditioned_on = None, None
            cond_spec = conditional.get(c)
            if cond_spec:
                cond_cols = cond_spec["conditioned_on"]
                key_parts = [row.get(cc) for cc in cond_cols]
                if all(p is not None for p in key_parts):
                    key_str = "||".join(str(p) for p in key_parts)
                    rng = cond_spec["ranges"].get(key_str)
                    if rng:
                        conditioned_on = dict(zip(cond_cols, (str(p) for p in key_parts)))
            if rng is None:
                rng = self.schema["numeric_ranges"].get(c)

            if rng and not (rng["min"] <= v <= rng["max"]):
                ctx = f" for {conditioned_on}" if conditioned_on else ""
                if rng["min"] == rng["max"]:
                    detail = f"'{c}' = {v} differs from the single value ({rng['min']:.3g}) seen in training{ctx}"
                else:
                    detail = f"'{c}' = {v} is outside the training range [{rng['min']:.3g}, {rng['max']:.3g}]{ctx}"
                extrapolations.append({
                    "feature": c, "value": v, "range": {"min": rng["min"], "max": rng["max"]},
                    "conditioned_on": conditioned_on, "detail": detail,
                })

        if unseen_categoricals:
            level = "unsupported_categorical"
        elif extrapolations:
            level = "extrapolation"
        else:
            level = "supported"

        warnings = [f"'{u['feature']}' = {u['value']!r} was never seen in training (unseen category)" for u in unseen_categoricals]
        warnings += [e["detail"] for e in extrapolations]
        for w in warnings:
            logger.warning("prediction input warning: %s", w)

        return {
            "level": level,
            "unseen_categoricals": unseen_categoricals,
            "extrapolations": extrapolations,
            "warnings": warnings,
        }

    def check_input_warnings(self, row: dict[str, Any]) -> list[str]:
        """Thin backward-compatible wrapper -- prefer assess_support() for
        any new caller that can act on the structured level, not just log
        text."""
        return self.assess_support(row)["warnings"]

    # ── Raw prediction per model family ─────────────────────────────────────

    def _predict_raw(self, model_name: str, df: pd.DataFrame) -> np.ndarray:
        if model_name not in self.models:
            raise ValueError(f"Unknown or unavailable model: {model_name}")
        model = self.models[model_name]
        if model_name == "ebm":
            X = self.ebm_pre.transform(df)
            return np.asarray(model.predict(X), dtype=float)
        X_tree = self.tree_pre.transform(df[self.numeric_and_binary + self.categorical_cols])
        if model_name == "lstm":
            X_scaled = self.lstm_scaler.transform(X_tree)
            X_seq = X_scaled.reshape(X_scaled.shape[0], X_scaled.shape[1], 1)
            return np.asarray(model.predict(X_seq, verbose=0), dtype=float).ravel()
        return np.asarray(model.predict(X_tree), dtype=float)

    def predict_one(self, model_name: str, row: dict[str, Any]) -> dict[str, Any]:
        resolved = self.resolve_model_name(model_name)
        support = self.assess_support(row)
        df = self._row_to_frame(row)
        raw_pred = float(self._predict_raw(resolved, df)[0])
        pred = max(raw_pred, 0.0)
        q = self.uncertainty[resolved]["quantile_90"]
        lower = max(0.0, pred - q)
        upper = max(0.0, pred + q)
        return {
            "model": resolved, "model_label": self.model_label(resolved),
            "prediction_days": pred, "lower_bound": lower, "upper_bound": upper,
            "warnings": support["warnings"], "support": support,
        }

    # ── Control vs. candidates ──────────────────────────────────────────────

    def compare_control_vs_candidates(
        self, model_name: str, shared: dict[str, Any], candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        resolved = self.resolve_model_name(model_name)
        control_row = self.build_control_row(shared)
        control_result = self.predict_one(resolved, control_row)
        control_pred = control_result["prediction_days"]

        results = []
        for i, cand in enumerate(candidates):
            row = {**shared, **cand}
            res = self.predict_one(resolved, row)
            cand_pred = res["prediction_days"]
            if control_pred > 1e-9:
                abs_impr = cand_pred - control_pred
                rel_impr = abs_impr / control_pred * 100.0
                ratio = cand_pred / control_pred
            else:
                abs_impr = cand_pred - control_pred
                rel_impr = float("nan")
                ratio = float("nan")
            results.append({
                "candidate_name": cand.get("name") or f"Candidate {i + 1}",
                "model": resolved, "model_label": self.model_label(resolved),
                "predicted_candidate_shelf_life": cand_pred,
                "predicted_control_shelf_life": control_pred,
                "absolute_improvement_days": abs_impr,
                "relative_improvement_pct": rel_impr,
                "shelf_life_ratio": ratio,
                "lower_bound": res["lower_bound"], "upper_bound": res["upper_bound"],
                "warnings": res["warnings"], "support": res["support"], "row": row,
            })

        results.sort(key=lambda r: (r["predicted_candidate_shelf_life"], r["absolute_improvement_days"]), reverse=True)
        for rank, r in enumerate(results, start=1):
            r["rank"] = rank

        return {"control": control_result, "candidates": results}

    # ── Local explanation ────────────────────────────────────────────────────

    def local_explanation(self, model_name: str, row: dict[str, Any], top_k: int = 8) -> list[dict[str, Any]]:
        resolved = self.resolve_model_name(model_name)
        df = self._row_to_frame(row)
        if resolved == "ebm":
            X = self.ebm_pre.transform(df)
            local = self.models["ebm"].explain_local(X)
            d = local.data(0)
            contribs = [
                {"feature": n, "contribution": float(s), "is_interaction": " & " in n}
                for n, s in zip(d["names"], d["scores"])
            ]
            contribs = [c for c in contribs if not c["is_interaction"]]
        else:
            contribs = self._perturbation_local(resolved, df)
        contribs.sort(key=lambda c: abs(c["contribution"]), reverse=True)
        return contribs[:top_k]

    def _reference_value(self, feature: str) -> Any:
        if feature in self.numeric_and_binary:
            return self.schema["numeric_ranges"][feature]["median"]
        return self.schema.get("categorical_modes", {}).get(feature, "missing")

    # ── Dataset-level summaries (shared by REST endpoints + assistant tools) ──

    def dataset_statistics(self, cheese_category: str | None = None) -> dict[str, Any]:
        df = self.full_df
        if cheese_category:
            df = df[df["cheese_category"] == cheese_category]
        if len(df) == 0:
            return {"n_rows": 0, "note": f"No rows match cheese_category={cheese_category!r}"}
        return {
            "n_rows": int(len(df)),
            "n_contexts": int(df["context_id"].nunique()),
            "cheese_categories": df["cheese_category"].value_counts().to_dict(),
            "food_matrices": df["food_matrix"].value_counts().to_dict(),
            "packaging_types": df["packaging_type"].value_counts().to_dict(),
            "indicator_types": df["indicator_type"].value_counts().to_dict(),
            "ingredient_families": df[df["primary_ingredient_family"] != "none"]["primary_ingredient_family"].value_counts().to_dict(),
            "ingredients": df[df["primary_ingredient_name"] != "none"]["primary_ingredient_name"].value_counts().to_dict(),
            "application_methods": df[df["application_method"] != "none"]["application_method"].value_counts().to_dict(),
            "shelf_life_days": {
                "min": float(df["shelf_life_days"].min()), "max": float(df["shelf_life_days"].max()),
                "mean": float(df["shelf_life_days"].mean()), "median": float(df["shelf_life_days"].median()),
                "std": float(df["shelf_life_days"].std()),
            },
            "storage_temperature_c": {
                "min": float(df["storage_temperature_c"].min()), "max": float(df["storage_temperature_c"].max()),
                "mean": float(df["storage_temperature_c"].mean()),
            },
            "control_vs_treatment": {
                "n_control": int((df["is_control"] == 1).sum()),
                "n_treatment": int((df["is_control"] == 0).sum()),
            },
        }

    def dataset_references(self) -> dict[str, Any]:
        df = self.full_df
        real = df[df["data_origin"] == "real_paper_derived"]
        non_real = df[df["data_origin"] != "real_paper_derived"]
        method = non_real["data_origin"].mode().iat[0] if len(non_real) else "unknown"
        rule_counts = df["source_rule_id"].value_counts().to_dict() if "source_rule_id" in df.columns else {}
        return {
            "sources": [],
            "n_real_rows": int(len(real)),
            "n_synthetic_rows": int(len(non_real)),
            "synthetic_method": method,
            "generation_rules": rule_counts,
        }

    def _perturbation_local(self, model_name: str, df: pd.DataFrame) -> list[dict[str, Any]]:
        """Local feature-perturbation explanation: for each feature, replace
        it with a fixed reference value (training median / mode) and measure
        the change in prediction. Used for tree models (stable, works with
        any fitted pipeline) and the LSTM (simple local perturbation, no
        dependency on SHAP)."""
        base_pred = float(self._predict_raw(model_name, df)[0])
        contribs = []
        for c in self.feature_cols:
            df2 = df.copy()
            df2[c] = self._reference_value(c)
            pred2 = float(self._predict_raw(model_name, df2)[0])
            contribs.append({"feature": c, "contribution": base_pred - pred2, "is_interaction": False})
        return contribs


def build_candidate_row(c: dict[str, Any]) -> dict[str, Any]:
    """Shared candidate-row construction used by both the FastAPI /api/predict
    endpoint and the assistant's compare_treatments tool, so treatment rows
    are built identically regardless of caller."""
    name = c.get("primary_ingredient_name")
    is_none = name == "none" or not name
    count = 0 if is_none else 1
    return {
        "name": c.get("name"), "is_control": 0,
        "treatment_type": c.get("treatment_type"),
        "application_method": "none" if is_none else c.get("application_method"),
        "ingredient_count": count,
        "primary_ingredient_name": name,
        "primary_ingredient_family": "none" if is_none else c.get("primary_ingredient_family"),
        "primary_concentration": 0.0 if is_none else c.get("primary_concentration"),
        "primary_concentration_unit": "none" if is_none else c.get("primary_concentration_unit"),
    }


def build_candidate_row_v6(c: dict[str, Any]) -> dict[str, Any]:
    """V6 candidate-row construction: takes whatever raw unit the user
    actually typed (primary_concentration / primary_concentration_unit) and
    converts it to the canonical_concentration_value/unit the V6 specialist
    models were trained on, via the verified conversion table in
    concentration_units.py -- never asks the frontend to pick from the
    canonical unit vocabulary directly, and never invents a factor for an
    unrecognized unit (to_canonical raises in that case)."""
    from concentration_units import to_canonical

    name = c.get("primary_ingredient_name")
    is_none = name == "none" or not name
    count = 0 if is_none else 1
    if is_none:
        canonical_value, canonical_unit = 0.0, "none"
    else:
        canonical_value, canonical_unit = to_canonical(c.get("primary_concentration"), c.get("primary_concentration_unit"))
    return {
        "name": c.get("name"), "is_control": 0,
        "treatment_type": c.get("treatment_type"),
        "application_method": "none" if is_none else c.get("application_method"),
        "ingredient_count": count,
        "primary_ingredient_name": name,
        "primary_ingredient_family": "none" if is_none else c.get("primary_ingredient_family"),
        "canonical_concentration_value": canonical_value,
        "canonical_concentration_unit": canonical_unit,
    }


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
