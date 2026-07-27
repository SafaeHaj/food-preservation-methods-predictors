"""Processing service -- canonical curation, kinetics, thresholds and the model lab.

Internal service: reached only through the gateway, which has already authenticated the
caller and forwards the identity as `X-User-Id` (see `shared.auth`).

Survival training and prediction are delegated onward to the prediction service over HTTP
(`app/services/survival_trainer.py`); this service owns no survival ML of its own.
"""

from fastapi import FastAPI

from shared.auth import install_internal_secret_guard
from shared.config import get_common_settings
from shared.error_handlers import install_exception_handlers
from shared.logging import configure_logging, install_request_id_middleware

from app.api.routes import (
    experiments, imputations, microorganisms, model_lab, normalization, observations,
    snapshots, studies, thresholds, trajectories, treatment_arms,
)

_settings = get_common_settings()
configure_logging("processing", _settings.LOG_LEVEL)

app = FastAPI(
    title="Processing Service",
    description=(
        "Canonical hierarchy, normalization, trajectories and kinetics, thresholds, "
        "snapshots and exports, and the model lab."
    ),
    version="2.0.0",
)

install_request_id_middleware(app)
install_internal_secret_guard(app)
install_exception_handlers(app)

for router in (
    studies.router, experiments.router, treatment_arms.router, observations.router,
    microorganisms.router, normalization.router, trajectories.router, imputations.router,
    thresholds.router, snapshots.router, model_lab.router,
):
    app.include_router(router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok", "service": "processing"}
