# FORGE: Phased Master Development Plan

This document establishes the roadmap, milestones, testing criteria, and deliverables for engineering the **FORGE** platform across 10 progressive phases (Phase 0 to Phase 9).

---

## Roadmap Overview

```
Phase 0: Architecture, Planning & Environment Specification [CURRENT]
Phase 1: Foundation (Next.js Frontend, FastAPI Backend, Core DB & Auth)
Phase 2: GitHub & Repository Intelligence (Ingestion, AST Parsing, File Explorer)
Phase 3: Advanced Code RAG (Tree-sitter, Qdrant, BM25 Hybrid, Reranking)
Phase 4: Multi-Agent Intelligence (LangGraph 8-Agent Collective, WebSocket Streaming)
Phase 5: GraphRAG & Code Knowledge Graph (Neo4j, Call Graph, React Flow)
Phase 6: Autonomous Debugging & Isolated Self-Repair Engine (Sandbox, Pytest)
Phase 7: GitHub Automation & PR Center (Branch, Commit, Diff, HITL Approval)
Phase 8: Observability, Tracing & DeepEval Evaluation Suite
Phase 9: Production Docker Compose, CI/CD, Documentation & Acceptance Test
```

---

## Detailed Phase Breakdown

### Phase 0 – Architecture and Planning
- **Objectives**:
  - Inspect workspace and environment tooling (Python, Node, Docker, etc.).
  - Formalize system architecture, agent contracts, database schemas, and API routes.
  - Create `ARCHITECTURE.md`, `DEVELOPMENT_PLAN.md`, and `TASK_TRACKER.md`.
  - Establish engineering conventions and security protocols.
- **Deliverables**:
  - `ARCHITECTURE.md`
  - `DEVELOPMENT_PLAN.md`
  - `TASK_TRACKER.md`
  - Master presentation to user for Phase 1 sign-off.
- **Verification**: User review and explicit approval.

---

### Phase 1 – Foundation (Core Services & App Shell)
- **Objectives**:
  - Bootstrap the backend: FastAPI application structure, SQLAlchemy models, SQLite/PostgreSQL configuration, Pydantic v2 schemas.
  - Bootstrap the frontend: Next.js 14 App Router, TypeScript, Tailwind CSS, Shadcn UI theme system, Lucide icons.
  - Implement authentication: JWT-based user authentication (register, login, me, session persistence).
  - Build foundational layout: Sidebar navigation, header with system status, responsive dark-mode theme.
  - Setup Docker Compose for local development (Postgres, Redis, Qdrant, Neo4j).
- **Deliverables**:
  - `backend/app/main.py` with health check and API v1 routers.
  - `backend/app/core/` (config, database, security, auth).
  - `backend/app/models/` and `backend/app/schemas/`.
  - `frontend/` with working Next.js App Router, auth pages (`/login`, `/register`), and base dashboard layout (`/dashboard`).
  - Unit tests verifying authentication and database transactions.
- **Verification**: `pytest` passes on auth/models; Next.js builds cleanly with zero TypeScript errors.

---

### Phase 2 – GitHub & Repository Intelligence
- **Objectives**:
  - Implement GitHub OAuth / Personal Access Token connection flow.
  - Build repository importer (remote GitHub clone, ZIP upload, and sample repo loader).
  - Implement file scanning, language detection, and `.gitignore` filtration.
  - Extract project metadata (dependencies, entry points, package definitions).
  - Build the Repository Explorer UI: File tree viewer, metadata inspector, Monaco code viewer.
- **Deliverables**:
  - `backend/app/services/github_service.py`
  - `backend/app/services/repo_service.py`
  - `backend/app/api/repositories.py`
  - Frontend Repository Explorer at `/repositories` and `/repositories/[id]`.
- **Verification**: Successfully ingest a sample repository, verify file tree rendering and metadata extraction.

---

### Phase 3 – Advanced Code RAG System
- **Objectives**:
  - Integrate Tree-sitter & AST parsers for multi-language code structure extraction (Python, TypeScript, JavaScript).
  - Implement intelligent code chunking (function-level, class-level, module-level).
  - Configure Qdrant vector database client with embedding model provider (OpenAI / HuggingFace BGE).
  - Implement Rank-BM25 keyword index for sparse lexical retrieval.
  - Build hybrid fusion (Reciprocal Rank Fusion - RRF) and cross-encoder reranking.
  - Build Code Intelligence UI: Natural language code search, snippet previews with exact line links.
- **Deliverables**:
  - `backend/app/rag/parser.py` (Tree-sitter / AST)
  - `backend/app/rag/chunker.py`
  - `backend/app/rag/vector_store.py` (Qdrant)
  - `backend/app/rag/bm25_store.py`
  - `backend/app/rag/hybrid_retriever.py`
  - Frontend `/code-search` interface.
- **Verification**: Index a repository; execute hybrid queries and assert semantic and exact identifier recall.

---

### Phase 4 – Multi-Agent Intelligence (LangGraph Orchestration)
- **Objectives**:
  - Implement the central LangGraph state graph with checkpointer.
  - Implement the 8 dedicated agents with strict Pydantic contracts:
    1. Planner Agent
    2. Repository Analysis Agent
    3. Bug Detection Agent
    4. Security Audit Agent (incorporating Semgrep rules)
    5. Coding Agent
    6. Testing Agent
    7. Code Review Agent
    8. Self-Repair Agent
  - Implement WebSocket event streaming for real-time turn-by-turn state dispatch.
  - Build Agent Control Center UI with React Flow visual node execution tracking.
- **Deliverables**:
  - `backend/app/agents/` (state, graph, planner, repo_analyst, bug_detector, security, coder, tester, reviewer, self_repair).
  - `backend/app/api/agents.py` & WebSocket endpoint `/ws/agents/{session_id}`.
  - Frontend `/agents` visual control center.
- **Verification**: Run end-to-end multi-agent orchestration simulation with streaming updates.

---

### Phase 5 – GraphRAG & Code Knowledge Graph
- **Objectives**:
  - Configure Neo4j integration and connection manager.
  - Parse AST symbol tables into graph nodes (Files, Classes, Functions, Imports).
  - Extract call graphs (`CALLS`), inheritance (`INHERITS`), and dependencies (`DEPENDS_ON`).
  - Implement graph traversal retrieval (2-hop neighborhood expansion).
  - Render interactive dependency graphs using React Flow in the frontend.
- **Deliverables**:
  - `backend/app/graph/neo4j_client.py`
  - `backend/app/graph/graph_extractor.py`
  - `backend/app/api/graph.py`
  - Frontend Graph Explorer view in `/repositories/[id]/graph`.
- **Verification**: Query dependencies of a function and assert caller/callee resolution.

---

### Phase 6 – Autonomous Debugging & Isolated Self-Repair Engine
- **Objectives**:
  - Build isolated execution harness (Docker container runner with resource limits, timeout guards, and fallback).
  - Implement automated bug intake (description, error log, stack trace).
  - Coding Agent generates diff patch; Sandbox executes Pytest suite.
  - If tests fail, Self-Repair Agent analyzes failure, coordinates with Coding Agent, and re-tests (bounded to 3 iterations).
  - Code Review Agent performs independent sanity check on passing patch.
  - Build AI Debugging Workspace UI with live logs, repair timeline, and Monaco diff viewer.
- **Deliverables**:
  - `backend/app/execution/sandbox.py`
  - `backend/app/services/debugging_service.py`
  - `backend/app/api/debugging.py`
  - Frontend `/debugging` workspace.
- **Verification**: Execute a controlled test bug (e.g. off-by-one error with failing test), verify autonomous detection, patch generation, test execution, self-repair, and review pass.

---

### Phase 7 – GitHub Automation & Pull Request Center
- **Objectives**:
  - Implement Git branch generation (`forge/fix-...`).
  - Implement Git commit generation with conventional commit messages.
  - Build Monaco unified and side-by-side Diff Viewer.
  - Enforce the **Human-in-the-Loop Approval Gate**: require explicit UI button click to commit or push.
  - Implement GitHub PR creation via GitHub REST API.
  - Build Pull Request Center UI (`/pull-requests`).
- **Deliverables**:
  - `backend/app/services/git_service.py`
  - `backend/app/api/pull_requests.py`
  - Frontend `/pull-requests` dashboard.
- **Verification**: Mock/real PR creation flow with audit log entry and approval state machine.

---

### Phase 8 – Observability, Monitoring & Evaluation
- **Objectives**:
  - Integrate Langfuse callback handler for token metrics, latency, and trace inspection.
  - Implement DeepEval benchmark suite to evaluate:
    - Bug detection recall
    - Patch correctness
    - Retrieval context precision
    - Self-repair convergence rate
  - Build Monitoring & Evaluation Dashboard (`/monitoring`) with Recharts.
- **Deliverables**:
  - `backend/app/observability/langfuse_tracer.py`
  - `backend/app/eval/evaluation_suite.py`
  - Frontend `/monitoring` analytics view.
- **Verification**: Capture execution traces and display real-time metric graphs.

---

### Phase 9 – Deployment, Documentation & Final Acceptance
- **Objectives**:
  - Finalize multi-stage Dockerfiles (`backend/Dockerfile`, `frontend/Dockerfile`).
  - Comprehensive `docker-compose.yml` for unified one-command launch.
  - GitHub Actions CI/CD workflows for linting, testing, and container build.
  - Complete `README.md` with architecture diagrams, quickstart guide, environment variable documentation.
  - Execute full End-to-End Functional Acceptance Workflow (Criteria 1-17 from Master Prompt).
- **Deliverables**:
  - `docker-compose.yml` & `.env.example`
  - `.github/workflows/ci.yml`
  - Comprehensive `README.md`
  - Full passing test suite.
- **Verification**: Complete end-to-end autonomous bug-fixing run verified.
