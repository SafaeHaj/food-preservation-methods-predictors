from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.database import Base, engine
from app.api.routes import auth, projects, papers, extraction, review, analytics, export, schema

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Food Research Platform API",
    description="Extract, review, and export food-science data from scientific papers.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(papers.router, prefix="/api")
app.include_router(extraction.router, prefix="/api")
app.include_router(review.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(export.router, prefix="/api")
app.include_router(schema.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "Food Research Platform"}
