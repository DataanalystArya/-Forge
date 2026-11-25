# FORGE: Autonomous AI-Powered Software Engineering Platform

FORGE is a multi-agent software engineering system built with **FastAPI**, **LangGraph**, **Qdrant**, **Neo4j**, and **Next.js 14**. It automates repository ingestion, structural parsing, semantic code search, multi-agent bug detection, AST security audits, patch synthesis, sandbox test verification, bounded self-repair, and GitHub Pull Request automation.

---

## Architecture Overview

```
                                  +-----------------------------+
                                  |   Next.js 14 Dark Navy UI   |
                                  |  (Monaco / ReactFlow / etc) |
                                  +--------------+--------------+
                                                 |
                                                 v
                                  +-----------------------------+
                                  |    FastAPI REST & WebSockets|
                                  +--------------+--------------+
                                                 |
             +--------------------+--------------+--------------------+
             |                    |                                   |
             v                    v                                   v
+------------------------+ +-------------------------+ +------------------------+
|   Code RAG & GraphRAG  | |  LangGraph Multi-Agent  | |   Execution & Sandbox  |
| - Tree-sitter / AST    | | - Planner Agent         | | - Pytest Isolated Run  |
| - Qdrant (all-MiniLM)  | | - Repo Analysis Agent   | | - Git Unified Diff     |
| - BM25Plus Lexical     | | - Bug Detection Agent   | | - Bounded Self-Repair  |
| - Neo4j / NetworkX     | | - Security Audit Agent  | | - Human Approval Gate  |
| - Reciprocal Rank Fuse | | - Coding & Testing Agent| | - Draft GitHub PRs     |
+------------------------+ +-------------------------+ +------------------------+
```

---

## Master Phase Completion Summary

| Phase | Component | Key Highlights | Verification Status |
|---|---|---|---|
| **Phase 1** | Foundation & App Shell | FastAPI, SQLite/PostgreSQL, JWT Auth, Next.js 14 | **Verified** |
| **Phase 2** | Repository Intelligence | GitHub PAT, ZIP ingest, AST parsing, Monaco code viewer | **Verified** |
| **Phase 3** | Code RAG Engine | SentenceTransformers (`all-MiniLM-L6-v2`), Qdrant, BM25Plus, RRF | **Verified** (`pallets/markupsafe`) |
| **Phase 4** | Multi-Agent LangGraph | 8 cooperative agents, MemorySaver checkpointer, WebSockets | **Verified** (3/3 tests passed) |
| **Phase 5** | GraphRAG & Neo4j | AST graph extractor, NetworkX fallback, React Flow visualizer | **Verified** (9/9 tests passed) |
| **Phase 6** | Autonomous Self-Repair | AST bug discovery, minimal unified diffs, pytest sandbox | **Verified** (5/5 tests passed) |
| **Phase 7** | GitHub Automation | Git operations, branch creation, draft PRs, HITL gate | **Verified** (3/3 tests passed) |
| **Phase 8** | Observability & Evaluation | Telemetry, LLM usage/costs, Recharts latency breakdown | **Verified** (4/4 tests passed) |
| **Phase 9** | Deployment & Finalization | Dockerfiles, Docker Compose, CI/CD, 62 unit tests | **Verified** (62/62 passed) |

---

## Prerequisites (macOS)

- **macOS** with Apple Silicon or Intel
- **Python 3.12+** (Python 3.14 compatible)
- **Node.js 20+** and **npm 10+**
- **Git**
- *(Optional)* **Docker & Docker Compose** for multi-container deployment

---

## Option A: Local Mac Zero-Friction Setup (Recommended)

This mode runs the entire stack locally with SQLite and in-memory vector/graph fallback without requiring Docker or external databases.

### 1. Clone & Setup Backend Virtual Environment

```bash
cd /Users/aryaverma/Downloads/Forge

# Create and activate virtual environment
python3 -m venv backend/venv
source backend/venv/bin/activate

# Install all backend dependencies
pip install -r backend/requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Key environment variables in `.env`:
- `DATABASE_URL=sqlite:///./forge.db`
- `QDRANT_USE_MEMORY=true`
- `NEO4J_USE_MEMORY=true`
- `OPENAI_API_KEY=` *(optional — leave blank for deterministic AST/Pytest mode)*
- `OPENAI_MODEL=gpt-4o`

### 3. Run Backend Server

```bash
cd /Users/aryaverma/Downloads/Forge
PYTHONPATH=backend QDRANT_USE_MEMORY=true HF_HUB_OFFLINE=1 backend/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
The FastAPI backend will start at `http://127.0.0.1:8000`. Swagger API docs are at `http://127.0.0.1:8000/docs`.

### 4. Setup & Run Frontend

In a separate terminal:

```bash
cd /Users/aryaverma/Downloads/Forge/frontend

# Install node dependencies
npm install

# Start development server
npm run dev
```

The Next.js 14 frontend will start at `http://localhost:3000`.

---

## Option B: Docker Compose Deployment

To run with full production services (PostgreSQL, Redis, Qdrant persistent server, and Neo4j graph database):

```bash
cd /Users/aryaverma/Downloads/Forge

# Build and start all services
docker compose up -d --build

# View container logs
docker compose logs -f backend
```

Services exposed:
- **Frontend App**: `http://localhost:3000`
- **Backend API**: `http://localhost:8000`
- **Qdrant Dashboard**: `http://localhost:6333/dashboard`
- **Neo4j Browser**: `http://localhost:7474` (User: `neo4j`, Password: `forge_graph`)
- **PostgreSQL**: `localhost:5432`
- **Redis**: `localhost:6379`

---

## Running the Automated Test Suite

To run all 62 backend verification tests across all 9 phases:

```bash
cd /Users/aryaverma/Downloads/Forge
PYTHONPATH=backend QDRANT_USE_MEMORY=true backend/venv/bin/pytest backend/tests/ -v --tb=short
```

Expected result:
```
================== 62 passed, 18 warnings in ~95s ==================
```

To verify frontend compilation:

```bash
cd /Users/aryaverma/Downloads/Forge/frontend
npm run build
```

---

## End-to-End Workflow Walkthrough

1. **Authentication**: Register a new user at `http://localhost:3000/register`, then login.
2. **Repository Ingestion**: Navigate to `/repositories`, connect via GitHub PAT or upload a repository ZIP.
3. **AST Exploration**: Click into the repository to view the Monaco code explorer and parsed AST symbols.
4. **Knowledge Graph (GraphRAG)**: Click `"Knowledge Graph"` to extract and explore the AST relationship graph (Files, Classes, Functions, Imports, Calls).
5. **Code Intelligence (RAG)**: Open `/code-search` to index chunks and query code using Semantic, BM25, or Hybrid RRF retrieval.
6. **Multi-Agent Control**: Open `/agents` to inspect the 8-agent LangGraph execution DAG and launch automated sessions.
7. **Autonomous Debugging & Self-Repair**:
   - Navigate to `/debugging`.
   - Select a repository, enter an issue description or paste failing pytest error logs.
   - Click `"Initiate Autonomous Debugging"`.
   - Watch the multi-agent pipeline: *Planner* decomposes tasks, *Bug Detector* localizes AST flaws, *Coding Agent* generates a minimal unified diff, *Testing Agent* executes real pytest in an isolated workspace, and *Self-Repair Agent* iterates if tests fail (up to 3 bounded retries).
   - Once verified, review the unified diff and click `"Approve & Apply Patch"`.
8. **Pull Request Center**:
   - Navigate to `/pull-requests`.
   - Select the approved session and enter your GitHub PAT.
   - Click `"Approve & Open GitHub Pull Request"`.
   - A draft Pull Request is opened on GitHub without auto-merging.
9. **Observability**: Open `/monitoring` to view real-time latency graphs, token consumption, estimated costs, and AI benchmark evaluations.

---

## Security & Human-in-the-Loop Rules

- **Zero Fake Success Policy**: Never claims a bug is fixed unless test execution genuinely passes in the sandbox.
- **Human Approval Gate**: Never merges code or modifies remote branches automatically. Explicit approval is required before patch commit and PR submission.
- **Credential Protection**: GitHub PATs and user secrets are encrypted at rest with AES-256-GCM and never logged in error traces.
- **Path Traversal Defense**: All workspace operations are strictly bounded to prevent Zip Slip or directory escape attacks.
