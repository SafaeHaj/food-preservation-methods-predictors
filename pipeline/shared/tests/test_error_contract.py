"""The error envelope is a contract every service and the frontend depend on.

`frontend/src/api/errors.ts` parses exactly this shape, so a change here that is not made
there breaks error display everywhere at once. These tests pin the shape, the status
mapping, and the rule that an unexpected exception never leaks its message.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from shared.error_handlers import install_exception_handlers
from shared.errors import (
    AppError, AuthenticationError, BusinessRuleError, ConflictError, NotFoundError,
    PermissionDeniedError, UpstreamServiceError, ValidationError,
)
from shared.logging import install_request_id_middleware


class Body(BaseModel):
    count: int


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    install_request_id_middleware(app)
    install_exception_handlers(app)

    @app.get("/raise/{code}")
    def raise_error(code: str):
        raise {
            "not_found": NotFoundError.for_resource("Paper", 12),
            "denied": PermissionDeniedError("Nope"),
            "unauthenticated": AuthenticationError("Who are you"),
            "conflict": ConflictError("Already running"),
            "validation": ValidationError("Bad column", details={"column": "x"}),
            "business": BusinessRuleError("Cannot cancel"),
            "upstream": UpstreamServiceError("Down", details={"service": "prediction"}),
        }[code]

    @app.get("/boom")
    def boom():
        raise RuntimeError("connection string postgres://user:hunter2@db/prod")

    @app.get("/http-exception")
    def http_exception():
        raise HTTPException(status_code=404, detail="Legacy style")

    @app.get("/integrity")
    def integrity():
        raise IntegrityError("INSERT ...", {}, Exception("duplicate key"))

    @app.post("/validate")
    def validate(body: Body):
        return body

    # raise_server_exceptions=False so the unhandled-exception handler actually runs
    # instead of the test client re-raising.
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    "path,status,code",
    [
        ("not_found", 404, "not_found"),
        ("denied", 403, "permission_denied"),
        ("unauthenticated", 401, "unauthenticated"),
        ("conflict", 409, "conflict"),
        ("validation", 422, "validation_error"),
        ("business", 400, "business_rule_violation"),
        ("upstream", 502, "upstream_unavailable"),
    ],
)
def test_domain_errors_map_to_status_and_code(client, path, status, code):
    response = client.get(f"/raise/{path}")
    assert response.status_code == status

    error = response.json()["error"]
    assert error["code"] == code
    assert error["message"]
    assert error["request_id"]


def test_details_are_included_when_present(client):
    error = client.get("/raise/validation").json()["error"]
    assert error["details"] == {"column": "x"}


def test_details_are_omitted_when_empty(client):
    assert "details" not in client.get("/raise/denied").json()["error"]


def test_unexpected_exception_does_not_leak_its_message(client):
    response = client.get("/boom")
    assert response.status_code == 500

    error = response.json()["error"]
    assert error["code"] == "internal_error"
    # The RuntimeError carried a connection string; none of it may reach the client.
    assert "postgres://" not in response.text
    assert "hunter2" not in response.text
    assert error["message"] == "An unexpected error occurred"


def test_http_exception_is_translated_to_the_same_envelope(client):
    response = client.get("/http-exception")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_integrity_error_is_a_conflict_not_a_server_error(client):
    response = client.get("/integrity")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_request_validation_reports_the_offending_fields(client):
    response = client.post("/validate", json={"count": "not-a-number"})
    assert response.status_code == 422

    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"]["fields"]


def test_request_id_is_adopted_from_the_caller(client):
    response = client.get("/raise/not_found", headers={"X-Request-Id": "abc123"})
    assert response.headers["X-Request-Id"] == "abc123"
    assert response.json()["error"]["request_id"] == "abc123"


def test_request_id_is_generated_when_absent(client):
    response = client.get("/raise/not_found")
    assert response.json()["error"]["request_id"] not in ("", "-", None)


def test_app_error_status_is_a_property_of_the_type_not_the_call_site():
    """The whole point of the hierarchy: the same condition cannot be a 400 in one route
    and a 404 in another."""
    assert NotFoundError("x").status_code == 404
    assert ConflictError("x").status_code == 409
    assert issubclass(NotFoundError, AppError)
