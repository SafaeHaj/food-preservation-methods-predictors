"""Processing-service settings: dataset staging and the prediction-service client."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.config.base import storage_subpath


class ProcessingSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        env_prefix="PROCESSING_",
    )

    #: On the shared uploads volume: relative, resolved by `storage_subpath` against
    #: STORAGE_DIR so the API and the Celery worker see the same files.
    DATASET_DIR: str = "datasets"
    MODEL_ARTIFACT_DIR: str = "model_artifacts"

    # ── Prediction service (training and inference are delegated) ─────────────
    PREDICTION_SERVICE_URL: str = "http://prediction:8100"
    #: A Weibull-AFT fit with an R-frailty second stage can legitimately run for minutes.
    PREDICTION_TIMEOUT_SECONDS: float = 600.0

    #: Engine names the prediction service exposes. Kept here rather than as literals at the
    #: call site: they were previously duplicated into the training task, where they had to
    #: be held in lockstep with the prediction service by hand, and any drift left a
    #: placeholder row stuck in "pending" forever.
    SURVIVAL_ENGINES: list[str] = ["weibull_aft", "rsf", "gbs"]

    @property
    def dataset_path(self) -> Path:
        return storage_subpath(self.DATASET_DIR)

    @property
    def model_artifact_path(self) -> Path:
        return storage_subpath(self.MODEL_ARTIFACT_DIR)


@lru_cache
def get_processing_settings() -> ProcessingSettings:
    return ProcessingSettings()
