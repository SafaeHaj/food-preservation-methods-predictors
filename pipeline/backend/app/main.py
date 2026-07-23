import os as _os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.database import Base, engine, apply_column_migrations
from app.api.routes import (
    auth, projects, papers, extraction, review,
    analytics, export, schema, model_lab,
    food_extraction, extraction_workspace,
)
from app.api.routes import (
    studies, experiments, observations, microorganisms,
    treatment_arms, jobs, members, audit, normalization,
    trajectories, imputations, thresholds, snapshots,
)

Base.metadata.create_all(bind=engine)
apply_column_migrations()          # backfill new columns on existing SQLite DBs

app = FastAPI(
    title="Food Research Platform API",
    description="Scientific data management platform for food-science research.",
    version="2.0.0",
)

_allowed_origins_raw = _os.environ.get(
    "ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000"
).split(",")
_wildcard = "*" in _allowed_origins_raw

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _wildcard else _allowed_origins_raw,
    allow_credentials=False if _wildcard else True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Legacy routes ─────────────────────────────────────────────────────────
app.include_router(auth.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(papers.router, prefix="/api")
app.include_router(extraction.router, prefix="/api")
app.include_router(review.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(export.router, prefix="/api")
app.include_router(schema.router, prefix="/api")

# ── Canonical scientific model ────────────────────────────────────────────
app.include_router(studies.router, prefix="/api")
app.include_router(experiments.router, prefix="/api")
app.include_router(treatment_arms.router, prefix="/api")
app.include_router(observations.router, prefix="/api")
app.include_router(microorganisms.router, prefix="/api")

# ── Collaboration ─────────────────────────────────────────────────────────
app.include_router(members.router, prefix="/api")
app.include_router(audit.router, prefix="/api")

# ── Normalization & quality ───────────────────────────────────────────────
app.include_router(normalization.router, prefix="/api")

# ── Analysis ──────────────────────────────────────────────────────────────
app.include_router(trajectories.router, prefix="/api")
app.include_router(imputations.router, prefix="/api")
app.include_router(thresholds.router, prefix="/api")

# ── Infrastructure ────────────────────────────────────────────────────────
app.include_router(jobs.router, prefix="/api")
app.include_router(snapshots.router, prefix="/api")

# ── Model Lab ─────────────────────────────────────────────────────────────────
app.include_router(model_lab.router, prefix="/api")

# ── Food-safety extraction (new schema) ───────────────────────────────────────
app.include_router(food_extraction.router, prefix="/api")

# ── Extraction Workspace ───────────────────────────────────────────────────────
app.include_router(extraction_workspace.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "Food Research Platform", "version": "2.0.0"}
