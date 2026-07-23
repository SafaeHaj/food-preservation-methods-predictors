import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db.models import ExtractedRow, Paper, Project, User
from app.schemas.papers import BulkStatusUpdate, RowOut, RowUpdate
from app.services.validator import validate_row

router = APIRouter(prefix="/projects/{project_id}/rows", tags=["review"])


def _row_out(row: ExtractedRow) -> RowOut:
    return RowOut(
        id=row.id,
        paper_id=row.paper_id,
        project_id=row.project_id,
        data=row.data,
        provenance=row.provenance,
        status=row.status,
        reviewer_note=row.reviewer_note or "",
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _get_project(project_id: int, user: User, db: Session) -> Project:
    project = db.query(Project).filter(Project.id == project_id, Project.owner_id == user.id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@router.get("", response_model=List[RowOut])
def list_rows(
    project_id: int,
    status: Optional[str] = Query(None),
    paper_id: Optional[int] = Query(None),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_project(project_id, user, db)
    q = db.query(ExtractedRow).filter(ExtractedRow.project_id == project_id)
    if status:
        q = q.filter(ExtractedRow.status == status)
    if paper_id:
        q = q.filter(ExtractedRow.paper_id == paper_id)
    rows = q.order_by(ExtractedRow.created_at.desc()).offset(skip).limit(limit).all()
    return [_row_out(r) for r in rows]


@router.patch("/{row_id}", response_model=RowOut)
def update_row(
    project_id: int,
    row_id: int,
    body: RowUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _get_project(project_id, user, db)
    row = db.query(ExtractedRow).filter(ExtractedRow.id == row_id, ExtractedRow.project_id == project_id).first()
    if not row:
        raise HTTPException(404, "Row not found")

    if body.data is not None:
        _, violations = validate_row(body.data, project.schema)
        row.data_json = json.dumps(body.data)
        if violations and not body.reviewer_note:
            row.reviewer_note = "; ".join(violations)

    if body.status is not None:
        row.status = body.status

    if body.reviewer_note is not None:
        row.reviewer_note = body.reviewer_note

    db.commit()
    db.refresh(row)

    # Trigger canonical promotion when a row is individually approved
    if body.status == "approved":
        from app.services.canonical_promoter import promote_paper_to_canonical
        promote_paper_to_canonical(row.paper_id, row.project_id, db)

    return _row_out(row)


@router.post("/bulk-status", status_code=200)
def bulk_update_status(
    project_id: int,
    body: BulkStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_project(project_id, user, db)
    updated = (
        db.query(ExtractedRow)
        .filter(
            ExtractedRow.project_id == project_id,
            ExtractedRow.id.in_(body.row_ids),
        )
        .all()
    )
    paper_ids: set[int] = set()
    for row in updated:
        row.status = body.status
        if body.status == "approved":
            paper_ids.add(row.paper_id)
    db.commit()

    # When rows are approved, promote them to canonical data if not already done
    if body.status == "approved" and paper_ids:
        from app.services.canonical_promoter import promote_paper_to_canonical
        for pid in paper_ids:
            row_obj = db.query(ExtractedRow).filter(ExtractedRow.paper_id == pid).first()
            if row_obj:
                promote_paper_to_canonical(pid, row_obj.project_id, db)

    return {"updated": len(updated)}


@router.delete("/{row_id}", status_code=204)
def delete_row(
    project_id: int,
    row_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_project(project_id, user, db)
    row = db.query(ExtractedRow).filter(ExtractedRow.id == row_id, ExtractedRow.project_id == project_id).first()
    if not row:
        raise HTTPException(404, "Row not found")
    db.delete(row)
    db.commit()
