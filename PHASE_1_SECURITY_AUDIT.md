# FORGE: Phase 1 Security Audit

**Auditor Role**: Principal Security Engineer  
**Date**: November 24, 2026  
**Scope**: Backend API, Authentication, Relational Layer, Input Validation, Configuration Hygiene

---

## 1. Threat Modeling & Vulnerability Analysis

### 1.1 Authentication & Cryptography
- **Password Storage**:
  - Implemented using `bcrypt.hashpw` with salt rounds = 12.
  - Plaintext password input is restricted to `min_length=6` and `max_length=72`. Enforcing 72 bytes prevents bcrypt truncation bypasses and computational DoS from oversized payload submissions.
  - **Verdict**: **SECURE**
- **JWT Token Construction & Expiration**:
  - Signed using `HS256` with claims: `sub`, `exp`, `iat`, `iss`.
  - Expiration verified: Expired timestamps reject authorization with HTTP 401.
  - Signature tampering verified: Modified signature bytes reject authorization with HTTP 401.
  - Production Secret Guard: Added Pydantic field validator preventing application bootstrap in `ENVIRONMENT=production` if `SECRET_KEY` contains default placeholder strings.
  - **Verdict**: **SECURE**

### 1.2 Multi-Tenancy & Authorization (IDOR Prevention)
- **Repository Isolation**:
  - All repository queries filter by both `Repository.id == repo_id` AND `Repository.user_id == current_user.id`.
  - Attempts by unauthorized users to read or delete another user's repository fail with HTTP 404 (preventing user enumeration).
  - Deletion of User accounts cascades cleanly to related models.
  - **Verdict**: **SECURE**

### 1.3 Injection & Traversal Defense
- **SQL Injection**:
  - All queries utilize SQLAlchemy ORM parameterized queries or bound expressions. No raw concatenated strings are executed.
  - **Verdict**: **SECURE**
- **Path Traversal & Malicious Repo Names**:
  - Potential Risk Identified: A user could supply `../../etc/passwd` or shell escape characters in `full_name`.
  - Remediation Applied: Added strict regex validation `^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$` with explicit `".." not in v` check. Malicious inputs return HTTP 422 Unprocessable Entity.
  - **Verdict**: **SECURE**

### 1.4 Network Security & CORS
- **CORS Configuration**:
  - Bound strictly to defined local origins (`http://localhost:3000`, `http://localhost:8000`, `http://127.0.0.1:3000`, `http://127.0.0.1:8000`).
  - No wildcard `*` with credentials.
  - **Verdict**: **SECURE**

### 1.5 Future Attack Surface Assessment (Phase 2 & 6 Preparation)
1. **Repository Cloning & SSRF**:
   When Phase 2 introduces `git clone`, repository URLs must be restricted to authenticated GitHub endpoints and validated against private IP ranges (`127.0.0.1`, `169.254.169.254`, `10.0.0.0/8`, `192.168.0.0/16`) to prevent Cloud Metadata SSRF.
2. **ZIP Ingestion & ZipSlip**:
   When Phase 2 implements local ZIP uploads, extraction must validate normalized destination paths (`os.path.commonpath`) to prevent directory traversal / ZipSlip attacks.
3. **Arbitrary Code Execution**:
   In Phase 6, test execution must strictly run inside Docker containers with non-root users, CPU/memory limits, read-only file systems, and network isolation (`--network none`). Untrusted code must never execute directly on the host.

---

## 2. Docker & Container Security Audit

- **Backend Dockerfile**:
  - Base: `python:3.14-slim`.
  - Execution User: `USER forgeuser` (UID 1000). Runs without root privileges.
  - Healthcheck: Configured with `curl -f http://localhost:8000/api/v1/health`.
  - Socket Isolation: Docker daemon socket is NOT mounted into application containers.
- **Frontend Dockerfile**:
  - Base: `node:20-alpine`.
  - Execution User: `USER nextjs` (UID 1001).
  - Multi-stage build isolates build dependencies from production runner.
- **Docker Daemon Status**:
  - **Runtime NOT VERIFIED**: Docker binary is not installed on the current host. Container isolation cannot be exercised until Docker or OrbStack is installed.
