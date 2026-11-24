# FORGE: Phase 1 Remediation & Resolution Plan

This document details the issues identified during the independent verification of Phase 1, the immediate remediations implemented, and the operational checklist for upcoming phases.

---

## 1. Issues Identified and Remediated

### Issue 1: SQLite Missing Foreign Key Enforcement
- **Description**: SQLite connections by default do not enforce foreign key constraints unless `PRAGMA foreign_keys = ON;` is executed. Without this, cascade deletions and relational constraints are not guaranteed in local development or test suites.
- **Remediation**: Added an `@event.listens_for(Engine, "connect")` listener in `backend/app/core/database.py` that automatically executes `PRAGMA foreign_keys=ON` on every SQLite connection.
- **Verification**: Verified via `test_cascade_deletion` in `test_audit_security.py` where deleting a user cascades to all related entities.
- **Status**: **RESOLVED**

### Issue 2: Path Traversal & Unrestricted Repository Full Name
- **Description**: `RepositoryBase.full_name` previously accepted arbitrary strings without format validation, exposing future Git clone and directory operations to path traversal (`../../`) or injection.
- **Remediation**: Added a Pydantic `field_validator` in `backend/app/schemas/repository.py` enforcing strict regex `^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$` and disallowing `..`.
- **Verification**: Verified via `test_repository_name_path_traversal_rejection` in `test_audit_security.py` (malicious paths return HTTP 422).
- **Status**: **RESOLVED**

### Issue 3: Unbounded Password Length (Bcrypt Truncation & DoS)
- **Description**: Plaintext passwords lacked an upper boundary, leaving the endpoint susceptible to CPU resource exhaustion from multi-megabyte string hashing, and failing to account for bcrypt's 72-byte truncation boundary.
- **Remediation**: Updated `UserCreate.password` to enforce `min_length=6, max_length=72`.
- **Status**: **RESOLVED**

### Issue 4: Insecure Default Secret Key in Production
- **Description**: The default development `SECRET_KEY` could mistakenly be used in a production deployment if not overridden.
- **Remediation**: Added a validator in `backend/app/core/config.py` that raises a `ValueError` if `ENVIRONMENT == "production"` and the `SECRET_KEY` matches the default placeholder.
- **Status**: **RESOLVED**

---

## 2. Infrastructure Status & Operational Requirements

### Docker Daemon Availability
- **Finding**: The host environment lacks a Docker runtime (`docker` command not found).
- **Classification**: **NOT VERIFIED** (Live container deployment and compose healthchecks).
- **Remediation Steps for Host Operator**:
  1. Install Docker Desktop or OrbStack for macOS.
  2. Launch Docker daemon.
  3. Verify via `docker info`.
  4. Run `docker compose up -d --build` to launch the multi-service cluster.
- **Architecture Integrity**:
  The application is explicitly designed with graceful fallbacks: SQLite operates when PostgreSQL is unavailable, and local isolated subprocess runners operate with timeout guards when Docker is not active. This ensures zero downtime during development.
