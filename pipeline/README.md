# Food Research Platform

A full-stack web platform for food science research teams to extract, review, validate and export structured data from scientific PDF papers.

## Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + TypeScript + Vite + TailwindCSS |
| Backend | FastAPI + SQLAlchemy (ORM) |
| Database | SQLite (dev) / PostgreSQL (prod) |
| Auth | JWT (python-jose + bcrypt) |
| AI Extraction | Anthropic Claude API (key in backend only) |
| PDF Parsing | PyMuPDF (fitz) |
| Charts | Recharts |
| Export | openpyxl (multi-sheet Excel) |

---

## Quick Start (Windows)

```bat
cd pipeline
start.bat
```

This will:
1. Create a Python virtual environment and install backend packages
2. Install frontend npm packages  
3. Start both servers in separate windows

**Then open:** http://localhost:5173

---

## Quick Start (Mac / Linux)

```bash
cd pipeline
chmod +x start.sh
./start.sh
```

---

## First-time Setup

### 1. Add your Anthropic API Key

Edit `backend/.env`:

```
ANTHROPIC_API_KEY=sk-ant-...your-key-here...
```

The key is **never sent to the frontend**. It lives only in the backend process.

### 2. Register an account

Go to http://localhost:5173/register and create your account.

### 3. Create a project

Click **New Project** on the dashboard. A default food-preservation schema is applied automatically.

---

## Workflow

```
1. Create Project
       ↓
2. Upload PDFs  (drag & drop, up to 10 at a time)
       ↓
3. Run AI Extraction  (click "Extract All" — runs in background)
       ↓
4. Human Review  (approve / edit / reject each row, confidence scores shown)
       ↓
5. Export to Excel  (6 sheets: Summary, All Data, Per-Paper, Provenance, Validation, Schema)
```

---

## API Documentation

FastAPI auto-generates interactive docs at:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

---

## Project Structure

```
pipeline/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, CORS, route registration
│   │   ├── core/
│   │   │   ├── config.py        # Settings (reads .env)
│   │   │   └── security.py      # JWT + bcrypt
│   │   ├── db/
│   │   │   ├── database.py      # SQLAlchemy engine + session
│   │   │   └── models.py        # User, Project, Paper, ExtractedRow
│   │   ├── schemas/             # Pydantic request/response models
│   │   ├── api/routes/
│   │   │   ├── auth.py          # POST /auth/login, /auth/register, GET /auth/me
│   │   │   ├── projects.py      # CRUD /projects
│   │   │   ├── papers.py        # Upload / list / delete PDFs
│   │   │   ├── extraction.py    # Trigger AI extraction (background tasks)
│   │   │   ├── review.py        # List / edit / approve / reject rows
│   │   │   ├── analytics.py     # Stats, field coverage, distributions
│   │   │   ├── export.py        # GET /export/excel
│   │   │   └── schema.py        # POST /schema/infer (from Excel)
│   │   └── services/
│   │       ├── pdf_extractor.py  # PyMuPDF text extraction
│   │       ├── ai_extractor.py   # Anthropic API call + response parsing
│   │       ├── validator.py      # Scientific plausibility rules
│   │       └── excel_exporter.py # 6-sheet openpyxl builder
│   ├── .env.example
│   └── requirements.txt
│
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── Login.tsx
│       │   ├── Register.tsx
│       │   ├── Dashboard.tsx    # Project list + create
│       │   ├── ProjectView.tsx  # Papers list + extract buttons
│       │   ├── Upload.tsx       # Drag-and-drop PDF upload
│       │   ├── SchemaPage.tsx   # Field editor + Excel inference
│       │   ├── Review.tsx       # Row-level review + bulk actions
│       │   └── Analytics.tsx    # Charts + coverage + distributions
│       ├── services/api.ts      # Axios client + typed API calls
│       ├── store/auth.ts        # Zustand auth store (persisted)
│       └── types/index.ts       # TypeScript interfaces
│
├── docker-compose.yml
├── start.bat                    # Windows one-click start
└── start.sh                     # Mac/Linux one-click start
```

---

## Scientific Validation Rules

Applied automatically during AI extraction and when editing rows:

| Field pattern | Rule |
|---|---|
| `concentration` | >= 0 |
| `day`, `time`, `duration` | >= 0 |
| `ph` | 3.0 – 8.5 |
| `log_cfu`, `cfu` | 0 – 12 |
| `percent`, `humidity`, `moisture` | 0 – 100 |
| `temperature` | -80 – 200 °C |

Custom min/max rules per field can be set in the Schema Editor.

---

## Environment Variables

All in `backend/.env`:

| Variable | Description | Default |
|---|---|---|
| `SECRET_KEY` | JWT signing key | `dev-secret-key-...` |
| `DATABASE_URL` | SQLAlchemy DB URL | `sqlite:///./food_research.db` |
| `ANTHROPIC_API_KEY` | **Required for AI** | — |
| `AI_MODEL` | Claude model ID | `claude-sonnet-4-6` |
| `MAX_UPLOAD_SIZE_MB` | Max PDF size | `50` |
| `MAX_PAPERS_PER_UPLOAD` | Files per batch | `10` |

For PostgreSQL in production:
```
DATABASE_URL=postgresql://user:password@host:5432/food_research
```
