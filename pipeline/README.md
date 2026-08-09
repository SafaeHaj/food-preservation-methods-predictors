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
| PDF structure | Docling (figures, tables, captions, page images) |
| Charts | PP-Chart2Table (figure → CSV) |
| Data extraction | A deterministic schema gate + controlled vocabulary; see below |
| LLM | Ollama by default; OpenAI / Anthropic / Groq / Gemini by config |
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

### The LLM is not where the numbers come from

A deterministic **schema gate** decides which tables and figures hold a data series, a
**controlled vocabulary** (`extraction/config/vocabulary.yaml`) resolves every name and
unit, and the backend assembles and validates each record. The model is asked for exactly
two things:

* `treatment` and `weight_g`, which exist only as prose in a methods section;
* which column is the axis, on a table the gate could not key — a *column name*, never a
  value, fed back into the gate so it re-reads the table itself.

Two consequences worth knowing. With no provider configured the pipeline still produces
every measurement, ingredient, indicator and dose; it loses only the protocol prose. And
changing provider cannot change a number — `extraction/tests/test_pipeline.py` asserts
exactly that.

### Switching to a paid API

Two lines in `.env`, because model and base URL default per provider:

```bash
EXTRACTION_LLM_PROVIDER=anthropic     # ollama | openai | anthropic | groq | gemini
EXTRACTION_ANTHROPIC_API_KEY=sk-ant-…
```

`GET /health` on the extraction service reports which model would answer and whether it is
reachable, so a switch is verifiable without running a paper through.

Adding a fifth provider is one file in `extraction/app/services/llm/providers/` and one row
in `registry.PROVIDER_DEFAULTS`. No pipeline module names a vendor.

### Changing the schema

`shared/shared/schemas/science.py` is the single edit point: the controlled vocabularies
and the Pydantic records both live there, and `shared/db/models.py` builds its `CHECK`
constraints from the same tuples. Editing a vocabulary means writing an Alembic revision
that resyncs those constraints — `shared/tests/test_check_constraints.py` fails on the same
commit if you forget, because `alembic --autogenerate` cannot detect CHECK drift.

---

## Workflow

```
1. Create a project (defines the extraction schema)
       ↓
2. Upload PDFs
       ↓
3. Docling extraction  — figures, tables, captions and context links into the workspace,
                         then the schema gate decides which of them hold a data series
                         (`GET .../gate-report` says what it decided about each, and why)
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
├── extraction/         # :8001 — papers, Docling workspace, assets, the medallion pipeline
│   ├── app/services/silver/   # clean, gate, convert charts, resolve names — no LLM, no SQL
│   ├── app/services/gold/     # assemble validated records, ask for the two prose fields
│   ├── app/services/llm/      # the one provider seam; providers/ holds one file each
│   └── config/vocabulary.yaml # the controlled vocabulary: data, not code
├── processing/         # :8002 — flattens the scientific schema into a training dataset,
│                       #         and drives prediction. Dataset builder is still a stub.
├── prediction/         # :8100 — survival engines (Weibull-AFT / RSF / GBS) + R frailtypack.
│                       #         Standalone: its own DB and models, no `shared` dependency.
├── shared/             # installed into gateway/extraction/processing as `shared`
│   ├── shared/schemas/science.py  # THE schema seam: vocabularies + records, one edit point
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
