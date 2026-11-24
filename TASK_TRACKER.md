# FORGE: Task Tracker & Milestone Registry

Legend:
- `[ ]` Pending
- `[/]` In Progress
- `[x]` Completed
- `[!]` Blocked / Attention Required

---

## Phase 0: Architecture, Planning & Environment Specification
- [x] Workspace inspection and tooling audit (Python 3.14, Node v20, npm 10, git)
- [x] System architecture design & module boundary mapping (`ARCHITECTURE.md`)
- [x] Multi-agent contracts and Pydantic schemas definition
- [x] Phased master development roadmap formulation (`DEVELOPMENT_PLAN.md`)
- [x] Task tracker initialization (`TASK_TRACKER.md`)
- [/] Present Phase 0 architecture and request user approval for Phase 1

---

## Phase 1: Foundation (Core Services & App Shell)
- [x] Initialize Python backend with virtualenv / dependencies (FastAPI, SQLAlchemy, Pydantic, Uvicorn, Jose, Passlib/Bcrypt)
- [x] Configure database engine (SQLite for zero-friction local run + PostgreSQL production adapter)
- [x] Implement Database Models (Users, Repositories, Sessions, Patches, Executions)
- [x] Implement Auth System (JWT tokens, password hashing, `/api/auth/register`, `/api/auth/login`, `/api/auth/me`)
- [x] Initialize Next.js 14 frontend (TypeScript, Tailwind CSS, Shadcn UI setup)
- [x] Implement Global Layout & Navigation (Dark Navy theme, sidebar, breadcrumbs, user session status)
- [x] Implement Auth Pages (`/login`, `/register`) with client validation and token storage
- [x] Implement Main Dashboard (`/dashboard`) with statistics cards, recent sessions, and quick actions
- [x] Create base `docker-compose.yml` for dev services (Postgres, Redis, Qdrant, Neo4j)
- [x] Write and pass backend test suite for authentication and database sessions (12/12 passed, audited)
- [x] Independent Phase 1 verification, security audit, and remediation completed (`PHASE_1_VERIFICATION_REPORT.md`, `PHASE_1_SECURITY_AUDIT.md`, `PHASE_1_REMEDIATION_PLAN.md`)

---

## Phase 2: GitHub & Repository Intelligence
- [ ] Implement GitHub connection service (Personal Access Token / OAuth integration)
- [ ] Implement Repository Ingestion Engine (GitHub clone, ZIP upload, sample benchmark repo loader)
- [ ] Implement File System Scanner with `.gitignore` compliance, binary exclusion, and language detection
- [ ] Implement Project Metadata Extractor (package manifests, entrypoint detection, architecture summary)
- [ ] Build Repository Explorer UI (`/repositories`, `/repositories/[id]`) with file tree viewer
- [ ] Integrate Monaco Editor for code preview with syntax highlighting
- [ ] Write and pass tests for repository ingestion and file parsing

---

## Phase 3: Advanced Code RAG System
- [ ] Integrate Tree-sitter & Python AST parser for syntactic code breakdown
- [ ] Implement semantic chunking (class-level, function-level, method-level with line traceability)
- [ ] Set up Qdrant vector store integration with embedding abstraction (OpenAI / local fallbacks)
- [ ] Implement Rank-BM25 keyword search index for lexical token matching
- [ ] Implement Hybrid Retriever combining Dense Vector + Sparse BM25 via Reciprocal Rank Fusion (RRF)
- [ ] Implement Cross-Encoder Reranking pipeline for top-K refinement
- [ ] Build Code Intelligence UI (`/code-search`) with semantic query input and file/line citation cards
- [ ] Write and pass retrieval relevance and precision tests

---

## Phase 4: Multi-Agent Intelligence (LangGraph Collective)
- [ ] Implement unified LangGraph state graph with memory checkpointer
- [ ] Build Agent 1: Planner Agent (task decomposition, execution plan generation)
- [ ] Build Agent 2: Repository Analysis Agent (architecture report, entry points, dependency profiling)
- [ ] Build Agent 3: Bug Detection Agent (static anomaly detection, error trace correlation)
- [ ] Build Agent 4: Security Audit Agent (vulnerability assessment, Semgrep rule mapping)
- [ ] Build Agent 5: Coding Agent (patch generation, unified diff creation, style adherence)
- [ ] Build Agent 6: Testing Agent (test discovery, test suite synthesis, execution reporting)
- [ ] Build Agent 7: Code Review Agent (maintainability, regression risks, style verification)
- [ ] Build Agent 8: Self-Repair Agent (root cause analysis on failure, iterative repair loop)
- [ ] Implement FastAPI WebSocket broker (`/ws/agents/{session_id}`) for streaming agent turns
- [ ] Build Agent Control Center UI (`/agents`) with React Flow live DAG graph execution view
- [ ] Write multi-agent orchestration integration tests

---

## Phase 5: GraphRAG & Code Knowledge Graph
- [ ] Configure Neo4j driver and schema constraints
- [ ] Implement AST Graph Extractor (Nodes: Files, Classes, Functions, Imports; Edges: CALLS, IMPORTS, INHERITS)
- [ ] Build Graph Traversal Engine (2-hop neighborhood expansion for caller/callee context)
- [ ] Integrate Graph Context with Vector Context into Hybrid Retrieval
- [ ] Build Interactive Dependency Graph Visualizer using React Flow in the frontend
- [ ] Write tests for graph extraction and relationship queries

---

## Phase 6: Autonomous Debugging & Isolated Self-Repair Engine
- [ ] Implement isolated execution engine (Docker container runner with resource limits, timeout guards, and fallback)
- [ ] Implement Debugging Intake API (`/api/debugging/session`) with issue description & logs
- [ ] Implement End-to-End Autonomous Debugging Pipeline:
  - Ingest issue -> Plan -> RAG retrieve -> Detect root cause -> Generate patch -> Execute tests
- [ ] Implement Controlled Self-Repair Loop (bounded retry limit of 3, patch rollback on regression)
- [ ] Implement Code Review verification gate before human sign-off
- [ ] Build AI Debugging Workspace UI (`/debugging/[id]`) with live log streaming, repair timeline, and diff inspector
- [ ] Execute validation test against real intentional bug repository with verified self-repair

---

## Phase 7: GitHub Automation & Pull Request Center
- [ ] Implement Git operations service (branch creation `forge/fix-...`, atomic commit generation)
- [ ] Build interactive Diff Viewer (Monaco Diff Editor: unified & split view)
- [ ] Implement strict **Human-in-the-Loop Approval Gate** (unauthorized write guard)
- [ ] Implement GitHub Pull Request creation via GitHub API
- [ ] Build Pull Request Center UI (`/pull-requests`) with branch status, diff preview, and PR submit button
- [ ] Write tests for Git operations and PR payload generation

---

## Phase 8: Observability, Tracing & DeepEval Evaluation Suite
- [ ] Integrate Langfuse tracing callback for LLM latency, token usage, and step inspection
- [ ] Implement DeepEval benchmark suite for agent outputs, retrieval precision, and patch accuracy
- [ ] Implement System Metrics aggregator (success rate, average duration, repair convergence)
- [ ] Build Monitoring & Observability UI (`/monitoring`) with interactive Recharts charts
- [ ] Run benchmark evaluation and record metrics

---

## Phase 9: Deployment, Documentation & Final Acceptance
- [ ] Create multi-stage production `Dockerfile` for Backend and Frontend
- [ ] Create production-ready `docker-compose.yml` for unified one-click startup
- [ ] Setup GitHub Actions CI/CD pipeline (`.github/workflows/ci.yml`)
- [ ] Write comprehensive `README.md` with architecture diagrams, setup instructions, and API docs
- [ ] Create `.env.example` with clear documentation of all configuration keys
- [ ] Execute full 17-point Functional Acceptance Criteria verification
- [ ] Prepare final delivery report
