"""Processing-service settings: exports, model lab, prediction-service client."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.config.base import storage_path, storage_subpath


class ProcessingSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        env_prefix="PROCESSING_",
    )

    #: Its own volume, not part of the uploads tree -- resolved against BASE_DIR.
    EXPORT_DIR: str = "exports"
    #: On the shared uploads volume: relative, resolved by `storage_subpath` against
    #: STORAGE_DIR so the API and the Celery worker see the same files.
    DATASET_DIR: str = "datasets"
    MODEL_ARTIFACT_DIR: str = "model_artifacts"

    # ── Prediction service (survival training/prediction is delegated) ────────
    PREDICTION_SERVICE_URL: str = "http://prediction:8100"
    #: A Weibull-AFT fit with an R-frailty second stage can legitimately run for minutes.
    PREDICTION_TIMEOUT_SECONDS: float = 600.0

    # ── Model families ────────────────────────────────────────────────────────
    # The engine name lists were duplicated as literals in the training task, where they
    # had to be kept in lockstep with the prediction service by hand. Any drift left a
    # placeholder row stuck in "pending" forever.
    KINETIC_MODELS: list[str] = ["baranyi", "gompertz", "weibull_inact", "geeraerd"]
    SURVIVAL_MODELS: list[str] = ["weibull_aft", "rsf", "gbs"]

    # ── Dataset parsing ───────────────────────────────────────────────────────
    #: Rows read when inferring column types on upload (the full file is read at train time).
    DATASET_PREVIEW_ROWS: int = 2000
    #: Fraction of non-empty values that must parse as numbers to call a column numeric.
    NUMERIC_COLUMN_THRESHOLD: float = 0.80
    #: A column is categorical if it has at most this many distinct values, and they repeat.
    CATEGORICAL_MAX_DISTINCT: int = 20

    FILE_CHUNK_BYTES: int = 65536

    @property
    def export_path(self) -> Path:
        return storage_path(self.EXPORT_DIR)

    @property
    def dataset_path(self) -> Path:
        return storage_subpath(self.DATASET_DIR)

    @property
    def model_artifact_path(self) -> Path:
        return storage_subpath(self.MODEL_ARTIFACT_DIR)


@lru_cache
def get_processing_settings() -> ProcessingSettings:
    return ProcessingSettings()
