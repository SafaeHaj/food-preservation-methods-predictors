"""
Pydantic v2 schemas for the platform entities every service shares.

Users, jobs, extraction runs, audit events and team membership -- the things that are not
science. The scientific schema's own request/response models belong to the service that
owns those tables (`extraction/app/schemas/ext_data.py`), not here.

This module was `canonical.py` and held schemas for a second scientific hierarchy --
studies, experiments, treatment arms, observations, trajectories, model fits, imputations,
thresholds, snapshots, exports -- alongside these. That hierarchy is gone, and with it the
reason for the name: nothing here is canonical or scientific.

Convention:
  - *Create  — input for POST (no id, no server-set timestamps)
  - *Update  — input for PATCH  (all fields Optional)
  - *Out     — response (includes id, timestamps, computed fields)
  - *Brief   — lightweight response used in list endpoints
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


# ─── shared config ────────────────────────────────────────────────────────────
_ORM = ConfigDict(from_attributes=True)


# ════════════════════════════════════════════════════════════════════════════
# USERS (thin read-only view, auth schemas live in auth.py)
# ════════════════════════════════════════════════════════════════════════════

class UserBrief(BaseModel):
    model_config = _ORM
    id: int
    email: str
    full_name: str


# ════════════════════════════════════════════════════════════════════════════
# JOBS
# ════════════════════════════════════════════════════════════════════════════

class JobOut(BaseModel):
    model_config = _ORM

    id: int
    project_id: Optional[int]
    paper_id: Optional[int]
    job_type: str
    status: str
    progress: int
    current_step: str
    total_steps: int
    error_message: str
    result: dict[str, Any]
    celery_task_id: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


# ════════════════════════════════════════════════════════════════════════════
# EXTRACTION RUNS
# ════════════════════════════════════════════════════════════════════════════

class ExtractionRunOut(BaseModel):
    model_config = _ORM

    id: int
    paper_id: int
    job_id: Optional[int]
    provider: Optional[str]
    model_name: Optional[str]
    prompt_version: Optional[str]
    status: str
    pages_processed: int
    chunks_created: int
    rows_extracted: int
    tables_found: int
    error_message: str
    created_at: datetime
    completed_at: Optional[datetime]


# ════════════════════════════════════════════════════════════════════════════
# AUDIT
# ════════════════════════════════════════════════════════════════════════════

class AuditEventOut(BaseModel):
    model_config = _ORM

    id: int
    actor_id: Optional[int]
    entity_type: str
    entity_id: int
    action: str
    diff: Optional[dict[str, Any]] = None
    reason: Optional[str]
    source: Optional[str]
    project_id: Optional[int]
    created_at: datetime


# ════════════════════════════════════════════════════════════════════════════
# PROJECT MEMBERS
# ════════════════════════════════════════════════════════════════════════════

class ProjectMemberCreate(BaseModel):
    user_email: str
    role: str = "reviewer"


class ProjectMemberUpdate(BaseModel):
    role: str


class ProjectMemberOut(BaseModel):
    model_config = _ORM

    id: int
    project_id: int
    user_id: int
    role: str
    joined_at: datetime
    user: Optional[UserBrief] = None
