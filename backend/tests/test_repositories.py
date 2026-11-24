import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import app.models  # noqa: F401 registers models on Base.metadata
from app.core.database import Base
from app.core.deps import get_db
from app.main import app

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers(client):
    reg_payload = {
        "email": "dev@forge.dev",
        "password": "Password123!",
        "full_name": "Forge Developer"
    }
    res = client.post("/api/v1/auth/register", json=reg_payload)
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_repository_crud_flow(client, auth_headers):
    # 1. Initially empty
    list_res = client.get("/api/v1/repositories", headers=auth_headers)
    assert list_res.status_code == 200
    assert list_res.json()["total"] == 0
    assert len(list_res.json()["items"]) == 0

    # 2. Register repository
    create_payload = {
        "full_name": "facebook/react",
        "description": "The library for web and native user interfaces.",
        "default_branch": "main",
        "is_private": False
    }
    create_res = client.post("/api/v1/repositories", json=create_payload, headers=auth_headers)
    assert create_res.status_code == 201
    repo_data = create_res.json()
    assert repo_data["full_name"] == "facebook/react"
    repo_id = repo_data["id"]

    # 3. Retrieve single repository
    get_res = client.get(f"/api/v1/repositories/{repo_id}", headers=auth_headers)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == repo_id

    # 4. List now has 1
    list_res2 = client.get("/api/v1/repositories", headers=auth_headers)
    assert list_res2.status_code == 200
    assert list_res2.json()["total"] == 1

    # 5. Check dashboard stats
    stats_res = client.get("/api/v1/dashboard/stats", headers=auth_headers)
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert stats["total_repositories"] == 1
    assert stats["total_sessions"] == 0

    # 6. Delete repository
    del_res = client.delete(f"/api/v1/repositories/{repo_id}", headers=auth_headers)
    assert del_res.status_code == 204

    # 7. List is empty again
    list_res3 = client.get("/api/v1/repositories", headers=auth_headers)
    assert list_res3.json()["total"] == 0
