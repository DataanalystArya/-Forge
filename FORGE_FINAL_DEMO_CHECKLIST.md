# FORGE – Final Demo Checklist

**Version:** Phase 10+ (Post-Authentication Fix)  
**Last Updated:** 2026-11-26

---

## ⬛ Pre-Demo Setup (Do Once)

```bash
# Terminal 1 — Start Backend
cd /Users/aryaverma/Downloads/Forge
PYTHONPATH=backend backend/venv/bin/uvicorn app.main:app \
  --host 127.0.0.1 --port 8000 --reload --reload-dir backend/app

# Terminal 2 — Start Frontend
cd /Users/aryaverma/Downloads/Forge/frontend
npm run start -- -p 3000
```

Then verify:
- [ ] `curl http://127.0.0.1:8000/api/v1/health` → `{"status":"healthy","database":"connected"}`
- [ ] Browser opens `http://localhost:3000` and shows FORGE landing page

---

## ✅ Demo Flow (Step-by-Step)

### Step 1 – Authentication (2 min)
- [ ] Go to `http://localhost:3000`
- [ ] Click **"Launch Platform"** → Register page
- [ ] Register with any email (including Gmail) and a 6+ character password
- [ ] After register, automatically redirected to **Dashboard**
- [ ] User avatar and email appear in top-right header
- [ ] **ENGINE: ONLINE** shown in green

**Talking point:** "Single JWT authentication with 7-day sessions. Token stored in localStorage with cookie-based session indicator for Next.js middleware route protection."

---

### Step 2 – Repository Management (3 min)
- [ ] Click **Repository Explorer** in sidebar
- [ ] Click **"+ Add Repository"** (Create tab)
- [ ] Enter name `demo/my-project`, click Create → shows in list
- [ ] Click **"Upload ZIP"**
- [ ] Upload any small Python project ZIP (or use the existing calc workspace)

**Alternative (requires internet):**
- [ ] Click **"Connect GitHub"**
- [ ] Enter a GitHub PAT with `repo:read` scope
- [ ] Import any public repo (e.g., `psf/requests`)

**Talking point:** "Repositories are stored in SQLite with metadata. Files are extracted, AST-parsed with Tree-sitter, and chunked for semantic indexing."

---

### Step 3 – Code Intelligence / RAG (3 min)
- [ ] Click **Code Intelligence** in sidebar
- [ ] Select the indexed repository from dropdown
- [ ] Click **"Index Repository"** → watch status update (PENDING → RUNNING → COMPLETED)
- [ ] Once COMPLETED: type a query e.g., `"how does authentication work"`
- [ ] Switch between **Hybrid**, **Semantic**, **BM25** search modes
- [ ] Show results with file paths, line numbers, relevance scores

**Talking point:**
- "Semantic search uses `all-MiniLM-L6-v2` (384-dimensional embeddings) stored in Qdrant."
- "BM25 is keyword-based using Rank-BM25 on SQLite-persisted chunks."
- "Hybrid combines both via Reciprocal Rank Fusion (RRF) — no single-mode bias."
- "In-memory Qdrant for local development. Set `QDRANT_USE_MEMORY=False` + Docker for persistence."

---

### Step 4 – Security Audit (2 min)
- [ ] Click **Security Center** in sidebar
- [ ] Select the repository
- [ ] Click **"Run Security Scan"**
- [ ] Show findings: severity badges (CRITICAL, HIGH, MEDIUM, LOW), file + line number, recommendation

**Talking point:** "Static AST analysis using Python's `ast` module. Detects: `eval()`/`exec()` usage, hardcoded secrets, dangerous subprocess calls, SQL injection patterns. No Semgrep dependency — purely Python."

---

### Step 5 – AI Debugging & Agent Workflow (4 min)
- [ ] Click **AI Debugging** in sidebar
- [ ] Select a repository
- [ ] Enter a title: `"Fix the failing test_add test"`
- [ ] Enter error logs: `"AssertionError: assert -1 == 5 where -1 = add(2, 3)"`
- [ ] Click **"Launch Debugging Session"**
- [ ] Show session detail: 8 agent phases, timeline, patch diffs, security findings, test results

**Talking point (no LLM key):** "Without an LLM API key, agents run in deterministic mode — real file analysis, real security rules, real pytest execution, but templated text summaries."

**Talking point (with LLM key):** "With OpenAI/Gemini/Ollama configured in Settings, agents produce LLM-generated root cause analysis, targeted code patches, and self-repair iteration."

---

### Step 6 – Agent Control Center (2 min)
- [ ] Click **Agent Control Center** in sidebar
- [ ] Show the **ReactFlow DAG** — 8 nodes, animated edges
- [ ] Select a completed session from the dropdown
- [ ] Show execution timeline: each agent, duration, status (COMPLETED/FAILED)

**Talking point:** "LangGraph state machine with Pydantic-validated state objects. Each agent node reads from shared state and writes results back — Planner, Repo Analyst, Bug Detector, Security Auditor, Coder, Tester, Reviewer, Self-Repair."

---

### Step 7 – Testing Center (2 min)
- [ ] Click **Testing Center** in sidebar
- [ ] Select the repository
- [ ] Leave test path empty (runs entire workspace)
- [ ] Click **"Run Tests in Sandbox"**
- [ ] Show stdout/stderr output — real pytest output

**Talking point:** "Runs pytest as an isolated subprocess in the repository workspace directory. Captures stdout, stderr, exit code. Exit code 5 = no test files found. Exit code 1 = tests found, some failed. Exit code 0 = all pass."

---

### Step 8 – Pull Requests (1 min)
- [ ] Click **Pull Requests** in sidebar
- [ ] Show empty list (expected without GitHub PAT with write scope)

**Talking point:** "After a debugging session completes and patches are approved, the Automation Engine creates a git branch with the patches and submits a GitHub Pull Request. Requires a GitHub PAT with `repo` scope."

---

### Step 9 – Monitoring & Evaluation (1 min)
- [ ] Click **Monitoring & Eval** in sidebar
- [ ] Show: total sessions, success rate, test pass/fail counts
- [ ] Show: LLM usage log (if any API calls made)
- [ ] Show: agent execution breakdown chart (if sessions exist)

**Talking point:** "All agent sessions, LLM API calls, test results, and evaluation metrics are logged to SQLite. This provides full observability over the autonomous engineering loop."

---

### Step 10 – Settings (1 min)
- [ ] Click **Settings** in sidebar
- [ ] Show Infrastructure Status: `Database: connected (sqlite)`, `Qdrant: connected (memory)`, `Graph: connected (networkx_disk)`
- [ ] Show LLM configuration panel with provider options (OpenAI, Gemini, OpenRouter, Ollama, Custom)

**Talking point:** "LLM provider is pluggable — any OpenAI-compatible API works. Ollama enables fully local/offline operation."

---

## ⚙️ What Works WITHOUT Any API Keys

| Feature | Works |
|---------|-------|
| Registration & Login | ✅ |
| Repository import (ZIP) | ✅ |
| File tree, AST symbols | ✅ |
| RAG indexing + all 3 search modes | ✅ |
| GraphRAG extraction + subgraph | ✅ |
| Security static scanning | ✅ |
| Agent session (deterministic mode) | ✅ |
| Sandbox test execution (real pytest) | ✅ |
| Monitoring telemetry | ✅ |

## 🔑 What REQUIRES External Credentials

| Feature | Requires |
|---------|---------|
| LLM-generated analysis & patches | `OPENAI_API_KEY` (or Gemini/OpenRouter/Ollama) |
| GitHub repository clone | GitHub PAT (read scope) |
| Pull Request creation | GitHub PAT (repo:write scope) |
| Persistent vector storage | Docker + Qdrant container |

---

## 💬 Fallback Talking Points for Blocked Features

**If asked why agents don't generate real patches:**
> "LLM API key is not configured for this demo environment. In production, this would call GPT-4o-mini / Gemini 2.0 Flash and generate a real unified diff patch. The agent architecture, state machine, and workflow are identical — only the LLM call is stubbed."

**If asked why PRs don't appear:**
> "Creating a GitHub Pull Request requires a GitHub Personal Access Token with repository write permissions. The backend automation engine (`github_automation.py`) implements this fully — it creates a branch, commits the patches, and calls the GitHub API. We haven't authorized an external test repository for this demo."

**If asked why vector search resets on restart:**
> "We're running Qdrant in in-memory mode for local development. Setting `QDRANT_USE_MEMORY=False` and running a Qdrant Docker container provides full persistence. BM25 search always persists since it reads from SQLite."

**If asked about production deployment:**
> "The backend deploys to Render/Railway with PostgreSQL and a persistent Qdrant instance. The frontend deploys to Vercel. Environment variables are configured in the hosting platform. The Vercel deployment at `forge-ai-neon-six.vercel.app` is the production frontend URL."

---

## 🚨 Common Demo Failures & Quick Fixes

| Symptom | Fix |
|---------|-----|
| Backend shows 404 | Check it's running on :8000; check `PYTHONPATH=backend` |
| "Could not validate credentials" | Re-login; token may have been cleared by previous session |
| Indexing stays at RUNNING | Wait 10-15s for `all-MiniLM-L6-v2` to load on first use |
| Search returns 0 results | Ensure indexing completed first (status = COMPLETED) |
| Testing shows "no workspace" | Only cloned repos have workspaces; not register-only repos |
| Frontend shows blank page | Rebuild: `rm -rf .next && npm run build && npm run start -- -p 3000` |
