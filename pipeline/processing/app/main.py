"""Processing service -- everything the pipeline knows about food science.

Extraction reads documents and stops: Docling, PP-Chart2Table, and a deterministic schema
gate that decides which tables and figures hold a series. It stages a gated package of raw
(axis, label, value) observations whose labels are still unresolved.

This service resolves them. It owns:

  * the controlled vocabulary -- which string means "Total viable count", which units are
    equivalent, which quantities are deliberately discarded;
  * the LLM seam, and both calls that use it: naming the axis of a table the gate could not
    key, and reading `treatment` and `weight_g` out of a methods section;
  * record assembly and validation into the scientific schema;
  * enrichment from PubChem and USDA FoodData Central;
  * the flat dataset the prediction service trains on.

The model is never asked for a number. Every value written here was read off a table or a
converted chart by the gate, resolved by the vocabulary, and validated before the database
saw it -- which is why a change of provider moves two prose fields and nothing else.

Internal service: reached only through the gateway, which has already authenticated the
caller and forwards the identity as `X-User-Id` (see `shared.auth`).

Survival training and prediction are delegated onward to the prediction service over HTTP
(`app/services/survival_trainer.py`); this service owns no ML of its own.
"""

from fastapi import FastAPI

from shared.auth import install_internal_secret_guard
from shared.config import get_common_settings
from shared.error_handlers import install_exception_handlers
from shared.logging import configure_logging, install_request_id_middleware

from app.api.routes import dataset, ingestion, prediction, science

_settings = get_common_settings()
configure_logging("processing", _settings.LOG_LEVEL)

app = FastAPI(
    title="Processing Service",
    description=(
        "Resolves extracted documents into the scientific schema, enriches them from "
        "external sources, and builds the dataset prediction trains on."
    ),
    version="4.0.0",
)

install_request_id_middleware(app)
install_internal_secret_guard(app)
install_exception_handlers(app)

for router in (dataset.router, ingestion.router, prediction.router, science.router):
    app.include_router(router, prefix="/api")


@app.get("/health")
def health():
    """Liveness, plus which model would answer and whether it can be reached.

    The LLM probe is what makes a provider switch verifiable: one call says whether the
    key, the base URL and the model id agree, instead of the first paper of a run finding
    out. It never raises -- a provider that is down makes ingestion degrade, not the
    service unhealthy -- and is skipped when the client cannot be constructed at all.
    """
    from app.services.llm import LLMUnavailable, get_llm_client

    try:
        llm = get_llm_client().probe().as_dict()
    except LLMUnavailable as exc:
        llm = {"reachable": False, "detail": exc.message, **exc.details}

    return {"status": "ok", "service": "processing", "llm": llm}
