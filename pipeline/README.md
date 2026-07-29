# Food Research Platform

A microservice platform for food science research teams: extract structured data from
scientific PDFs, curate it into a canonical experimental model, fit shelf-life models, and
export the result.

## Architecture

```
browser ──> gateway (:8000, the ONLY published app service; verifies the JWT once)
              ├──> extraction  (:8001)
              └──> processing  (:8002) ──> prediction (:8100)

            extraction-worker ┐
            processing-worker ┘── Celery over Redis

            all services share one Postgres
```

The gateway is the only service exposed to the browser. It authenticates the request once
and forwards the caller's identity to the internal services as `X-User-Id`; those services
do not re-verify tokens. `INTERNAL_SECRET` proves a request actually came through the
gateway — without it, the internal services trust that header from any caller.

Long-running work (Docling parses, LLM ingestion, model fitting, exports) runs in the Celery
workers, never in an API container. The gateway is the sole migration writer: it runs
`alembic upgrade head` before it starts serving.

| Layer | Technology |
|---|---|
| Frontend | React 18 + TypeScript + Vite + TailwindCSS |
| Gateway / services | FastAPI + SQLAlchemy |
| Database | PostgreSQL 16 (shared), Alembic migrations in `shared/alembic` |
| Async work | Celery + Redis |
| Auth | JWT (gateway only) + `INTERNAL_SECRET` between services |
| PDF structure | Docling (figures, tables, captions); PyMuPDF renders page previews |
| Charts | PP-Chart2Table (figure → CSV) |
| LLM extraction | Groq (`llama-3.3-70b-versatile` by default) |
| Modelling | Weibull-AFT / RSF / GBS, plus R `frailtypack` shared-frailty |

---

## Quick Start

Requires Docker with Compose v2. From `pipeline/`:

```bash
cp .env.example .env
# SECRET_KEY is required and has no default — generate one:
python -c "import secrets; print(secrets.token_urlsafe(48))"
# paste it into .env, then do the same for INTERNAL_SECRET
docker compose up --build
```

Then open **http://localhost:5173** and register an account.

The first build is slow — the prediction image compiles R's `frailtypack`, and the
extraction image pulls Docling's models.

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Gateway API | http://localhost:8000 |
| API docs | http://localhost:8000/docs |
| Postgres | `127.0.0.1:5432` (loopback only) |

Everything else (`extraction`, `processing`, `prediction`, both workers, Redis) is reachable
only on the internal compose network.

---

## Configuration

All settings live in `pipeline/.env`, and **[`.env.example`](.env.example) documents every
one of them** — it is the single source of truth, deliberately not duplicated here.

Two values have no working default:

- **`SECRET_KEY`** — required. Signs both JWTs and asset URLs, so every service must share
  the same value. Compose refuses to start without it.
- **`INTERNAL_SECRET`** — optional but strongly recommended. Empty means the internal
  services accept `X-User-Id` from any caller.

Anything omitted falls back to the default declared on the matching class in
`shared/shared/config/`.

Without `EXTRACTION_GROQ_API_KEY` the pipeline still runs Docling parsing, asset extraction
and chart conversion; it stops at the LLM step and reports that extraction is not
configured, rather than failing opaquely.

---

## Workflow

```
1. Create a project (defines the extraction schema)
       ↓
2. Upload PDFs
       ↓
3. Docling extraction  — figures, tables, captions and context links into the workspace
       ↓
4. Extracted Data      — see what came out, across every paper in the project
       ↓
5. Validation          — pick what goes to the LLM, then send it
       ↓
6. Scientific database — experiments, ingredients, indicators (set their thresholds here),
                         measurements, each traceable back to its place in the PDF
       ↓
7. Model lab           — flatten that into a training dataset
       ↓
8. Prediction          — fit shelf-life models and score new formulations
```

Steps 6-8 read one schema. There is no promotion step: what the LLM writes is what
everything downstream reads.

---

## Project structure

```
pipeline/
├── gateway/            # :8000 — auth, projects, members, jobs (SSE), audit; proxies the rest
├── extraction/         # :8001 — papers, Docling workspace, assets, LLM ingestion
│   └── app/services/   #   docling_pipeline, context_linker, chart_converter, evidence_*
├── processing/         # :8002 — flattens the scientific schema into a training dataset,
│                       #         and drives prediction. Dataset builder is still a stub.
├── prediction/         # :8100 — survival engines (Weibull-AFT / RSF / GBS) + R frailtypack.
│                       #         Standalone: its own DB and models, no `shared` dependency.
├── shared/             # installed into gateway/extraction/processing as `shared`
│   ├── shared/db/models.py    # platform + scientific schema (FK deletion policy documented here)
│   ├── shared/config/         # per-service settings classes
│   ├── shared/auth.py         # X-User-Id resolution + internal-secret guard
│   └── alembic/               # migrations — the gateway runs these on startup
├── frontend/           # React + Vite; pages/project/* is the per-project workspace
└── docker-compose.yml
```

---

## Common tasks

```bash
# Follow one service
docker compose logs -f extraction-worker

# Database shell
docker compose exec postgres psql -U food -d food_research

# Create a migration after changing shared/shared/db/models.py
docker compose exec gateway sh -c "cd /shared && alembic revision --autogenerate -m 'what changed'"

# Apply migrations by hand (the gateway does this on startup anyway)
docker compose exec gateway sh -c "cd /shared && alembic upgrade head"

# Rebuild one service after a dependency change
docker compose up -d --build extraction

# Reset the database — DESTROYS ALL DATA
docker compose down -v
```

---

## Troubleshooting

**`SECRET_KEY must be set`** — you skipped `cp .env.example .env`, or left `SECRET_KEY`
empty. It has no default on purpose: a shipped default would be a shipped private key.

**Changed `POSTGRES_PASSWORD` and now nothing connects** — the password is baked into the
`pgdata` volume when Postgres first initialises. Changing the variable afterwards does not
change the real password. Either `docker compose down -v` (destroys the data) or `ALTER
USER` inside the container.

**A service logs "INTERNAL_SECRET is not set: this service trusts X-User-Id from any
caller"** — expected when `INTERNAL_SECRET` is empty. Set it in `.env` and restart.

**Port 5432 already in use** — set `POSTGRES_PORT` in `.env`. Postgres is bound to
`127.0.0.1` only; it is not reachable from other machines.

**Extraction stops before the LLM step** — `EXTRACTION_GROQ_API_KEY` is unset. Docling
parsing and chart conversion still work.

**Health** — `docker compose ps` shows the health of every service. The gateway takes
longest to become healthy because it runs the migrations first.
