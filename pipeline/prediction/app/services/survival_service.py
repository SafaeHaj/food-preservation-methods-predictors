"""Survival train/predict orchestration for the model-lab flat-table path.

This is the service the processing/model-lab layer calls (over HTTP) to *replace* the
colleague's ``survival_trainer``. It fits the three survival engines
(``weibull_aft`` / ``rsf`` / ``gbs``) on a flat uploaded dataset, persists each fitted model
as an artifact, and returns a result dict shaped exactly like the one the model-lab
``_bg_train`` background task already consumes -- so no BFF contract changes.

Engine availability is honoured per-engine: a missing optional backend (``scikit-survival``,
``xgboost``) or a fit failure is recorded as ``skipped`` / ``failed`` with a reason, never
sinking the whole run. R + ``frailtypack`` (Weibull stage 2) is used when configured and
available, falling back to the Python stage-1 refit otherwise.
"""

from __future__ import annotations

import importlib.util
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from app.core.config import REPO_ROOT, Config, get_config, get_settings
from app.prediction.flat import FlatDesign, build_flat_design
from app.prediction.models.cv import grouped_cv_score
from app.prediction.models.gbs import GradientBoostedSurvivalEngine
from app.prediction.models.r_frailty import RNotAvailableError
from app.prediction.models.rsf import RandomSurvivalForestEngine
from app.prediction.models.weibull_aft import WeibullAFTEngine

#: The survival engines exposed to the model lab. R-frailty is Weibull stage 2, not its own row.
ENGINE_NAMES = ("weibull_aft", "rsf", "gbs")

#: Below this many usable rows, survival modelling is not meaningful.
MIN_ROWS = 10


def _artifact_dir() -> Path:
    d = Path(get_settings().survival_artifact_dir)
    if not d.is_absolute():
        d = REPO_ROOT / d
    d.mkdir(parents=True, exist_ok=True)
    return d


def _service_config() -> Config:
    """Base config with runtime-speed overrides suitable for an interactive service.

    These trim wall-clock cost on the small datasets the model lab handles; they are speed
    choices, not model-behaviour changes. ``use_r_frailty`` is left as configured (true in
    the container image, which bakes in R + frailtypack).
    """
    cfg = get_config()
    m = cfg.model
    waft = replace(
        m.weibull_aft,
        lambda_path_length=min(m.weibull_aft.lambda_path_length, 15),
        max_iter=min(m.weibull_aft.max_iter, 1000),
        tol=max(m.weibull_aft.tol, 1e-6),
    )
    unc = replace(m.uncertainty, n_boot=min(m.uncertainty.n_boot, 60))
    return cfg.with_overrides(model=replace(m, weibull_aft=waft, uncertainty=unc))


def _sksurv_available() -> bool:
    return importlib.util.find_spec("sksurv") is not None


def _frailty_off(cfg: Config) -> Config:
    """Copy of ``cfg`` with the Weibull R-frailty (stage 2) disabled."""
    m = cfg.model
    return cfg.with_overrides(
        model=replace(m, weibull_aft=replace(m.weibull_aft, use_r_frailty=False))
    )


class SurvivalTrainingService:
    """Fit every engine on a flat dataset and persist the artifacts."""

    def __init__(self, config: Config | None = None, artifact_dir: Path | None = None) -> None:
        self.config = config or _service_config()
        self.artifact_dir = artifact_dir or _artifact_dir()

    # -- public entry point ------------------------------------------------------------

    def train(self, records: list[dict], mapping: dict[str, str]) -> dict[str, Any]:
        try:
            design = build_flat_design(records, mapping)
        except ValueError as exc:
            return {"error": str(exc)}
        if design.n_rows < MIN_ROWS:
            return {"error": f"Too few valid rows ({design.n_rows}) for survival modelling. Need >= {MIN_ROWS}."}

        models = {name: self._fit_one(name, design) for name in ENGINE_NAMES}
        completed = [m for m in models.values() if m.get("status") == "completed"]
        best = max(
            (m for m in completed if m.get("concordance_index") is not None),
            key=lambda m: m["concordance_index"],
            default=None,
        )
        return {
            "n_rows": design.n_rows,
            "n_train": design.n_rows,
            "n_test": 0,
            "event_rate": float(np.mean(design.y_event)),
            "time_col": design.time_col,
            "event_col": design.event_col,
            "study_col": design.study_col,
            "feature_cols": design.feature_cols,
            "n_completed": len(completed),
            "best_model": _engine_of(best, models),
            "models": models,
        }

    # -- per-engine fit ----------------------------------------------------------------

    def _engine_factory(self, name: str, design: FlatDesign, config: Config | None = None):
        cfg = config or self.config
        feature_groups = np.arange(len(design.X.columns))
        group_names = list(design.X.columns)
        if name == "weibull_aft":
            return lambda: WeibullAFTEngine(cfg, feature_groups=feature_groups, group_names=group_names)
        if name == "rsf":
            return lambda: RandomSurvivalForestEngine(cfg)
        if name == "gbs":
            return lambda: GradientBoostedSurvivalEngine(cfg)
        raise KeyError(name)

    def _fit_config(self, name: str, design: FlatDesign) -> Config:
        """Full-fit config: disable Weibull R-frailty when there is no real study grouping.

        Without a mapped ``study_id`` the groups are per-row, and ``frailtyPenal`` on singleton
        clusters is unidentifiable -- it raises rather than converging, which would fail Weibull
        on most model-lab uploads. Frailty is only meaningful with >= 2 genuine studies.
        """
        cfg = self.config
        if name == "weibull_aft" and cfg.model.weibull_aft.use_r_frailty:
            has_studies = design.study_col is not None and len(np.unique(design.groups)) >= 2
            if not has_studies:
                cfg = _frailty_off(cfg)
        return cfg

    def _fit_one(self, name: str, design: FlatDesign) -> dict[str, Any]:
        cfg = self._fit_config(name, design)
        factory = self._engine_factory(name, design, cfg)
        try:
            model = factory()
            try:
                model.fit(design.X, design.y_time, design.y_event, groups=design.groups)
            except (RNotAvailableError, RuntimeError):
                # Weibull frailty stage failed (R missing, or non-convergent): keep the stage-1 refit
                # rather than failing the engine. A genuine stage-1 error re-raises on the retry.
                if name != "weibull_aft" or not cfg.model.weibull_aft.use_r_frailty:
                    raise
                cfg = _frailty_off(cfg)
                factory = self._engine_factory(name, design, cfg)
                model = factory()
                model.fit(design.X, design.y_time, design.y_event, groups=design.groups)
        except ImportError as exc:
            return {"status": "skipped", "reason": _dep_reason(name, exc)}
        except Exception as exc:  # noqa: BLE001 - per-engine isolation
            return {"status": "failed", "reason": f"{type(exc).__name__}: {exc}"}

        c_index = self._safe_c_index(name, design)
        model_ref = f"{name}_{uuid.uuid4().hex[:12]}"
        joblib.dump(
            {
                "engine_name": name,
                "model": model,
                "preprocessor": design.preprocessor,
                "columns": list(design.X.columns),
            },
            self.artifact_dir / f"{model_ref}.joblib",
        )
        return {
            "status": "completed",
            "concordance_index": c_index,
            "n_train": design.n_rows,
            "n_test": 0,
            "artifact_path": model_ref,
        }

    def _safe_c_index(self, name: str, design: FlatDesign) -> float | None:
        """Study-grouped CV C-index, or None when it cannot be computed (no sksurv / <2 groups).

        CV always uses the frailty-off Weibull: an R subprocess per fold is prohibitively slow,
        and the frailty shifts the scale, not the formulation ranking the C-index measures.
        """
        if not _sksurv_available():
            return None
        cfg = _frailty_off(self.config) if name == "weibull_aft" else self.config
        factory = self._engine_factory(name, design, cfg)
        try:
            cv = grouped_cv_score(
                factory, design.X, design.y_time, design.y_event, design.groups,
                n_splits=cfg.model.cv.n_splits, seed=cfg.model.cv.seed,
            )
            val = float(cv["mean_c_index"])
            return None if np.isnan(val) else val
        except Exception:  # noqa: BLE001 - CI is best-effort; a failure must not fail training
            return None


class SurvivalPredictionService:
    """Point + interval for a single formulation from a persisted artifact."""

    def __init__(self, artifact_dir: Path | None = None) -> None:
        self.artifact_dir = artifact_dir or _artifact_dir()

    def predict(
        self,
        model_ref: str,
        model_name: str,
        input_features: dict[str, Any],
        required_shelf_life: float | None = None,
    ) -> dict[str, Any]:
        path = self.artifact_dir / f"{model_ref}.joblib"
        if not path.exists():
            return {"error": f"Model artifact not found: {model_ref}"}
        try:
            bundle = joblib.load(path)
            model = bundle["model"]
            X = bundle["preprocessor"].transform(input_features)

            point = float(model.predict_point(X)[0])
            pred = model.predict(X)  # cheap analytic CI for Weibull; capped bootstrap for trees
            lo = float(pred.lower[0])
            hi = float(pred.upper[0])
            lo, hi = (min(lo, hi), max(lo, hi))

            result: dict[str, Any] = {
                "model_name": model_name,
                "predicted_shelf_life_days": round(point, 2),
                "ci_lo_days": round(lo, 2),
                "ci_hi_days": round(hi, 2),
            }
            if required_shelf_life is not None:
                result["required_shelf_life_days"] = required_shelf_life
                result["success"] = bool(point >= required_shelf_life)
            return result
        except Exception as exc:  # noqa: BLE001 - surface as an error field, matching the BFF contract
            return {"error": f"{type(exc).__name__}: {exc}"}


def _dep_reason(name: str, exc: ImportError) -> str:
    hint = {
        "rsf": "scikit-survival not installed (pip install scikit-survival)",
        "gbs": "xgboost not installed (pip install xgboost)",
    }.get(name)
    return hint or f"missing dependency: {exc}"


def _engine_of(entry: dict | None, models: dict[str, dict]) -> str | None:
    if entry is None:
        return None
    for name, m in models.items():
        if m is entry:
            return name
    return None
