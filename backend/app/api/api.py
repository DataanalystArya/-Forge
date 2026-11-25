from fastapi import APIRouter
from app.api import auth, repositories, dashboard, health, github, rag, agents, graph, debugging, github_automation, monitoring

api_router = APIRouter()

# Healthcheck
api_router.include_router(health.router)

# Authentication endpoints
api_router.include_router(auth.router)

# GitHub integration endpoints
api_router.include_router(github.router)

# Repositories endpoints
api_router.include_router(repositories.router)

# Dashboard statistics
api_router.include_router(dashboard.router)

# Phase 3 — Code RAG
api_router.include_router(rag.router)

# Phase 4 — Multi-Agent Orchestration
api_router.include_router(agents.router)

# Phase 5 — GraphRAG
api_router.include_router(graph.router)

# Phase 6 — Autonomous Debugging
api_router.include_router(debugging.router)

# Phase 7 — GitHub Automation
api_router.include_router(github_automation.router)

# Phase 8 — Monitoring & Evaluation
api_router.include_router(monitoring.router)
