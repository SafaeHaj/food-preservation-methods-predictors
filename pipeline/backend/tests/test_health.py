"""Basic smoke tests."""


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


def test_register_and_login(client):
    resp = client.post("/api/auth/register", json={
        "email": "newuser@example.com",
        "full_name": "New User",
        "password": "StrongPass123",
    })
    assert resp.status_code == 201, resp.text

    resp2 = client.post("/api/auth/login", json={
        "email": "newuser@example.com",
        "password": "StrongPass123",
    })
    assert resp2.status_code == 200
    assert "access_token" in resp2.json()


def test_protected_endpoint_rejects_unauthenticated(client):
    resp = client.get("/api/studies?project_id=1")
    assert resp.status_code == 401  # HTTPBearer returns 401 when no credentials


def test_studies_list_empty(client, auth_headers, db, test_user):
    from app.db.models import Project
    proj = Project(name="Test Project", owner_id=test_user.id, description="")
    db.add(proj)
    db.commit()
    db.refresh(proj)

    resp = client.get(f"/api/studies?project_id={proj.id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_study(client, auth_headers, db, test_user):
    from app.db.models import Project
    proj = Project(name="Test Project", owner_id=test_user.id, description="")
    db.add(proj)
    db.commit()
    db.refresh(proj)

    resp = client.post("/api/studies", json={
        "project_id": proj.id,
        "title": "Test Study on Cheese Preservation",
        "authors": ["Smith J", "Doe A"],
        "publication_year": 2022,
        "review_status": "extracted",
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["title"] == "Test Study on Cheese Preservation"
    assert data["authors"] == ["Smith J", "Doe A"]


def test_normalization_service():
    """Unit test: time unit conversion."""
    from app.services.normalization import normalize_time_to_days
    assert normalize_time_to_days(7, "days") == 7.0
    assert normalize_time_to_days(1, "week") == 7.0
    assert abs(normalize_time_to_days(24, "hours") - 1.0) < 1e-9
    assert normalize_time_to_days(1, "unknownunit") is None


def test_threshold_crossing():
    """Unit test: threshold crossing helper."""
    from app.services.threshold_analysis import _crossed
    assert _crossed(5.9, 6.0, "<=") is True
    assert _crossed(6.1, 6.0, "<=") is False
    assert _crossed(6.1, 6.0, ">=") is True
    assert _crossed(5.0, 6.0, ">") is False
