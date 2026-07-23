"""
Pytest test infrastructure.

Uses an in-memory SQLite database (never touches the real dev DB).
Provides fixtures for:
  - db: fresh SQLAlchemy session for each test
  - client: FastAPI TestClient with auth header
  - auth_headers: Bearer token for a test user
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
# Import ALL models so Base.metadata knows about every table
import app.db.models  # noqa: F401
from app.db.models import User
from app.core.security import create_access_token, hash_password
from app.main import app

TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,  # single shared connection → all code sees same in-memory DB
)
TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


@pytest.fixture(scope="function")
def db():
    """Fresh in-memory database for each test function."""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db):
    """TestClient wired to the in-memory DB."""
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def test_user(db) -> User:
    user = User(
        email="test@example.com",
        full_name="Test User",
        hashed_password=hash_password("password123"),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture(scope="function")
def auth_headers(test_user: User) -> dict:
    token = create_access_token({"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}
