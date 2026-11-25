"""
LangGraph Multi-Agent Orchestrator — Phase 4.

Graph topology:
  planner -> repo_analyst -> bug_detector -> security_auditor -> coding -> testing
  testing --(tests failed & has_edits & retry < max_retries)--> self_repair -> coding
  testing --(otherwise)--> code_review -> END
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.agents.nodes import (
    bug_detector_node,
    code_review_node,
    coding_node,
    planner_node,
    repo_analyst_node,
    security_auditor_node,
    self_repair_node,
    testing_node,
)
from app.agents.state import ForgeAgentState
from app.services.ws_manager import ws_manager

logger = logging.getLogger("forge.graph")

_checkpointer = MemorySaver()


def _route_after_testing(state: ForgeAgentState) -> str:
    test_res = state.get("test_result", {})
    has_edits = bool(state.get("proposed_edits"))
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)

    if (
        has_edits
        and test_res.get("tests_found")
        and not test_res.get("passed", False)
        and retry_count < max_retries
    ):
        return "self_repair"
    return "code_review"


def build_forge_graph():
    builder = StateGraph(ForgeAgentState)

    builder.add_node("planner", planner_node)
    builder.add_node("repo_analyst", repo_analyst_node)
    builder.add_node("bug_detector", bug_detector_node)
    builder.add_node("security_auditor", security_auditor_node)
    builder.add_node("coding", coding_node)
    builder.add_node("testing", testing_node)
    builder.add_node("self_repair", self_repair_node)
    builder.add_node("code_review", code_review_node)

    builder.set_entry_point("planner")
    builder.add_edge("planner", "repo_analyst")
    builder.add_edge("repo_analyst", "bug_detector")
    builder.add_edge("bug_detector", "security_auditor")
    builder.add_edge("security_auditor", "coding")
    builder.add_edge("coding", "testing")
    builder.add_conditional_edges(
        "testing",
        _route_after_testing,
        {
            "self_repair": "self_repair",
            "code_review": "code_review",
        },
    )
    builder.add_edge("self_repair", "coding")
    builder.add_edge("code_review", END)

    return builder.compile(checkpointer=_checkpointer)


forge_graph = build_forge_graph()


def run_session_sync(initial_state: ForgeAgentState) -> Dict[str, Any]:
    """Execute the LangGraph workflow synchronously for a session."""
    session_id = initial_state["session_id"]
    config = {"configurable": {"thread_id": session_id}}
    return forge_graph.invoke(initial_state, config=config)


def _run_session_background(initial_state: ForgeAgentState) -> None:
    from app.core.database import SessionLocal
    from app.models.session import DebuggingSession

    session_id = initial_state["session_id"]
    try:
        final_state = run_session_sync(initial_state)
        db = SessionLocal()
        try:
            sess = db.query(DebuggingSession).filter(DebuggingSession.id == session_id).first()
            if sess:
                sess.status = "COMPLETED"
                sess.current_phase = "CodeReviewAgent"
                sess.retry_count = final_state.get("retry_count", 0)
                db.commit()
        finally:
            db.close()

        ws_manager.broadcast_sync(
            session_id,
            {
                "type": "session_completed",
                "session_id": session_id,
                "status": "COMPLETED",
                "review_verdict": final_state.get("review_verdict"),
                "bugs_count": len(final_state.get("bug_reports", [])),
                "security_count": len(final_state.get("security_findings", [])),
            },
        )
    except Exception as exc:
        logger.error(f"LangGraph execution failed for session {session_id}: {exc}", exc_info=True)
        db = SessionLocal()
        try:
            sess = db.query(DebuggingSession).filter(DebuggingSession.id == session_id).first()
            if sess:
                sess.status = "FAILED"
                sess.current_phase = "FAILED"
                db.commit()
        finally:
            db.close()

        ws_manager.broadcast_sync(
            session_id,
            {"type": "session_failed", "session_id": session_id, "error": str(exc)},
        )


def start_agent_session(
    session_id: str,
    repository_id: str,
    user_id: str,
    title: str,
    description: str,
    error_logs: str = "",
    max_retries: int = 3,
) -> None:
    workspace_dir = os.path.join(os.getcwd(), "workspaces", repository_id)
    initial_state: ForgeAgentState = {
        "session_id": session_id,
        "repository_id": repository_id,
        "user_id": user_id,
        "workspace_dir": workspace_dir,
        "issue_title": title,
        "issue_description": description,
        "error_logs": error_logs or "",
        "max_retries": max_retries,
        "retry_count": 0,
        "status": "PLANNING",
        "agent_events": [],
        "errors": [],
    }
    t = threading.Thread(
        target=_run_session_background,
        args=(initial_state,),
        daemon=True,
        name=f"forge-agent-{session_id[:8]}",
    )
    t.start()
