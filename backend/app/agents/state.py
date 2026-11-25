"""
Shared LangGraph State Contract for FORGE Multi-Agent System (Phase 4).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class ForgeAgentState(TypedDict, total=False):
    session_id: str
    repository_id: str
    user_id: str
    workspace_dir: str
    issue_title: str
    issue_description: str
    error_logs: str

    # Control & iteration bounds
    max_retries: int
    retry_count: int
    current_agent: str
    status: str  # PLANNING | ANALYZING | BUG_DETECTION | SECURITY_AUDIT | CODING | TESTING | REPAIRING | REVIEWING | COMPLETED | FAILED

    # Agent outputs
    plan: Dict[str, Any]
    repo_summary: Dict[str, Any]
    rag_context: List[Dict[str, Any]]
    graph_context: Dict[str, Any]
    bug_reports: List[Dict[str, Any]]
    security_findings: List[Dict[str, Any]]

    # Patch & diff
    proposed_edits: List[Dict[str, str]]  # [{"file_path": ..., "original_content": ..., "new_content": ...}]
    diff_content: str
    affected_files: List[str]
    patch_rationale: str
    patch_id: Optional[str]

    # Test & review
    test_result: Dict[str, Any]
    review_verdict: str  # APPROVED | CHANGES_REQUESTED | BLOCKED
    review_comments: List[str]
    repair_history: List[Dict[str, Any]]

    # Telemetry & errors
    llm_available: bool
    agent_events: List[Dict[str, Any]]
    errors: List[str]
