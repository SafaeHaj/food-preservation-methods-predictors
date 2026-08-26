# Food Research Platform

**Collaborators:** Safae Hajjout, Zyad Fri
**Supervisors:** Pr. Loubna Benabbou, Pr. Salwa Karboune

**Institutions:** McGill University, Université du Québec à Rimouski (UQAR), UM6P College of Computing

This repository contains a food-science research platform designed to extract structured data from scientific PDFs, normalize it into a canonical experimental schema, and use it for predictive modeling and shelf-life analysis.

## Overview

This project brings together:

- PDF extraction and document parsing
- structured scientific data collection
- controlled vocabularies and validation
- food research data modeling
- predictive survival analysis for formulations and shelf-life studies

## Architecture

The system is organized as a microservice platform under `pipeline/`:

```text
browser
  └── gateway (:8000)
        ├── extraction (:8001)
        ├── processing (:8002)
        └── prediction (:8100)

Celery workers + Redis handle long-running jobs
A shared PostgreSQL database is used across services
```

Key design choices in the current codebase:

- The gateway is the only public-facing service.
- Internal services trust the forwarded `X-User-Id` header only when `INTERNAL_SECRET` is valid.
- Long-running tasks are handled by Celery workers rather than API containers.
- The gateway runs Alembic migrations before serving requests.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + TypeScript + Vite + TailwindCSS |
| API services | FastAPI + SQLAlchemy |
| Database | PostgreSQL 16 |
| Async jobs | Celery + Redis |
| PDF processing | Docling |
| Chart extraction | PP-Chart2Table |
| LLM integration | Ollama by default; provider-based support for OpenAI, Anthropic, Groq, Gemini |
| Modeling | Survival models, including Weibull-AFT / RSF / GBS and R `frailtypack` |

## Repository structure

```text
.
├── README.md
├── requirements.txt
├── data/
├── misc/
├── scripts/
└── pipeline/
    ├── docker-compose.yml
    ├── .env.example
    ├── frontend/
    ├── gateway/
    ├── extraction/
    ├── processing/
    ├── prediction/
    ├── shared/
    └── uploads/
```

Main runtime services in `pipeline/`:

```text
pipeline/
├── gateway/      # public API and auth layer
├── extraction/   # document parsing, asset extraction, structured data preparation
├── processing/   # validation, vocabulary normalization, LLM-assisted extraction
├── prediction/   # model serving / survival prediction service
├── shared/       # common schemas, DB models, config, migrations
├── frontend/     # browser UI
├── docker-compose.yml
├── .env.example
└── .env          # local config created by the user
```

## Quick start

From the `pipeline/` directory:

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Then set the generated value in `.env` for:

- `SECRET_KEY` (required)
- `INTERNAL_SECRET` (recommended)
- optionally other provider settings if you want LLM-powered processing

Then start the stack:

```bash
docker compose up --build
```

Open:

- Frontend: http://localhost:5173
- Gateway API: http://localhost:8000
- API docs: http://localhost:8000/docs

The first build may take time because the prediction service compiles R dependencies and the extraction stack pulls heavy document-processing assets.

## Configuration notes

The actual configuration is driven by `pipeline/.env` and the example file `pipeline/.env.example`.

Important values currently required or expected:

- `POSTGRES_USER` and `POSTGRES_PASSWORD` must be set
- `SECRET_KEY` is required and has no default
- `INTERNAL_SECRET` is strongly recommended; if blank, internal services trust forwarded identity headers more loosely
- `PROCESSING_LLM_PROVIDER` chooses the LLM backend used by the processing service
- provider keys such as `PROCESSING_OPENAI_API_KEY`, `PROCESSING_ANTHROPIC_API_KEY`, `PROCESSING_GEMINI_API_KEY`, and `PROCESSING_GROQ_API_KEY` are only needed when that provider is selected

The actual repo structure shows that the LLM configuration belongs to the processing service, not the extraction service.

## What is missing and why

A few things are intentionally not automatic or not available without external setup:

- `SECRET_KEY` is required; without it the app will not start
- database credentials are required and the database is persisted in Docker volumes
- `INTERNAL_SECRET` is recommended to protect internal service trust boundaries
- LLM access needs an API key or a local Ollama setup
- if no provider is configured or reachable, the pipeline can still do deterministic extraction, but the prose/LLM-assisted fields may not be filled in
- the first Docker build is slow because of compiled R tooling and Docling model downloads

## Workflow

The intended project flow is:

1. Create a project
2. Upload PDFs
3. Extract tables, figures, captions, and document context
4. Validate and normalize the extracted scientific records
5. Enrich data with controlled vocabularies and LLM-assisted classification
6. Store the canonical scientific data in the shared schema
7. Build a training dataset for modeling
8. Run prediction / shelf-life modeling tasks


## Summary

This repo is a microservice-based research platform for food science and experimental data extraction. The architecture is designed to support structured, auditable extraction from PDFs and downstream predictive analysis.