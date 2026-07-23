# PreserveFM Research Platform — Implementation Checklist

Last updated: 2026-07-13  
Architecture: FastAPI + React 18 + SQLite(dev)/PostgreSQL(prod)

---

## Milestone 0 — Safety and Baseline ✅

- [x] `.gitignore` excludes `.env`, `*.db`, `uploads/`, `venv/`, `node_modules/`, `.vite/`, `dist/`, `__pycache__/`
- [x] `backend/.env.example` documented without secrets
- [x] Alembic initialized (`alembic.ini`, `alembic/env.py`)
- [x] Baseline migration created (existing 4 tables)
- [x] Canonical model migration created (all new tables)
- [x] `pytest` test infrastructure (`backend/tests/conftest.py`)
- [x] `IMPLEMENTATION.md` (this file)
- [x] `docker-compose.yml` updated with Redis + Celery worker

---

## Milestone 1 — Canonical Scientific Data Model ✅

### Backend Models (`app/db/models.py`)
- [x] **Job** — tracks all async work (extraction, modelling, export)
- [x] **ExtractionRun** — one per paper/attempt, links Job + Paper
- [x] **ExtractionChunk** — one per page/section/table
- [x] **Study** — one scientific paper/study (title, authors, DOI, type)
- [x] **Microorganism** — reusable taxonomy (genus, species, strain, role)
- [x] **Experiment** — experimental conditions block (temp, packaging, design)
- [x] **ExperimentMicroorganism** — M2M link
- [x] **TreatmentArm** — control or treatment arm
- [x] **Observation** — single measured value at one timepoint
- [x] **ProvenanceRecord** — PDF source evidence (page, bbox, snippet)
- [x] **ValidationIssue** — rule violations with severity/code
- [x] **AuditEvent** — full create/update/delete/approve history
- [x] **ProjectMember** — roles (owner/admin/reviewer/analyst/viewer)
- [x] **ReviewAssignment** — paper/study → reviewer queue
- [x] **Comment** — threaded comments on any entity
- [x] **NormalizationMapping** — original term → canonical term
- [x] **TrajectoryDefinition** — defines compatible observation groups
- [x] **ModelRun** — one fitting run (multiple models tried)
- [x] **ModelFit** — fitted parameters for one model
- [x] **ModelPrediction** — predicted values from ModelFit
- [x] **ImputationProposal** — proposed imputed value (never overwrites)
- [x] **ThresholdDefinition** — microbial/quality safety thresholds
- [x] **DatasetSnapshot** — versioned, reproducible dataset export
- [x] **ExportRun** — tracks export generation jobs

### Backend API Routes
- [x] `/projects/{id}/studies` — CRUD
- [x] `/projects/{id}/experiments` — CRUD + signature
- [x] `/projects/{id}/treatment-arms` — CRUD with control link
- [x] `/projects/{id}/observations` — CRUD + bulk import
- [x] `/projects/{id}/provenance` — evidence records
- [x] `/projects/{id}/validation-issues` — issues list + resolve
- [x] `/projects/{id}/jobs` — job status + cancel
- [x] `/projects/{id}/members` — role management
- [x] `/projects/{id}/normalization` — mapping CRUD + apply
- [x] `/projects/{id}/trajectories` — trajectory CRUD
- [x] `/projects/{id}/models` — model registry + runs + fits
- [x] `/projects/{id}/imputations` — proposal CRUD + accept/reject
- [x] `/projects/{id}/thresholds` — threshold CRUD
- [x] `/projects/{id}/audit` — audit log (read only)
- [x] `/files/{paper_id}` — authenticated PDF streaming
- [x] `/projects/{id}/snapshots` — dataset snapshots

---

## Milestone 2 — Full Extraction and Evidence Review 🔲

- [x] Remove `paper_text[:8000]` limitation → full document chunked
- [x] PyMuPDF page/block metadata extraction
- [x] Table extraction with headers, row labels, footnotes
- [x] Wide table → long observations conversion
- [ ] Celery worker for durable extraction (currently BackgroundTasks)
- [ ] SSE/WebSocket extraction progress stream
- [x] Structured AI extraction with Pydantic output
- [x] Deduplication of observations across chunks
- [ ] Side-by-side PDF review UI (react-pdf)

---

## Milestone 3 — Normalization and Validation 🔲

- [x] Unit normalization service (time, temperature, concentration, counts)
- [x] Taxonomy normalization mappings
- [x] Cross-field validation rules engine
- [x] Data-quality score calculation
- [x] Missingness reason taxonomy
- [ ] Normalization page UI (unmapped terms, suggest/apply)

---

## Milestone 4 — Dataset and Collaboration 🔲

- [x] TanStack Table canonical dataset page
- [x] Server-side pagination/filter/sort
- [x] Team roles and ProjectMember management
- [x] Comments and review assignments
- [x] Audit/version history API
- [ ] Corrected Excel re-import
- [ ] Bulk edit with keyboard navigation

---

## Milestone 5 — Trajectories and Classical Models 🔲

- [x] Trajectory builder with condition signature
- [x] Process classification (growth/inactivation/stable/complex)
- [x] Model registry (Gompertz, Baranyi, Richards, Logistic, Weibull, Geeraerd, Biphasic, Linear, Zero-order, First-order, Quadratic, Spline, GAM, GP)
- [ ] Model comparison table and diagnostics UI
- [ ] Leave-one-time-point-out cross-validation

---

## Milestone 6 — Imputation and Uncertainty 🔲

- [x] Applicability gate (Green/Yellow/Red status)
- [x] Imputation proposal workflow (propose → accept/reject)
- [ ] Bootstrap confidence intervals
- [ ] Multiple imputation draws
- [ ] Model Lab interactive curve UI

---

## Milestone 7 — Treatment, Dose, Shelf Life 🔲

- [x] Treatment vs control arm linking
- [x] Threshold crossing calculation
- [x] ThresholdDefinition CRUD
- [ ] Dose-response visualization
- [ ] Shelf-life extension calculation
- [ ] Secondary Arrhenius/Ratkowsky temperature models

---

## Milestone 8 — Analytics, Export, ML Adapter 🔲

- [x] Comprehensive Excel export (23 sheets)
- [x] DatasetSnapshot API
- [x] ML-ready export with missingness masks + origin flags
- [ ] Expanded analytics charts
- [ ] HTML/PDF report generation
- [ ] TabDDPM external job interface

---

## Milestone 9 — Production Hardening 🔲

- [ ] PostgreSQL full test
- [ ] Redis + Celery production configuration
- [ ] S3-compatible object storage adapter
- [ ] Rate limiting (auth, upload, extraction, model jobs)
- [ ] End-to-end Playwright tests
- [ ] Performance optimization (query profiling, N+1 fixes)

---

## API Reference (summary)

| Group | Prefix | Key endpoints |
|-------|--------|---------------|
| Auth | `/api/auth` | login, register, me |
| Projects | `/api/projects` | CRUD, schema |
| Papers | `/api/projects/{id}/papers` | upload, list, delete |
| Files | `/api/files/{paper_id}` | authenticated PDF stream |
| Extraction | `/api/projects/{id}/extract` | trigger one/all |
| Jobs | `/api/projects/{id}/jobs` | list, get, cancel |
| Studies | `/api/projects/{id}/studies` | CRUD |
| Experiments | `/api/projects/{id}/experiments` | CRUD |
| TreatmentArms | `/api/projects/{id}/treatment-arms` | CRUD |
| Observations | `/api/projects/{id}/observations` | CRUD, bulk |
| Provenance | `/api/projects/{id}/provenance` | list, get |
| Validation | `/api/projects/{id}/validation-issues` | list, resolve |
| Audit | `/api/projects/{id}/audit` | list (read-only) |
| Members | `/api/projects/{id}/members` | list, add, update, remove |
| Normalization | `/api/projects/{id}/normalization` | mappings CRUD, apply |
| Trajectories | `/api/projects/{id}/trajectories` | CRUD |
| Models | `/api/projects/{id}/models` | registry, runs, fits |
| Imputations | `/api/projects/{id}/imputations` | propose, accept, reject |
| Thresholds | `/api/projects/{id}/thresholds` | CRUD |
| Analytics | `/api/projects/{id}/analytics` | summary |
| Dataset | `/api/projects/{id}/dataset` | paginated canonical view |
| Export | `/api/projects/{id}/export` | excel, csv, parquet |
| Snapshots | `/api/projects/{id}/snapshots` | create, list |
| Review | `/api/projects/{id}/rows` | legacy flat rows |
| Schema | `/api/schema` | infer |

---

## Data-quality principle

Every value knows:
- Its **origin**: reported_table / reported_text / reported_figure / graph_estimated / calculated / unit_converted / normalized / model_imputed / manual_entry / imported_external / synthetic
- Its **missing reason** (if absent): not_reported / not_measured / not_applicable / below_detection_limit / above_detection_limit / unreadable_source / extraction_failed / removed_after_validation / figure_only_not_digitized / intentionally_masked_for_validation / unknown
- Its **provenance**: paper_id, page_number, table_number, figure_number, source snippet, bounding box
- Its **review status**: extracted / needs_review / in_review / changes_requested / approved / rejected / superseded

Imputed values are stored ONLY as ImputationProposal objects. Accepted imputations remain permanently distinguishable from observed values via value_origin = "model_imputed".
