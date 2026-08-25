"""
classification_service.py -- loads artifacts_classification/ (produced by
train_classifier.py) and serves efficacy-class predictions. Mirrors the
read-only-from-saved-artifacts pattern of model_service.py: loads once at
startup, NEVER retrains, NEVER touches train_classifier.py or the
regression pipeline's artifacts/.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

ROOT = Path(__file__).resolve().parent
ARTIFACTS_DIR = ROOT / "artifacts_classification"
MODELS_DIR = ARTIFACTS_DIR / "models"

CLF_MODEL_LABELS = {
    "random_forest": "Random Forest Classifier",
    "xgboost": "XGBoost Classifier",
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


class ClassificationService:
    """Loads every classification artifact once and serves predictions from memory."""

    def __init__(self) -> None:
        self.schema = _read_json(ARTIFACTS_DIR / "schema.json")
        self.metrics = _read_json(ARTIFACTS_DIR / "metrics.json")
        self.confusion = _read_json(ARTIFACTS_DIR / "confusion_matrix.json")
        self.feature_importance = _read_json(ARTIFACTS_DIR / "feature_importance.json")
        self.class_distribution = _read_json(ARTIFACTS_DIR / "class_distribution.json")
        self.class_definitions = _read_json(ARTIFACTS_DIR / "class_definitions.json")
        self.manifest = _read_json(ARTIFACTS_DIR / "training_manifest.json")

        self.numeric_cols: list[str] = self.schema["numeric_columns"]
        self.categorical_cols: list[str] = self.schema["categorical_columns"]
        self.binary_cols: list[str] = self.schema["binary_columns"]
        self.numeric_and_binary: list[str] = self.numeric_cols + self.binary_cols
        self.feature_cols: list[str] = self.schema["all_feature_columns"]
        self.class_names: list[str] = self.class_definitions["class_names"]
        self.best_model: str = self.manifest["best_model_by_test_macro_f1"]

        self.tree_pre = joblib.load(MODELS_DIR / "preprocessor_tree.joblib")
        self.models: dict[str, Any] = {
            "random_forest": joblib.load(MODELS_DIR / "random_forest_classifier.joblib"),
            "xgboost": joblib.load(MODELS_DIR / "xgboost_classifier.joblib"),
        }

    @property
    def available_models(self) -> list[str]:
        return list(self.models.keys())

    def resolve_model_name(self, name: str) -> str:
        return self.best_model if name in ("best_model", "best") else name

    def model_label(self, name: str) -> str:
        resolved = self.resolve_model_name(name)
        return CLF_MODEL_LABELS.get(resolved, resolved)

    # ── Warnings (same semantics as ModelService.check_input_warnings) ─────────

    def check_input_warnings(self, row: dict[str, Any]) -> list[str]:
        warnings: list[str] = []
        for c in self.numeric_and_binary:
            v = row.get(c)
            if v is None:
                continue
            rng = self.schema["numeric_ranges"].get(c)
            try:
                v = float(v)
            except (TypeError, ValueError):
                continue
            if rng and not (rng["min"] <= v <= rng["max"]):
                warnings.append(f"'{c}' = {v} is outside the training range [{rng['min']:.2f}, {rng['max']:.2f}]")
        for c in self.categorical_cols:
            v = row.get(c)
            if v is None:
                continue
            options = self.schema["categorical_options"].get(c, [])
            if str(v) not in options:
                warnings.append(f"'{c}' = {v!r} was never seen in training (unseen category)")
        return warnings

    def _row_to_frame(self, row: dict[str, Any]) -> pd.DataFrame:
        full = {c: row.get(c) for c in self.feature_cols}
        return pd.DataFrame([full])

    # ── Prediction ───────────────────────────────────────────────────────────

    def predict_one(self, model_name: str, row: dict[str, Any]) -> dict[str, Any]:
        resolved = self.resolve_model_name(model_name)
        if resolved not in self.models:
            raise ValueError(f"Unknown or unavailable classifier: {resolved}")
        model = self.models[resolved]
        df = self._row_to_frame(row)
        X = self.tree_pre.transform(df[self.numeric_and_binary + self.categorical_cols])

        raw_pred = model.predict(X)[0]
        proba_raw = model.predict_proba(X)[0]

        if resolved == "xgboost":
            # XGBClassifier was trained on integer class indices (0/1/2).
            predicted_class = self.class_names[int(raw_pred)]
            class_order = self.class_names
        else:
            # RandomForestClassifier's classes_ is alphabetically sorted
            # ("High"/"Low"/"Medium"), not Low/Medium/High -- map explicitly
            # so probabilities line up with self.class_names in order.
            predicted_class = str(raw_pred)
            class_order = [str(c) for c in model.classes_]

        probabilities = {
            cls: float(proba_raw[class_order.index(cls)]) if cls in class_order else 0.0
            for cls in self.class_names
        }

        return {
            "model": resolved, "model_label": self.model_label(resolved),
            "predicted_class": predicted_class,
            "probabilities": probabilities,
            "warnings": self.check_input_warnings(row),
        }

    def predict_many(self, model_name: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results = []
        for i, cand in enumerate(candidates):
            row = {k: v for k, v in cand.items() if k != "name"}
            res = self.predict_one(model_name, row)
            res["candidate_name"] = cand.get("name") or f"Candidate {i + 1}"
            res["row"] = row
            results.append(res)
        # Rank High -> Medium -> Low, using prediction confidence as a tiebreaker within a class.
        order = {cls: i for i, cls in enumerate(self.class_names)}
        results.sort(key=lambda r: (-order[r["predicted_class"]], -r["probabilities"][r["predicted_class"]]))
        return results
