"""Authorization policy and signed asset URLs.

Both replaced holes that were reachable in production: project access was a predicate
copy-pasted at ~15 call sites (and forgotten at several), and binary assets were served to
anyone because `<img>` cannot send a bearer token.
"""

from __future__ import annotations

import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.access import (
    authorize_job, authorize_paper, authorize_project, effective_role, role_satisfies,
)
from shared.db.database import Base
from shared.db.models import Job, Paper, Project, ProjectMember, User
from shared.errors import NotFoundError, PermissionDeniedError
from shared.signing import sign_path, verify_path

SECRET = "test-signing-secret"


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def world(db):
    """An owner, a member, an outsider, and a project with one paper and one job."""
    owner = User(email="owner@example.com", full_name="Owner", hashed_password="x", is_active=True)
    member = User(email="member@example.com", full_name="Member", hashed_password="x", is_active=True)
    outsider = User(email="outsider@example.com", full_name="Outsider", hashed_password="x", is_active=True)
    db.add_all([owner, member, outsider])
    db.flush()

    project = Project(name="Cheese", description="", schema_json="[]", owner_id=owner.id)
    db.add(project)
    db.flush()

    db.add(ProjectMember(project_id=project.id, user_id=owner.id, role="owner"))
    db.add(ProjectMember(project_id=project.id, user_id=member.id, role="viewer"))

    paper = Paper(
        project_id=project.id, filename="a.pdf", original_name="a.pdf",
        file_path="/tmp/a.pdf", page_count=1, status="uploaded", error_message="",
    )
    db.add(paper)
    db.flush()

    job = Job(project_id=project.id, paper_id=paper.id, job_type="workspace_extraction",
              status="running", created_by=owner.id)
    db.add(job)
    db.commit()

    return {"owner": owner, "member": member, "outsider": outsider,
            "project": project, "paper": paper, "job": job}


# ─── Roles ────────────────────────────────────────────────────────────────────

def test_role_hierarchy_is_ordered():
    assert role_satisfies("owner", "viewer")
    assert role_satisfies("admin", "reviewer")
    assert role_satisfies("viewer", "viewer")
    assert not role_satisfies("viewer", "analyst")
    assert not role_satisfies("analyst", "admin")


def test_unknown_role_satisfies_nothing():
    assert not role_satisfies("wizard", "viewer")


# ─── Project access ───────────────────────────────────────────────────────────

def test_owner_has_owner_role(db, world):
    assert effective_role(db, world["project"], world["owner"]) == "owner"


def test_member_gets_their_granted_role(db, world):
    """Membership was previously ignored entirely: inviting a collaborator granted nothing."""
    assert effective_role(db, world["project"], world["member"]) == "viewer"


def test_outsider_has_no_role(db, world):
    assert effective_role(db, world["project"], world["outsider"]) is None


def test_outsider_gets_404_not_403(db, world):
    """A 403 would confirm the project exists, letting an outsider enumerate ids."""
    with pytest.raises(NotFoundError):
        authorize_project(db, world["project"].id, world["outsider"])


def test_member_cannot_perform_an_admin_action(db, world):
    with pytest.raises(PermissionDeniedError):
        authorize_project(db, world["project"].id, world["member"], "admin")


def test_owner_can_perform_an_admin_action(db, world):
    assert authorize_project(db, world["project"].id, world["owner"], "admin").id == world["project"].id


def test_missing_project_is_not_found(db, world):
    with pytest.raises(NotFoundError):
        authorize_project(db, 9999, world["owner"])


# ─── Paper and job access ─────────────────────────────────────────────────────

def test_paper_is_authorized_through_its_project(db, world):
    assert authorize_paper(db, world["project"].id, world["paper"].id, world["member"]).id == world["paper"].id

    with pytest.raises(NotFoundError):
        authorize_paper(db, world["project"].id, world["paper"].id, world["outsider"])


def test_paper_from_another_project_is_not_found(db, world):
    other = Project(name="Other", description="", schema_json="[]", owner_id=world["owner"].id)
    db.add(other)
    db.commit()

    with pytest.raises(NotFoundError):
        authorize_paper(db, other.id, world["paper"].id, world["owner"])


def test_job_is_authorized_through_its_project(db, world):
    """`GET /api/jobs/{id}` had no ownership check at all: any authenticated user could
    read any job's error messages and results."""
    assert authorize_job(db, world["job"].id, world["owner"]).id == world["job"].id

    with pytest.raises(NotFoundError):
        authorize_job(db, world["job"].id, world["outsider"])


def test_projectless_job_is_visible_only_to_its_creator(db, world):
    job = Job(project_id=None, job_type="maintenance", status="running",
              created_by=world["owner"].id)
    db.add(job)
    db.commit()

    assert authorize_job(db, job.id, world["owner"]).id == job.id
    with pytest.raises(NotFoundError):
        authorize_job(db, job.id, world["member"])


# ─── Signed asset URLs ────────────────────────────────────────────────────────

def test_a_fresh_signature_verifies():
    path = "/api/projects/1/papers/2/assets/3/image"
    signed = sign_path(SECRET, path, ttl_seconds=60)

    _, query = signed.split("?", 1)
    params = dict(pair.split("=") for pair in query.split("&"))
    assert verify_path(SECRET, path, params["exp"], params["sig"])


def test_signature_does_not_transfer_to_another_asset():
    """Editing the asset id must invalidate the signature, or one signed URL would grant
    access to every asset in the installation."""
    signed = sign_path(SECRET, "/api/projects/1/papers/2/assets/3/image", 60)
    params = dict(pair.split("=") for pair in signed.split("?", 1)[1].split("&"))

    assert not verify_path(
        SECRET, "/api/projects/1/papers/2/assets/999/image", params["exp"], params["sig"]
    )


def test_expiry_cannot_be_extended_by_the_client():
    signed = sign_path(SECRET, "/api/x/image", 60)
    params = dict(pair.split("=") for pair in signed.split("?", 1)[1].split("&"))

    forged = str(int(params["exp"]) + 100_000)
    assert not verify_path(SECRET, "/api/x/image", forged, params["sig"])


def test_an_expired_signature_is_rejected():
    path = "/api/x/image"
    expired = str(int(time.time()) - 1)
    # Sign the expired timestamp honestly: a valid signature over a past expiry must still
    # be refused, otherwise the TTL means nothing.
    import hashlib
    import hmac
    signature = hmac.new(
        SECRET.encode(), f"{path}:{expired}".encode(), hashlib.sha256
    ).hexdigest()

    assert not verify_path(SECRET, path, expired, signature)


def test_another_secret_cannot_sign():
    signed = sign_path("attacker-secret", "/api/x/image", 60)
    params = dict(pair.split("=") for pair in signed.split("?", 1)[1].split("&"))

    assert not verify_path(SECRET, "/api/x/image", params["exp"], params["sig"])


@pytest.mark.parametrize("expiry,signature", [(None, "abc"), ("123", None), (None, None), ("nope", "abc")])
def test_missing_or_malformed_proof_is_rejected(expiry, signature):
    assert not verify_path(SECRET, "/api/x/image", expiry, signature)
