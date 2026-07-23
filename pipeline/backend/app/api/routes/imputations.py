"""Imputation proposals — create, list, review."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db.models import ImputationProposal, User
from app.schemas.canonical import ImputationProposalOut, ImputationReview

router = APIRouter(prefix="/imputations", tags=["imputations"])


def _get_or_404(imp_id: int, db: Session) -> ImputationProposal:
    p = db.query(ImputationProposal).filter(ImputationProposal.id == imp_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Imputation proposal not found")
    return p


@router.get("", response_model=list[ImputationProposalOut])
def list_proposals(
    project_id: Optional[int] = Query(None),
    trajectory_id: Optional[int] = Query(None),
    reviewer_decision: Optional[str] = Query(None),
    applicability_status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(ImputationProposal)
    if project_id:
        q = q.filter(ImputationProposal.project_id == project_id)
    if trajectory_id:
        q = q.filter(ImputationProposal.trajectory_id == trajectory_id)
    if reviewer_decision:
        q = q.filter(ImputationProposal.reviewer_decision == reviewer_decision)
    if applicability_status:
        q = q.filter(ImputationProposal.applicability_status == applicability_status)
    return q.order_by(ImputationProposal.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/{imp_id}", response_model=ImputationProposalOut)
def get_proposal(
    imp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _get_or_404(imp_id, db)


@router.post("/{imp_id}/review", response_model=ImputationProposalOut)
def review_proposal(
    imp_id: int,
    payload: ImputationReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from datetime import datetime
    if payload.decision not in ("accepted", "rejected"):
        raise HTTPException(status_code=400, detail="Decision must be 'accepted' or 'rejected'")
    proposal = _get_or_404(imp_id, db)
    proposal.reviewer_decision = payload.decision
    proposal.reviewer_id = current_user.id
    proposal.reviewer_note = payload.note
    proposal.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(proposal)
    return proposal
