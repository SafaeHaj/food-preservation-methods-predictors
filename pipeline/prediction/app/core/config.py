"""Application settings and the typed ML configuration.

`Settings` exposes environment-driven app config (from `.env`); `load_config` loads the
layered YAML under `config/` (base overlaid with the active environment) into the typed
`Config` used by the prediction pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

# Service root = the dir holding app/, config/, data/ (i.e. .../app/core/config.py -> parents[2]).
REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"
DEFAULT_CONFIG_PATH = CONFIG_DIR / "base.yaml"


@dataclass(frozen=True)
class PillarConfig:
    leaf_to_tier: dict[str, str]
    output_level: Literal["leaf", "tier", "both"] = "leaf"
    unmapped_bucket: str = "Unmapped"
    unmapped_policy: Literal["bucket", "error"] = "bucket"

    @property
    def leaves(self) -> list[str]:
        return list(self.leaf_to_tier)

    @property
    def tiers(self) -> list[str]:
        return sorted(set(self.leaf_to_tier.values()))
    

    def tier_of(self, leaf: str) -> str | None:
        return self.leaf_to_tier.get(leaf)

@dataclass(frozen=True)
class CoverageConfig:
    min_support_studies: int = 3
    min_support_events: int = 2
    action: Literal["drop", "flag"] = "drop"


@dataclass(frozen=True)
class FeatureConfig:
    context_columns: list[str] = field(default_factory=lambda: ["meat_matrix", "treatment"])
    interactions: dict[str, bool] = field(default_factory=dict)
    coverage: CoverageConfig = field(default_factory=CoverageConfig)
    standardize: bool = True


@dataclass(frozen=True)
class CVConfig:
    n_splits: int = 5
    seed: int = 0


@dataclass(frozen=True)
class UncertaintyConfig:
    level: float = 0.95
    method: Literal["analytic", "bootstrap"] = "analytic"
    n_boot: int = 200
    resample_unit: Literal["study", "row"] = "study"


@dataclass(frozen=True)
class WeibullAFTConfig:
    lambda_path_length: int = 25
    lambda_min_ratio: float = 0.01
    max_iter: int = 2000
    tol: float = 1e-7
    use_r_frailty: bool = True


@dataclass(frozen=True)
class TreeEngineConfig:
    include_experiment_id_as_feature: bool = False
    rsf: dict[str, Any] = field(default_factory=dict)
    gbs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelConfig:
    engine: str = "weibull_aft"
    cv: CVConfig = field(default_factory=CVConfig)
    uncertainty: UncertaintyConfig = field(default_factory=UncertaintyConfig)
    weibull_aft: WeibullAFTConfig = field(default_factory=WeibullAFTConfig)
    tree_engines: TreeEngineConfig = field(default_factory=TreeEngineConfig)


@dataclass(frozen=True)
class RConfig:
    rscript_path: str | None = None
    lib_path: str | None = None
    timeout_seconds: int = 600


@dataclass(frozen=True)
class Config:
    pillars: PillarConfig
    features: FeatureConfig
    model: ModelConfig
    r: RConfig

    def with_overrides(self, **sections: Any) -> Config:
        """Return a copy with whole sections replaced."""
        current = {
            "pillars": self.pillars,
            "features": self.features,
            "model": self.model,
            "r": self.r,
        }
        unknown = set(sections) - set(current)
        if unknown:
            raise ValueError(f"unknown config section(s): {sorted(unknown)}")
        current.update(sections)
        return Config(**current)


def load_config(path: str | Path | None = None, environment: str | None = None) -> Config:
    """Load the layered YAML config into the typed `Config`.

    With no explicit `path`, `config/base.yaml` is overlaid with
    `config/{environment}.yaml` (environment from the argument or `Settings`).
    """
    if path is not None:
        return _parse(yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {})
    if not DEFAULT_CONFIG_PATH.exists():
        raise FileNotFoundError(f"config not found: {DEFAULT_CONFIG_PATH}")
    raw = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    env = environment or get_settings().environment
    override = CONFIG_DIR / f"{env}.yaml"
    if override.exists():
        raw = _deep_merge(raw, yaml.safe_load(override.read_text(encoding="utf-8")) or {})
    return _parse(raw)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively overlay `override` onto `base`, returning a new dict."""
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _parse(raw: dict[str, Any]) -> Config:
    p = raw.get("pillars", {})
    leaf_to_tier = p.get("leaf_to_tier") or {}
    if not leaf_to_tier:
        raise ValueError("pillars.leaf_to_tier must not be empty")
    output_level = p.get("output_level", "leaf")
    if output_level not in ("leaf", "tier", "both"):
        raise ValueError(f"pillars.output_level must be leaf|tier|both, got {output_level!r}")
    unmapped_policy = p.get("unmapped_policy", "bucket")
    if unmapped_policy not in ("bucket", "error"):
        raise ValueError(f"pillars.unmapped_policy must be bucket|error, got {unmapped_policy!r}")
    pillars = PillarConfig(
        leaf_to_tier=dict(leaf_to_tier),
        output_level=output_level,
        unmapped_bucket=p.get("unmapped_bucket", "Unmapped"),
        unmapped_policy=unmapped_policy,
    )

    f = raw.get("features", {})
    cov = f.get("coverage", {})
    action = cov.get("action", "drop")
    if action not in ("drop", "flag"):
        raise ValueError(f"features.coverage.action must be drop|flag, got {action!r}")
    features = FeatureConfig(
        context_columns=list(f.get("context_columns") or ["meat_matrix", "treatment"]),
        interactions=dict(f.get("interactions") or {}),
        coverage=CoverageConfig(
            min_support_studies=int(cov.get("min_support_studies", 3)),
            min_support_events=int(cov.get("min_support_events", 2)),
            action=action,
        ),
        standardize=bool(f.get("standardize", True)),
    )

    m = raw.get("model", {})
    unc = m.get("uncertainty", {})
    method = unc.get("method", "analytic")
    if method not in ("analytic", "bootstrap"):
        raise ValueError(f"model.uncertainty.method must be analytic|bootstrap, got {method!r}")
    resample_unit = unc.get("resample_unit", "study")
    if resample_unit not in ("study", "row"):
        raise ValueError(
            f"model.uncertainty.resample_unit must be study|row, got {resample_unit!r}"
        )
    waft = m.get("weibull_aft", {})
    trees = m.get("tree_engines", {})
    model = ModelConfig(
        engine=m.get("engine", "weibull_aft"),
        cv=CVConfig(**(m.get("cv") or {})),
        uncertainty=UncertaintyConfig(
            level=float(unc.get("level", 0.95)),
            method=method,
            n_boot=int(unc.get("n_boot", 200)),
            resample_unit=resample_unit,
        ),
        weibull_aft=WeibullAFTConfig(
            lambda_path_length=int(waft.get("lambda_path_length", 25)),
            lambda_min_ratio=float(waft.get("lambda_min_ratio", 0.01)),
            max_iter=int(waft.get("max_iter", 2000)),
            tol=float(waft.get("tol", 1e-7)),
            use_r_frailty=bool(waft.get("use_r_frailty", True)),
        ),
        tree_engines=TreeEngineConfig(
            include_experiment_id_as_feature=bool(
                trees.get("include_experiment_id_as_feature", False)
            ),
            rsf=dict(trees.get("rsf") or {}),
            gbs=dict(trees.get("gbs") or {}),
        ),
    )

    r = raw.get("r", {}) or {}
    rcfg = RConfig(
        rscript_path=r.get("rscript_path"),
        lib_path=r.get("lib_path"),
        timeout_seconds=int(r.get("timeout_seconds", 600)),
    )

    return Config(pillars=pillars, features=features, model=model, r=rcfg)


class Settings(BaseSettings):
    """Environment-driven application settings, sourced from `.env`."""

    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    environment: str = "development"
    database_url: str = "sqlite:///./data/processed/shelflife.db"
    #: Shared with the gateway and `processing`; proves a request came through the gateway.
    #: Empty disables the check (see `app.core.security`).
    internal_secret: str = ""
    api_title: str = "Shelf-life API"
    api_version: str = "0.1.0"
    log_level: str = "INFO"
    #: Where fitted survival model artifacts are written. Relative paths resolve against the
    #: service root (REPO_ROOT); override with an absolute path (e.g. a mounted volume) in prod.
    survival_artifact_dir: str = "data/artifacts"


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_config() -> Config:
    return load_config()
