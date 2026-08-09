"""Extraction service -- PDF ingestion, the Docling workspace, and the schema gate.

It reads documents and stops. Everything with food-science meaning -- the vocabulary, the
LLM, record assembly -- belongs to the processing service, which picks up the gated package
this one stages.

Internal service: reached only through the gateway, which has already authenticated the
caller and forwards the identity as `X-User-Id` (see `shared.auth`). The one exception is
signed binary-asset URLs, which carry their own proof (`shared.signing`).
"""

from fastapi import FastAPI

from shared.auth import install_internal_secret_guard
from shared.config import get_common_settings
from shared.error_handlers import install_exception_handlers
from shared.logging import configure_logging, install_request_id_middleware

from app.api.routes import papers, schema, workspace

_settings = get_common_settings()
configure_logging("extraction", _settings.LOG_LEVEL)

app = FastAPI(
    title="Extraction Service",
    description="Papers, the Docling workspace, assets and the deterministic schema gate.",
    version="3.0.0",
)

install_request_id_middleware(app)
install_internal_secret_guard(app)
install_exception_handlers(app)

app.include_router(papers.router, prefix="/api")
app.include_router(workspace.router, prefix="/api")
app.include_router(schema.router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok", "service": "extraction"}
