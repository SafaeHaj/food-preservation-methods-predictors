from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db.models import ExtractedRow, Paper, Project, User
from app.schemas.projects import SchemaField
from app.services.excel_exporter import build_excel

router = APIRouter(prefix="/projects/{project_id}/export", tags=["export"])


@router.get("/excel")
def export_excel(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id, Project.owner_id == user.id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    papers = db.query(Paper).filter(Paper.project_id == project_id).all()
    rows = db.query(ExtractedRow).filter(ExtractedRow.project_id == project_id).all()

    papers_data = [
        {
            "id": p.id,
            "original_name": p.original_name,
            "status": p.status,
            "page_count": p.page_count,
        }
        for p in papers
    ]
    rows_data = [
        {
            "id": r.id,
            "paper_id": r.paper_id,
            "data": r.data,
            "provenance": r.provenance,
            "status": r.status,
            "reviewer_note": r.reviewer_note or "",
        }
        for r in rows
    ]

    xlsx_bytes = build_excel(
        project_name=project.name,
        schema_fields=project.schema,
        papers=papers_data,
        rows=rows_data,
    )

    safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in project.name)
    filename = f"{safe_name}_export.xlsx"

    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
