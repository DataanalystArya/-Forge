# FORGE: Phase 2 – GitHub Integration & Repository Intelligence Report

**Author**: Principal AI Engineer & Security Architect  
**Date**: November 24, 2026  
**Status**: DELIVERED & FULLY VERIFIED (16/16 Pytest Suite Passed, Next.js Production Build Succeeded)

---

## 1. Executive Summary

Phase 2 introduces **Repository Intelligence** into FORGE, bridging external code sources into an isolated, structured workspace with full Abstract Syntax Tree (AST) symbol extraction and interactive code browsing.

Key accomplishments in this phase:
1. **Secure GitHub Integration**: Connected GitHub accounts with encrypted-at-rest token storage (Fernet/AES-GCM derived from system secret); tokens are strictly masked and never returned in API responses.
2. **Safe Isolated Workspaces**: Repositories are cloned into sandboxed workspace paths (`workspaces/<repo_id>/`) with strict URL validation (preventing protocol smuggling, file:// access, and command injection).
3. **Hardened ZIP Ingestion**: Direct source archive uploads protected by multi-stage security checks (Zip Slip prevention, symlink rejection, 50MB compressed / 200MB uncompressed limits, and compression ratio bomb guards).
4. **Tree-sitter & AST Code Scanner**: Recursively analyzes ingested repositories, extracts functions, classes, methods, and line boundaries, counts lines of code, computes language distributions, and saves persistent `code_artifacts`.
5. **Monaco-Powered Repository Explorer**: Interactive frontend viewer featuring nested collapsible folder trees, AST symbol inspection with jump-to-code, and Monaco Code Editor with syntax highlighting, line numbers, and file metadata.

---

## 2. Security Architecture & Threat Defenses

| Threat Vector | Mitigation Strategy | Verification / Evidence |
| :--- | :--- | :--- |
| **Zip Slip Path Traversal** | Member filenames validated with `Path.is_absolute()` and `os.path.commonpath([target_dir, member_dest]) == target_dir`. Path traversal entries (`../../`) rejected with HTTP 400. | `test_zip_slip_vulnerability_prevention` (Passed). |
| **Symlink Poisoning** | Explicit check on archive member external attributes: `(external_attr >> 16) & 0o120000 == 0o120000` rejected. | `test_zip_upload_scanning_and_tree` (Passed). |
| **Decompression Bombs** | Max compressed size: 50 MB; Max uncompressed size: 200 MB; Max compression ratio: 100x; Max files: 10,000. | Verified in `workspace_service.py`. |
| **Git Clone Command Injection** | Subprocess invocation avoids `shell=True`. Strict URL scheme check (`http`/`https` only) and character whitelist. | `validate_clone_url` enforced in `clone_repository`. |
| **Credential Leakage** | GitHub access tokens encrypted with Fernet prior to database write; decrypted only in transient memory during GitHub API calls; omitted from all Pydantic response models. | `test_github_pat_connection_and_token_protection` (Passed). |
| **File Content Traversal** | API endpoint `/api/v1/repositories/{id}/file?path=...` normalizes input path and validates destination resolves strictly inside `workspaces/<repo_id>/`. | `test_file_content_path_traversal_prevention` (Passed). |
| **Arbitrary Code Execution** | Repositories are treated purely as static data; no build scripts, setup.py, or repository code is executed on the host. | Verified across all scanner and ingestion flows. |

---

## 3. Implemented API Endpoints

### GitHub Integration (`/api/v1/github`)
- `GET /api/v1/github/status`: Returns current GitHub connection status (`is_connected`, `username`, `avatar_url`, `connected_at`). Never exposes tokens.
- `POST /api/v1/github/connect-pat`: Validates and securely connects a GitHub Personal Access Token.
- `POST /api/v1/github/disconnect`: Purges stored credentials and records audit log.
- `GET /api/v1/github/repos`: Lists accessible repositories from connected GitHub account.

### Repository Workspace & Explorer (`/api/v1/repositories`)
- `POST /api/v1/repositories/{id}/clone`: Clones remote repository into workspace and executes structural scan.
- `POST /api/v1/repositories/{id}/upload-zip`: Safely extracts ZIP archive and executes structural scan.
- `GET /api/v1/repositories/{id}/tree`: Returns recursive folder and file hierarchy.
- `GET /api/v1/repositories/{id}/file?path=...`: Returns file contents with language, lines, and size metadata.
- `GET /api/v1/repositories/{id}/symbols`: Returns extracted AST symbols (`CLASS`, `FUNCTION`, `FILE`) with line boundaries.

---

## 4. Frontend Component Architecture

1. **Repository Dashboard (`/repositories`)**:
   - Tab 1: **Ingested Repositories**: Cards displaying active status (`READY`, `PARSING`), file counts, line counts, branch, and link to code explorer.
   - Tab 2: **GitHub Repositories**: Live list of user's GitHub repositories with one-click "Clone & Ingest" button.
   - Modals for connecting GitHub PAT, uploading ZIP archives, and manually registering repositories.

2. **Monaco Repository Explorer (`/repositories/[id]`)**:
   - **Header**: Repository full name, branch, total files, total lines, and language distribution tags (`Python: 65%`, `TypeScript: 35%`).
   - **Left Panel (Tabs)**:
     - *Files Tree*: Collapsible folders, language indicators, file selection.
     - *AST Symbols*: Parsed classes and functions with line numbers (`L1-L24`) for fast navigation.
   - **Right Panel (Monaco Editor)**:
     - Read-only code viewing using `@monaco-editor/react`.
     - VS Dark theme with line numbers and minimap.
     - Dynamic language syntax matching.

---

## 5. Verification Test Suite (16/16 Passed)

```bash
PYTHONPATH=backend backend/venv/bin/pytest backend/tests -v
```
**Results**:
- `test_cross_user_repository_isolation` $\to$ **PASSED**
- `test_expired_jwt_token` $\to$ **PASSED**
- `test_tampered_jwt_token` $\to$ **PASSED**
- `test_inactive_user_access_blocked` $\to$ **PASSED**
- `test_cascade_deletion` $\to$ **PASSED**
- `test_repository_name_path_traversal_rejection` $\to$ **PASSED**
- `test_health_check` $\to$ **PASSED**
- `test_user_registration_and_login` $\to$ **PASSED**
- `test_invalid_login` $\to$ **PASSED**
- `test_database_table_initialization` $\to$ **PASSED**
- `test_database_postgres_resilient_fallback` $\to$ **PASSED**
- `test_zip_upload_scanning_and_tree` $\to$ **PASSED**
- `test_zip_slip_vulnerability_prevention` $\to$ **PASSED**
- `test_file_content_path_traversal_prevention` $\to$ **PASSED**
- `test_github_pat_connection_and_token_protection` $\to$ **PASSED**
- `test_repository_crud_flow` $\to$ **PASSED**

### Frontend Production Build
```bash
cd frontend && npm run build
```
**Results**:
- `✓ Compiled successfully`
- `✓ Generating static pages (16/16)`
- `✓ Dynamic route /repositories/[id] generated`
- Zero TypeScript or compile errors.

---

## 6. Local Testing Instructions

1. **Launch Backend**:
   ```bash
   PYTHONPATH=backend backend/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```
2. **Launch Frontend**:
   ```bash
   cd frontend && npm run dev
   ```
3. Navigate to `http://localhost:3000/repositories`.
4. Click **Upload ZIP** to upload any local repository archive or click **Connect GitHub** to import public/private repositories.
5. Click **Explore Code** to browse files and view code with Monaco Editor.
