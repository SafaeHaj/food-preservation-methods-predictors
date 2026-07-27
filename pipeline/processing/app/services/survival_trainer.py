"""Survival / AFT training and prediction, delegated to the prediction microservice.

The prediction service owns the engines (Weibull-AFT / RSF / GBS / R-frailty) and the
fitted artifacts. These two functions are the seam.

They used to return `{"error": "..."}` on failure, which every caller had to remember to
check by hand -- and the ones that forgot recorded a successful training run with no
models. Failures now raise `UpstreamServiceError`, which the centralized handler renders as
the same error envelope as everything else, and which aborts the training transaction
rather than half-committing it.

`artifact_path` is an opaque model reference the prediction service understands. It is
stored verbatim and handed back at predict time; nothing here interprets it.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from shared.config import get_common_settings, get_processing_settings
from shared.http import InternalServiceClient


@lru_cache
def _client() -> InternalServiceClient:
    settings = get_processing_settings()
    return InternalServiceClient(
        settings.PREDICTION_SERVICE_URL,
        service_name="prediction",
        timeout=settings.PREDICTION_TIMEOUT_SECONDS,
        internal_secret=get_common_settings().INTERNAL_SECRET,
    )


def run_survival_training(records: list[dict], mapping: dict[str, str]) -> dict[str, Any]:
    """Fit the survival engines on a flat dataset.

    Returns {"models": {engine: {status, concordance_index, n_train, n_test, reason?,
    artifact_path}}, "feature_cols", "time_col", "event_col"}.
    """
    return _client().post("/api/v1/survival/train", {"records": records, "mapping": mapping})


def predict_survival(
    artifact_path: str,
    model_name: str,
    input_features: dict[str, Any],
    required_shelf_life: float | None = None,
) -> dict[str, Any]:
    """Predict shelf life for one formulation from a persisted survival model."""
    return _client().post(
        "/api/v1/survival/predict",
        {
            "model_ref": artifact_path,
            "model_name": model_name,
            "input_features": input_features,
            "required_shelf_life": required_shelf_life,
        },
    )
