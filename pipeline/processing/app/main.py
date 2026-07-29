"""Processing service -- the seam between extraction and prediction.

It picks up where the extraction pipeline leaves off. Extraction owns papers, the workspace
and the validation step that sends a curated selection to the LLM; what comes back are the
five scientific tables. This service reads those and turns them into a flat dataset the
prediction service can train on. Nothing in the extraction flow changes because of it.

Internal service: reached only through the gateway, which has already authenticated the
caller and forwards the identity as `X-User-Id` (see `shared.auth`).

It previously owned a second copy of the science -- studies, experiments, treatment arms,
observations, trajectories, kinetic fits, imputations, thresholds, snapshots, exports and a
CSV-upload model lab -- built on tables that only a promoter ever wrote to, transcribing the
extraction output into a parallel shape. That whole hierarchy is gone; the extraction output
*is* the schema now, and this service reads it directly.

Survival training and prediction are delegated onward to the prediction service over HTTP
(`app/services/survival_trainer.py`); this service owns no ML of its own.
"""

from fastapi import FastAPI

from shared.auth import install_internal_secret_guard
from shared.config import get_common_settings
from shared.error_handlers import install_exception_handlers
from shared.logging import configure_logging, install_request_id_middleware

from app.api.routes import dataset, prediction

_settings = get_common_settings()
configure_logging("processing", _settings.LOG_LEVEL)

app = FastAPI(
    title="Processing Service",
    description="Flattens the scientific schema into datasets and drives prediction.",
    version="3.0.0",
)

install_request_id_middleware(app)
install_internal_secret_guard(app)
install_exception_handlers(app)

for router in (dataset.router, prediction.router):
    app.include_router(router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok", "service": "processing"}
