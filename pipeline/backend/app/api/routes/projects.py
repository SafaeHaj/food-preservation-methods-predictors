import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db.models import ExtractedRow, Paper, Project, User
from app.schemas.projects import ProjectCreate, ProjectOut, ProjectUpdate, SchemaField

router = APIRouter(prefix="/projects", tags=["projects"])

DEFAULT_SCHEMA = [
    SchemaField(name="ingredient_name", label="Ingredient / Antimicrobial", type="text", required=True),
    SchemaField(name="concentration", label="Concentration", type="number", unit="g/100g",
                validation={"min": 0, "max": 100}),
    SchemaField(name="concentration_unit", label="Concentration Unit", type="text"),
    SchemaField(name="microbial_indicator", label="Microbial Indicator", type="text"),
    SchemaField(name="initial_count_log_cfu_g", label="Initial Count (log CFU/g)", type="number",
                validation={"min": 0, "max": 12}),
    SchemaField(name="treatment_day", label="Treatment Day", type="number", validation={"min": 0}),
    SchemaField(name="final_count_log_cfu_g", label="Final Count (log CFU/g)", type="number",
                validation={"min": 0, "max": 12}),
    SchemaField(name="ph", label="pH", type="number", validation={"min": 3.0, "max": 8.5}),
    SchemaField(name="temperature_c", label="Temperature (°C)", type="number",
                validation={"min": -20, "max": 60}),
    SchemaField(name="storage_conditions", label="Storage Conditions", type="text"),
    SchemaField(name="product_type", label="Product / Matrix", type="text"),
    SchemaField(name="efficacy_class", label="Efficacy Class", type="select",
                options=["bacteriostatic", "bactericidal", "fungistatic", "fungicidal", "not_reported"]),
    SchemaField(name="study_design", label="Study Design", type="select",
                options=["in_vitro", "in_vivo", "challenge_study", "field_study"]),
    SchemaField(name="doi", label="DOI", type="text"),
    SchemaField(name="notes", label="Notes", type="text"),
]


def _project_out(project: Project, db: Session) -> ProjectOut:
    paper_count = db.query(Paper).filter(Paper.project_id == project.id).count()
    row_count = db.query(ExtractedRow).filter(ExtractedRow.project_id == project.id).count()
    schema_fields = [SchemaField(**f) for f in project.schema]
    return ProjectOut(
        id=project.id,
        name=project.name,
        description=project.description,
        schema_fields=schema_fields,
        created_at=project.created_at,
        updated_at=project.updated_at,
        owner_id=project.owner_id,
        paper_count=paper_count,
        row_count=row_count,
    )


@router.get("", response_model=List[ProjectOut])
def list_projects(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    projects = db.query(Project).filter(Project.owner_id == user.id).order_by(Project.created_at.desc()).all()
    return [_project_out(p, db) for p in projects]


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    schema = body.schema_fields if body.schema_fields else DEFAULT_SCHEMA
    project = Project(
        name=body.name,
        description=body.description,
        schema_json=json.dumps([f.model_dump() for f in schema]),
        owner_id=user.id,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return _project_out(project, db)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = db.query(Project).filter(Project.id == project_id, Project.owner_id == user.id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    return _project_out(project, db)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(project_id: int, body: ProjectUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = db.query(Project).filter(Project.id == project_id, Project.owner_id == user.id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    if body.name is not None:
        project.name = body.name
    if body.description is not None:
        project.description = body.description
    if body.schema_fields is not None:
        project.schema_json = json.dumps([f.model_dump() for f in body.schema_fields])
    db.commit()
    db.refresh(project)
    return _project_out(project, db)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = db.query(Project).filter(Project.id == project_id, Project.owner_id == user.id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    db.delete(project)
    db.commit()
