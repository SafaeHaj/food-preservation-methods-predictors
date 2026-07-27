"""End-to-end API tests via FastAPI's TestClient."""

from __future__ import annotations


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_extraction_then_query(client):
    run = client.post("/api/v1/extraction/run")
    assert run.status_code == 200
    assert run.json()["loaded"]["experiments"] == 15

    experiments = client.get("/api/v1/query/experiments")
    assert experiments.status_code == 200
    assert len(experiments.json()) == 15

    measurements = client.get("/api/v1/query/experiments/EXP001/measurements")
    assert measurements.status_code == 200
    assert len(measurements.json()) == 16


def test_prediction_stub(client):
    resp = client.post("/api/v1/prediction", json={"context": {}, "formulation": {}})
    assert resp.status_code == 501
    assert resp.json()["available"] is False
