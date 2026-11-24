import io
import os
import zipfile
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import app.models  # noqa: F401
from app.core.database import Base
from app.core.deps import get_db
from app.core.encryption import decrypt_token
from app.models.user import GitHubAccount
from app.main import app
from unittest.mock import patch

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
    res = client.post("/api/v1/auth/register", json={
        "email": "engineer2@forge.dev",
        "password": "Password123!",
        "full_name": "Senior Staff Engineer"
    })
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_sample_zip_bytes() -> bytes:
    """Create a sample valid project zip archive in memory."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "app/calculator.py",
            "class Calculator:\n    def add(self, a, b):\n        return a + b\n\ndef multiply(x, y):\n    return x * y\n"
        )
        zf.writestr(
            "src/utils.ts",
            "export class StringFormatter {\n  format(s: string) {\n    return s.trim();\n  }\n}\n\nexport function helper() {\n  return true;\n}\n"
        )
        zf.writestr("README.md", "# Test Project\nSample repository for testing FORGE.\n")
    return buf.getvalue()


def test_zip_upload_scanning_and_tree(client, auth_headers):
    # 1. Create repository
    repo_res = client.post("/api/v1/repositories", json={
        "full_name": "test-org/calculator-service",
        "description": "A demo calculator microservice"
    }, headers=auth_headers)
    assert repo_res.status_code == 201
    repo_id = repo_res.json()["id"]

    # 2. Upload sample ZIP
    zip_bytes = create_sample_zip_bytes()
    upload_res = client.post(
        f"/api/v1/repositories/{repo_id}/upload-zip",
        files={"file": ("project.zip", zip_bytes, "application/zip")},
        headers=auth_headers
    )
    assert upload_res.status_code == 200
    repo_data = upload_res.json()
    assert repo_data["status"] == "READY"
    assert repo_data["total_files"] == 3
    assert repo_data["total_lines"] > 0

    # 3. Retrieve nested file tree
    tree_res = client.get(f"/api/v1/repositories/{repo_id}/tree", headers=auth_headers)
    assert tree_res.status_code == 200
    tree = tree_res.json()
    assert len(tree) >= 2  # app dir, src dir, README.md

    # 4. Retrieve specific file content
    file_res = client.get(
        f"/api/v1/repositories/{repo_id}/file?path=app/calculator.py",
        headers=auth_headers
    )
    assert file_res.status_code == 200
    f_data = file_res.json()
    assert f_data["name"] == "calculator.py"
    assert f_data["language"] == "Python"
    assert "class Calculator" in f_data["content"]
    assert f_data["lines"] == 6

    # 5. Retrieve extracted AST symbols
    sym_res = client.get(f"/api/v1/repositories/{repo_id}/symbols", headers=auth_headers)
    assert sym_res.status_code == 200
    artifacts = sym_res.json()["artifacts"]
    symbol_names = [a["entity_name"] for a in artifacts]
    assert "Calculator" in symbol_names
    assert "multiply" in symbol_names


def test_zip_slip_vulnerability_prevention(client, auth_headers):
    """Verify that archives containing malicious traversal paths are rejected."""
    repo_res = client.post("/api/v1/repositories", json={
        "full_name": "security-org/zipslip-test"
    }, headers=auth_headers)
    repo_id = repo_res.json()["id"]

    # Create malicious archive with ZipSlip entry
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../escape.txt", "Pwned via ZipSlip")
    malicious_bytes = buf.getvalue()

    res = client.post(
        f"/api/v1/repositories/{repo_id}/upload-zip",
        files={"file": ("evil.zip", malicious_bytes, "application/zip")},
        headers=auth_headers
    )
    assert res.status_code == 400
    assert "Malicious archive entry" in res.json()["detail"] or "Zip Slip" in res.json()["detail"]


def test_file_content_path_traversal_prevention(client, auth_headers):
    """Verify that requests with path traversal are blocked with 400."""
    repo_res = client.post("/api/v1/repositories", json={
        "full_name": "security-org/traversal-test"
    }, headers=auth_headers)
    repo_id = repo_res.json()["id"]

    zip_bytes = create_sample_zip_bytes()
    client.post(
        f"/api/v1/repositories/{repo_id}/upload-zip",
        files={"file": ("project.zip", zip_bytes, "application/zip")},
        headers=auth_headers
    )

    bad_paths = [
        "../../etc/passwd",
        "app/../../../etc/shadow",
        "/etc/hosts",
    ]
    for bad in bad_paths:
        res = client.get(
            f"/api/v1/repositories/{repo_id}/file?path={bad}",
            headers=auth_headers
        )
        assert res.status_code in (400, 404)


def test_github_pat_connection_and_token_protection(client, auth_headers, db_session):
    """Verify that connecting a GitHub PAT encrypts the token at rest and never leaks it."""
    mock_profile = {
        "id": 9991234,
        "login": "octo-engineer",
        "avatar_url": "https://avatars.githubusercontent.com/u/9991234"
    }

    with patch("app.services.github_service.GitHubService.get_user_profile", return_value=mock_profile):
        res = client.post("/api/v1/github/connect-pat", json={
            "token": "ghp_mockPersonalAccessTokenSecret123456789"
        }, headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["is_connected"] is True
        assert data["username"] == "octo-engineer"
        # Token must NEVER appear in response
        assert "token" not in data
        assert "access_token" not in data

        # Check DB to verify encryption
        account = db_session.query(GitHubAccount).first()
        assert account is not None
        assert account.access_token_enc != "ghp_mockPersonalAccessTokenSecret123456789"
        # Verify it can be decrypted with the system secret
        decrypted = decrypt_token(account.access_token_enc)
        assert decrypted == "ghp_mockPersonalAccessTokenSecret123456789"

        # Check status endpoint
        status_res = client.get("/api/v1/github/status", headers=auth_headers)
        assert status_res.status_code == 200
        assert status_res.json()["username"] == "octo-engineer"
        assert "token" not in status_res.json()

        # Disconnect
        disc_res = client.post("/api/v1/github/disconnect", headers=auth_headers)
        assert disc_res.status_code == 204

        status_res2 = client.get("/api/v1/github/status", headers=auth_headers)
        assert status_res2.status_code == 200
        assert status_res2.json()["is_connected"] is False
