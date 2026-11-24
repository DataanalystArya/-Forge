from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import app.models  # noqa: F401
from app.core import security
from app.core.database import Base
from app.core.deps import get_db
from app.models.user import User
from app.models.repository import Repository, IndexingJob
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


def test_cross_user_repository_isolation(client):
    """Verify that User A cannot view, access, or delete User B's repositories."""
    # 1. Register User A
    res_a = client.post("/api/v1/auth/register", json={
        "email": "user_a@forge.dev",
        "password": "PasswordA123!",
        "full_name": "User Alpha"
    })
    token_a = res_a.json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # 2. Register User B
    res_b = client.post("/api/v1/auth/register", json={
        "email": "user_b@forge.dev",
        "password": "PasswordB123!",
        "full_name": "User Beta"
    })
    token_b = res_b.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # 3. User A creates a repository
    repo_res = client.post("/api/v1/repositories", json={
        "full_name": "alpha-org/private-core",
        "description": "Confidential repository of Alpha",
        "is_private": True
    }, headers=headers_a)
    assert repo_res.status_code == 201
    repo_id = repo_res.json()["id"]

    # 4. User B lists repositories - must NOT contain User A's repository
    list_b = client.get("/api/v1/repositories", headers=headers_b)
    assert list_b.status_code == 200
    assert list_b.json()["total"] == 0
    assert len(list_b.json()["items"]) == 0

    # 5. User B attempts direct GET of User A's repository - must return 404 Not Found
    direct_get = client.get(f"/api/v1/repositories/{repo_id}", headers=headers_b)
    assert direct_get.status_code == 404

    # 6. User B attempts direct DELETE of User A's repository - must return 404 Not Found
    direct_del = client.delete(f"/api/v1/repositories/{repo_id}", headers=headers_b)
    assert direct_del.status_code == 404

    # 7. Verify repository still exists for User A
    verify_get = client.get(f"/api/v1/repositories/{repo_id}", headers=headers_a)
    assert verify_get.status_code == 200
    assert verify_get.json()["id"] == repo_id


def test_expired_jwt_token(client):
    """Verify that expired JWT tokens are strictly rejected with 401 Unauthorized."""
    # Create an expired token (negative delta)
    expired_token = security.create_access_token(
        subject="fake-user-id",
        expires_delta=timedelta(seconds=-10)
    )
    headers = {"Authorization": f"Bearer {expired_token}"}
    res = client.get("/api/v1/auth/me", headers=headers)
    assert res.status_code == 401
    assert "detail" in res.json()


def test_tampered_jwt_token(client):
    """Verify that tampered JWT signatures are rejected with 401 Unauthorized."""
    valid_token = security.create_access_token(subject="fake-user-id")
    # Tamper the token by corrupting the signature bytes
    tampered_token = valid_token[:-4] + "xxxx"
    headers = {"Authorization": f"Bearer {tampered_token}"}
    res = client.get("/api/v1/auth/me", headers=headers)
    assert res.status_code == 401


def test_inactive_user_access_blocked(client, db_session):
    """Verify that an inactive account cannot perform authenticated actions."""
    reg_res = client.post("/api/v1/auth/register", json={
        "email": "disabled@forge.dev",
        "password": "Password123!",
        "full_name": "Disabled Account"
    })
    token = reg_res.json()["access_token"]
    user_id = reg_res.json()["user"]["id"]

    # Deactivate the user in DB
    user = db_session.query(User).filter(User.id == user_id).first()
    user.is_active = False
    db_session.commit()

    headers = {"Authorization": f"Bearer {token}"}
    res = client.get("/api/v1/auth/me", headers=headers)
    assert res.status_code == 403
    assert "Inactive user" in res.json()["detail"]


def test_cascade_deletion(client, db_session):
    """Verify that deleting a User cascades to their Repositories and IndexingJobs."""
    reg_res = client.post("/api/v1/auth/register", json={
        "email": "delete_me@forge.dev",
        "password": "Password123!",
        "full_name": "Delete Me"
    })
    user_id = reg_res.json()["user"]["id"]
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create repository
    repo_res = client.post("/api/v1/repositories", json={
        "full_name": "delete-org/test-repo"
    }, headers=headers)
    repo_id = repo_res.json()["id"]

    # Verify repository and indexing job exist
    assert db_session.query(Repository).filter(Repository.id == repo_id).count() == 1
    assert db_session.query(IndexingJob).filter(IndexingJob.repository_id == repo_id).count() == 1

    # Delete the user directly
    user = db_session.query(User).filter(User.id == user_id).first()
    db_session.delete(user)
    db_session.commit()

    # Verify cascades removed the repo and indexing jobs
    assert db_session.query(Repository).filter(Repository.id == repo_id).count() == 0
    assert db_session.query(IndexingJob).filter(IndexingJob.repository_id == repo_id).count() == 0


def test_repository_name_path_traversal_rejection(client):
    """Verify that malformed or malicious repository names (e.g. path traversal) are rejected."""
    reg_res = client.post("/api/v1/auth/register", json={
        "email": "security_test@forge.dev",
        "password": "Password123!"
    })
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    malicious_names = [
        "../../etc/passwd",
        "owner/repo/../../traversal",
        "owner/repo;rm -rf /",
        "owner",
        "owner/repo/sub/extra",
    ]

    for bad_name in malicious_names:
        res = client.post("/api/v1/repositories", json={"full_name": bad_name}, headers=headers)
        assert res.status_code == 422, f"Expected 422 for malicious repo name '{bad_name}', got {res.status_code}"
