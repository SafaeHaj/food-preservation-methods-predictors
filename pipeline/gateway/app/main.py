"""Gateway / BFF -- the only publicly exposed service.

Terminates the SPA's `/api` surface, verifies the JWT exactly once, and either serves the
platform-domain routes it owns (auth, projects, members, jobs, audit) or proxies to the
domain service that owns the path.

The schema is owned by Alembic (`pipeline/shared/alembic`) and applied by this service's
start command before uvicorn runs. There is no `create_all`: it would race the migrations
and silently diverge from the migration history.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.config import get_common_settings, get_gateway_settings
from shared.error_handlers import install_exception_handlers
from shared.logging import configure_logging, install_request_id_middleware

from app.api.routes import audit, auth, jobs, members, projects
from app.proxy import router as proxy_router

_common = get_common_settings()
_settings = get_gateway_settings()
configure_logging("gateway", _common.LOG_LEVEL)

app = FastAPI(
    title="Food Research Platform API",
    description="Gateway for the food-science research platform (auth, platform domain, routing).",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _settings.allow_all_origins else _settings.ALLOWED_ORIGINS,
    # Credentials cannot be combined with a wildcard origin; the browser rejects it.
    allow_credentials=not _settings.allow_all_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

install_request_id_middleware(app)
install_exception_handlers(app)

# ── Platform domain (owned by the gateway) ────────────────────────────────────
for router in (auth.router, projects.router, members.router, jobs.router, audit.router):
    app.include_router(router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "gateway", "version": app.version}


# ── Catch-all proxy (registered LAST so owned routes match first) ─────────────
app.include_router(proxy_router)
