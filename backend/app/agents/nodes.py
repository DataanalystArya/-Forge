"""
LangGraph Agent Nodes — Phase 4 (Multi-Agent Intelligence) & Phase 6 (Debugging/Repair).

Implements all 8 FORGE agents:
1. Planner Agent
2. Repository Analysis Agent
3. Bug Detection Agent
4. Security Audit Agent
5. Coding Agent
6. Testing Agent
7. Code Review Agent
8. Self-Repair Agent

Every agent reads actual repository files, DB artifacts, RAG chunks, and
GraphRAG context (when indexed), logs an AgentExecution row, and emits a live
WebSocket event. LLM reasoning uses LLMService; if OPENAI_API_KEY is not set,
agents run deterministic AST/static/RAG/pytest analysis and record the exact
LLM unavailability without fabricating AI outputs.
"""
from __future__ import annotations

import ast
import difflib
import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.agents.state import ForgeAgentState
from app.services.llm_service import LLMService
from app.services.scanner_service import IGNORED_DIRECTORIES, IGNORED_EXTENSIONS
from app.services.ws_manager import ws_manager

logger = logging.getLogger("forge.agents")

# ---------------------------------------------------------------------------
# Security & Static Bug Rules (Deterministic, Zero Code Execution)
# ---------------------------------------------------------------------------

_SECURITY_RULES = [
    ("FORGE-SEC-001", "CRITICAL", re.compile(r"\beval\s*\("), "Use of eval() allows arbitrary code execution.", "Replace eval() with ast.literal_eval() or explicit parsing."),
    ("FORGE-SEC-002", "CRITICAL", re.compile(r"\bexec\s*\("), "Use of exec() allows arbitrary code execution.", "Refactor dynamic execution into explicit function dispatch."),
    ("FORGE-SEC-003", "HIGH", re.compile(r"subprocess\.\w+\([^)]*shell\s*=\s*True"), "subprocess called with shell=True risks command injection.", "Pass argument list and set shell=False."),
    ("FORGE-SEC-004", "HIGH", re.compile(r"\bos\.system\s*\("), "os.system() invokes a subshell and risks command injection.", "Use subprocess.run([...], shell=False)."),
    ("FORGE-SEC-005", "HIGH", re.compile(r"\bpickle\.loads?\s*\("), "Deserializing untrusted data with pickle can execute arbitrary code.", "Use JSON or a schema-validated serializer."),
    ("FORGE-SEC-006", "MEDIUM", re.compile(r"yaml\.load\s*\([^)]*\)"), "yaml.load() without SafeLoader is unsafe on untrusted YAML.", "Use yaml.safe_load()."),
    ("FORGE-SEC-007", "HIGH", re.compile(r"(password|secret|api_key|token)\s*=\s*['\"][^'\"]{8,}['\"]", re.IGNORECASE), "Possible hardcoded credential or secret literal.", "Move secrets to environment variables."),
    ("FORGE-SEC-008", "HIGH", re.compile(r"(SELECT|INSERT|UPDATE|DELETE)\s+.+\s*(%s|\{.*\}|\+\s*\w+)", re.IGNORECASE), "Potential SQL string interpolation.", "Use parameterized SQL queries."),
]


def _iter_workspace_files(workspace_dir: str, max_files: int = 200) -> List[Path]:
    root = Path(workspace_dir)
    if not root.is_dir():
        return []
    collected: List[Path] = []
    for cur, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRECTORIES]
        for fname in sorted(files):
            fp = Path(cur) / fname
            if fp.suffix.lower() in IGNORED_EXTENSIONS:
                continue
            try:
                if fp.stat().st_size > 512 * 1024:
                    continue
            except OSError:
                continue
            collected.append(fp)
            if len(collected) >= max_files:
                return collected
    return collected


def _record_execution(
    session_id: str,
    agent_name: str,
    input_summary: Dict[str, Any],
    output_summary: Dict[str, Any],
    duration_ms: int,
    status: str = "COMPLETED",
    error: Optional[str] = None,
) -> None:
    try:
        from app.core.database import SessionLocal
        from app.models.session import AgentExecution, DebuggingSession

        db = SessionLocal()
        try:
            exe = AgentExecution(
                session_id=session_id,
                agent_name=agent_name,
                input_state_json=json.dumps(input_summary, default=str)[:4000],
                output_state_json=json.dumps(output_summary, default=str)[:8000],
                duration_ms=duration_ms,
                status=status,
                error=error,
            )
            db.add(exe)
            sess = db.query(DebuggingSession).filter(DebuggingSession.id == session_id).first()
            if sess:
                sess.current_agent_phase = agent_name if hasattr(sess, "current_agent_phase") else None
                sess.current_phase = agent_name
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        logger.debug(f"Could not record AgentExecution: {exc}")

    ws_manager.broadcast_sync(
        session_id,
        {
            "type": "agent_step",
            "session_id": session_id,
            "agent_name": agent_name,
            "status": status,
            "duration_ms": duration_ms,
            "summary": output_summary,
            "error": error,
        },
    )


def _extract_json_block(text: str) -> Optional[Dict[str, Any]]:
    """Extract first JSON object from an LLM response."""
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Agent 1: Planner Agent
# ---------------------------------------------------------------------------

def planner_node(state: ForgeAgentState) -> Dict[str, Any]:
    t0 = time.monotonic()
    session_id = state["session_id"]
    title = state.get("issue_title", "")
    description = state.get("issue_description", "")
    error_logs = state.get("error_logs", "")

    steps = [
        {"id": 1, "agent": "RepositoryAnalysisAgent", "goal": "Profile repository structure, symbols, and RAG/Graph context"},
        {"id": 2, "agent": "BugDetectionAgent", "goal": "Locate root cause and line-level bug evidence"},
        {"id": 3, "agent": "SecurityAuditAgent", "goal": "Scan repository for security vulnerabilities"},
        {"id": 4, "agent": "CodingAgent", "goal": "Synthesize minimal patch & unified diff"},
        {"id": 5, "agent": "TestingAgent", "goal": "Execute repository test suite in isolated workspace"},
        {"id": 6, "agent": "CodeReviewAgent", "goal": "Verify patch quality, test results, and approval readiness"},
    ]

    llm_notes = None
    llm_available = LLMService.is_configured()
    if llm_available:
        res = LLMService.invoke(
            system_prompt="You are FORGE Planner Agent. Produce a concise JSON plan with keys 'strategy' and 'focus_areas' (list of strings).",
            user_prompt=f"Issue: {title}\nDescription: {description}\nLogs:\n{error_logs[:1500]}",
            session_id=session_id,
            agent_name="PlannerAgent",
        )
        if res.available:
            parsed = _extract_json_block(res.content)
            llm_notes = parsed or {"raw_strategy": res.content[:800]}

    plan = {
        "issue_title": title,
        "steps": steps,
        "max_retries": state.get("max_retries", 3),
        "llm_enhanced": bool(llm_notes),
        "llm_plan": llm_notes,
    }
    duration_ms = int((time.monotonic() - t0) * 1000)
    _record_execution(session_id, "PlannerAgent", {"title": title}, plan, duration_ms)

    return {
        "current_agent": "PlannerAgent",
        "status": "PLANNING",
        "plan": plan,
        "llm_available": llm_available,
        "agent_events": list(state.get("agent_events", [])) + [{"agent": "PlannerAgent", "status": "COMPLETED", "duration_ms": duration_ms}],
    }


# ---------------------------------------------------------------------------
# Agent 2: Repository Analysis Agent
# ---------------------------------------------------------------------------

def repo_analyst_node(state: ForgeAgentState) -> Dict[str, Any]:
    t0 = time.monotonic()
    session_id = state["session_id"]
    repo_id = state["repository_id"]
    workspace_dir = state.get("workspace_dir", "")
    query = f"{state.get('issue_title', '')} {state.get('issue_description', '')}".strip()

    files = _iter_workspace_files(workspace_dir)
    rel_files = [str(f.relative_to(workspace_dir)) for f in files] if workspace_dir and Path(workspace_dir).is_dir() else []

    manifests = [f for f in rel_files if Path(f).name in ("requirements.txt", "pyproject.toml", "package.json", "setup.py", "Cargo.toml", "go.mod")]

    # Real Code RAG retrieval
    rag_hits: List[Dict[str, Any]] = []
    try:
        from app.core.database import SessionLocal
        from app.services.retrieval_service import search_hybrid

        db = SessionLocal()
        try:
            hits = search_hybrid(query or "main", repo_id, db, top_k=6)
            rag_hits = [
                {
                    "file_path": h.file_path,
                    "symbol_name": h.symbol_name,
                    "symbol_type": h.symbol_type,
                    "start_line": h.start_line,
                    "end_line": h.end_line,
                    "score": round(h.score, 4),
                    "snippet": h.chunk_content[:600],
                }
                for h in hits
            ]
        finally:
            db.close()
    except Exception as exc:
        logger.debug(f"RAG retrieval in RepoAnalyst skipped: {exc}")

    # GraphRAG context (Phase 5 integration — works once graph_service is available)
    graph_ctx: Dict[str, Any] = {}
    try:
        from app.services.graph_service import GraphService
        graph_ctx = GraphService.get_instance().query_context(repo_id, query, limit=8)
    except Exception:
        graph_ctx = {"available": False}

    summary = {
        "total_scanned_files": len(rel_files),
        "sample_files": rel_files[:25],
        "manifests": manifests,
        "rag_hits_count": len(rag_hits),
        "graph_nodes_count": len(graph_ctx.get("nodes", [])) if isinstance(graph_ctx, dict) else 0,
    }
    duration_ms = int((time.monotonic() - t0) * 1000)
    _record_execution(session_id, "RepositoryAnalysisAgent", {"repo_id": repo_id}, summary, duration_ms)

    return {
        "current_agent": "RepositoryAnalysisAgent",
        "status": "ANALYZING",
        "repo_summary": summary,
        "rag_context": rag_hits,
        "graph_context": graph_ctx,
        "agent_events": list(state.get("agent_events", [])) + [{"agent": "RepositoryAnalysisAgent", "status": "COMPLETED", "duration_ms": duration_ms}],
    }


# ---------------------------------------------------------------------------
# Agent 3: Bug Detection Agent
# ---------------------------------------------------------------------------

def _scan_python_ast_bugs(workspace_dir: str) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    root = Path(workspace_dir)
    if not root.is_dir():
        return findings

    for fp in _iter_workspace_files(workspace_dir):
        if fp.suffix.lower() != ".py":
            continue
        rel = str(fp.relative_to(root))
        try:
            text = fp.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        try:
            tree = ast.parse(text, filename=rel)
        except SyntaxError as syn:
            findings.append({
                "file_path": rel,
                "line_number": syn.lineno or 1,
                "severity": "CRITICAL",
                "confidence": 0.99,
                "category": "SyntaxError",
                "root_cause": f"Python SyntaxError: {syn.msg}",
                "evidence": syn.text.strip() if syn.text else "",
            })
            continue

        for node in ast.walk(tree):
            # Bare except
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                findings.append({
                    "file_path": rel,
                    "line_number": node.lineno,
                    "severity": "MEDIUM",
                    "confidence": 0.85,
                    "category": "BareExcept",
                    "root_cause": "Bare 'except:' catches SystemExit/KeyboardInterrupt and hides real errors.",
                    "evidence": "except:",
                })
            # Mutable default argument in function
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for default in node.args.defaults + node.args.kw_defaults:
                    if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                        findings.append({
                            "file_path": rel,
                            "line_number": node.lineno,
                            "severity": "MEDIUM",
                            "confidence": 0.9,
                            "category": "MutableDefaultArg",
                            "root_cause": f"Function '{node.name}' uses a mutable default argument.",
                            "evidence": f"def {node.name}(...)",
                        })
                        break
    return findings


def _extract_traceback_locations(error_logs: str, workspace_dir: str) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    if not error_logs:
        return findings
    # Match Python traceback: File "...", line N
    for m in re.finditer(r'File\s+"([^"]+)",\s+line\s+(\d+)', error_logs):
        fpath, lineno = m.group(1), int(m.group(2))
        rel = fpath
        if workspace_dir and fpath.startswith(workspace_dir):
            rel = str(Path(fpath).relative_to(workspace_dir))
        findings.append({
            "file_path": rel,
            "line_number": lineno,
            "severity": "HIGH",
            "confidence": 0.92,
            "category": "StackTraceReference",
            "root_cause": "Referenced directly in failure stack trace / error logs.",
            "evidence": m.group(0),
        })
    return findings


def bug_detector_node(state: ForgeAgentState) -> Dict[str, Any]:
    t0 = time.monotonic()
    session_id = state["session_id"]
    workspace_dir = state.get("workspace_dir", "")
    error_logs = state.get("error_logs", "")
    issue_desc = state.get("issue_description", "")

    bugs = _extract_traceback_locations(error_logs, workspace_dir)
    bugs.extend(_scan_python_ast_bugs(workspace_dir))

    # Optional LLM root-cause refinement
    if LLMService.is_configured():
        rag_text = "\n".join(
            f"[{h['file_path']}:L{h['start_line']}-{h['end_line']}]\n{h['snippet']}"
            for h in state.get("rag_context", [])[:4]
        )
        res = LLMService.invoke(
            system_prompt=(
                "You are FORGE Bug Detection Agent. Return JSON with key 'bugs': "
                "list of {file_path, line_number, severity, confidence, category, root_cause, evidence}."
            ),
            user_prompt=f"Issue: {issue_desc}\nLogs:\n{error_logs[:1500]}\n\nCode Context:\n{rag_text[:3000]}",
            session_id=session_id,
            agent_name="BugDetectionAgent",
        )
        if res.available:
            parsed = _extract_json_block(res.content)
            if parsed and isinstance(parsed.get("bugs"), list):
                for b in parsed["bugs"][:5]:
                    if isinstance(b, dict) and b.get("file_path"):
                        bugs.append({
                            "file_path": str(b.get("file_path")),
                            "line_number": int(b.get("line_number") or 1),
                            "severity": str(b.get("severity") or "MEDIUM"),
                            "confidence": float(b.get("confidence") or 0.75),
                            "category": str(b.get("category") or "LLMRootCause"),
                            "root_cause": str(b.get("root_cause") or ""),
                            "evidence": str(b.get("evidence") or ""),
                        })

    duration_ms = int((time.monotonic() - t0) * 1000)
    _record_execution(
        session_id,
        "BugDetectionAgent",
        {"error_logs_len": len(error_logs)},
        {"bugs_detected": len(bugs), "bugs": bugs[:10]},
        duration_ms,
    )

    return {
        "current_agent": "BugDetectionAgent",
        "status": "BUG_DETECTION",
        "bug_reports": bugs,
        "agent_events": list(state.get("agent_events", [])) + [{"agent": "BugDetectionAgent", "status": "COMPLETED", "duration_ms": duration_ms}],
    }


# ---------------------------------------------------------------------------
# Agent 4: Security Audit Agent
# ---------------------------------------------------------------------------

def security_auditor_node(state: ForgeAgentState) -> Dict[str, Any]:
    t0 = time.monotonic()
    session_id = state["session_id"]
    repo_id = state["repository_id"]
    workspace_dir = state.get("workspace_dir", "")

    findings: List[Dict[str, Any]] = []
    root = Path(workspace_dir)
    if root.is_dir():
        for fp in _iter_workspace_files(workspace_dir):
            if fp.suffix.lower() not in (".py", ".js", ".ts", ".jsx", ".tsx", ".yml", ".yaml", ".sh"):
                continue
            rel = str(fp.relative_to(root))
            try:
                lines = fp.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            for idx, line in enumerate(lines, start=1):
                for rule_id, severity, pattern, msg, rec in _SECURITY_RULES:
                    if pattern.search(line):
                        findings.append({
                            "rule_id": rule_id,
                            "severity": severity,
                            "file_path": rel,
                            "line_number": idx,
                            "message": msg,
                            "recommendation": rec,
                        })

    # Persist to SecurityFinding table
    try:
        from app.core.database import SessionLocal
        from app.models.session import SecurityFinding

        db = SessionLocal()
        try:
            db.query(SecurityFinding).filter(SecurityFinding.session_id == session_id).delete()
            for f in findings[:100]:
                db.add(
                    SecurityFinding(
                        repository_id=repo_id,
                        session_id=session_id,
                        rule_id=f["rule_id"],
                        severity=f["severity"],
                        file_path=f["file_path"],
                        line_number=f["line_number"],
                        message=f["message"],
                        recommendation=f["recommendation"],
                    )
                )
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        logger.debug(f"Could not persist SecurityFinding rows: {exc}")

    duration_ms = int((time.monotonic() - t0) * 1000)
    _record_execution(
        session_id,
        "SecurityAuditAgent",
        {"workspace_dir": workspace_dir},
        {"findings_count": len(findings), "findings": findings[:10]},
        duration_ms,
    )

    return {
        "current_agent": "SecurityAuditAgent",
        "status": "SECURITY_AUDIT",
        "security_findings": findings,
        "agent_events": list(state.get("agent_events", [])) + [{"agent": "SecurityAuditAgent", "status": "COMPLETED", "duration_ms": duration_ms}],
    }


# ---------------------------------------------------------------------------
# Agent 5: Coding Agent
# ---------------------------------------------------------------------------

def _build_unified_diff(file_path: str, old_text: str, new_text: str) -> str:
    return "".join(
        difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
        )
    )


def coding_node(state: ForgeAgentState) -> Dict[str, Any]:
    t0 = time.monotonic()
    session_id = state["session_id"]
    workspace_dir = state.get("workspace_dir", "")
    issue_desc = state.get("issue_description", "")
    bugs = state.get("bug_reports", [])
    retry_count = state.get("retry_count", 0)
    repair_history = state.get("repair_history", [])

    proposed_edits: List[Dict[str, str]] = []
    diff_content = ""
    rationale = ""
    affected_files: List[str] = []
    patch_id: Optional[str] = None

    if not LLMService.is_configured():
        rationale = (
            "OPENAI_API_KEY is not configured. Coding Agent cannot synthesize an LLM patch "
            "without a real LLM provider. Static bug & security findings are preserved."
        )
        duration_ms = int((time.monotonic() - t0) * 1000)
        _record_execution(
            session_id,
            "CodingAgent",
            {"bugs": len(bugs), "retry_count": retry_count},
            {"llm_available": False, "rationale": rationale},
            duration_ms,
            status="COMPLETED",
        )
        return {
            "current_agent": "CodingAgent",
            "status": "CODING",
            "proposed_edits": [],
            "diff_content": "",
            "affected_files": [],
            "patch_rationale": rationale,
            "llm_available": False,
            "agent_events": list(state.get("agent_events", [])) + [{"agent": "CodingAgent", "status": "COMPLETED", "duration_ms": duration_ms}],
        }

    # Build real file context from top RAG / bug files
    root = Path(workspace_dir)
    candidate_paths: List[str] = []
    for b in bugs:
        if b.get("file_path") and b["file_path"] not in candidate_paths:
            candidate_paths.append(b["file_path"])
    for h in state.get("rag_context", []):
        if h.get("file_path") and h["file_path"] not in candidate_paths:
            candidate_paths.append(h["file_path"])

    file_snippets = []
    for rel in candidate_paths[:3]:
        fp = (root / rel).resolve()
        try:
            fp.relative_to(root.resolve())
        except ValueError:
            continue
        if fp.is_file():
            content = fp.read_text(encoding="utf-8", errors="ignore")
            file_snippets.append(f"=== FILE: {rel} ===\n{content[:4000]}")

    repair_ctx = f"\nPrevious repair attempts:\n{json.dumps(repair_history[-2:], default=str)}" if repair_history else ""
    res = LLMService.invoke(
        system_prompt=(
            "You are FORGE Coding Agent. Return strict JSON: "
            '{"rationale": "...", "edits": [{"file_path": "...", "new_content": "..."}]}. '
            "Only edit files that need fixing."
        ),
        user_prompt=(
            f"Issue: {issue_desc}\n"
            f"Detected Bugs: {json.dumps(bugs[:5], default=str)}\n"
            f"{repair_ctx}\n\n"
            + "\n\n".join(file_snippets)
        ),
        session_id=session_id,
        agent_name="CodingAgent",
    )

    if res.available:
        parsed = _extract_json_block(res.content)
        if parsed and isinstance(parsed.get("edits"), list):
            rationale = str(parsed.get("rationale") or "Generated patch via LLM.")
            diffs: List[str] = []
            for edit in parsed["edits"]:
                rel = str(edit.get("file_path", "")).lstrip("/")
                new_content = edit.get("new_content")
                if not rel or new_content is None:
                    continue
                fp = (root / rel).resolve()
                try:
                    fp.relative_to(root.resolve())
                except ValueError:
                    continue
                old_content = fp.read_text(encoding="utf-8", errors="ignore") if fp.is_file() else ""
                if old_content == new_content:
                    continue
                diffs.append(_build_unified_diff(rel, old_content, new_content))
                proposed_edits.append({
                    "file_path": rel,
                    "original_content": old_content,
                    "new_content": new_content,
                })
                affected_files.append(rel)
            diff_content = "\n".join(diffs)
        else:
            rationale = f"LLM did not return structured edits: {res.content[:400]}"
    else:
        rationale = f"LLM call failed: {res.error}"

    if diff_content:
        try:
            from app.core.database import SessionLocal
            from app.models.session import Patch

            db = SessionLocal()
            try:
                patch = Patch(
                    session_id=session_id,
                    iteration=retry_count + 1,
                    diff_content=diff_content,
                    affected_files_json=json.dumps(affected_files),
                    rationale=rationale,
                    is_applied=False,
                )
                db.add(patch)
                db.commit()
                db.refresh(patch)
                patch_id = patch.id
            finally:
                db.close()
        except Exception as exc:
            logger.debug(f"Could not persist Patch: {exc}")

    duration_ms = int((time.monotonic() - t0) * 1000)
    _record_execution(
        session_id,
        "CodingAgent",
        {"candidate_files": candidate_paths[:3]},
        {"affected_files": affected_files, "has_diff": bool(diff_content), "patch_id": patch_id},
        duration_ms,
    )

    return {
        "current_agent": "CodingAgent",
        "status": "CODING",
        "proposed_edits": proposed_edits,
        "diff_content": diff_content,
        "affected_files": affected_files,
        "patch_rationale": rationale,
        "patch_id": patch_id,
        "llm_available": res.available,
        "agent_events": list(state.get("agent_events", [])) + [{"agent": "CodingAgent", "status": "COMPLETED", "duration_ms": duration_ms}],
    }


# ---------------------------------------------------------------------------
# Agent 6: Testing Agent
# ---------------------------------------------------------------------------

def _apply_edits_temporarily(workspace_dir: str, edits: List[Dict[str, str]]) -> List[Tuple[Path, Optional[str]]]:
    root = Path(workspace_dir).resolve()
    backups: List[Tuple[Path, Optional[str]]] = []
    for edit in edits:
        fp = (root / edit["file_path"]).resolve()
        try:
            fp.relative_to(root)
        except ValueError:
            continue
        old = fp.read_text(encoding="utf-8", errors="ignore") if fp.is_file() else None
        backups.append((fp, old))
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(edit["new_content"], encoding="utf-8")
    return backups


def _restore_backups(backups: List[Tuple[Path, Optional[str]]]) -> None:
    for fp, old in backups:
        if old is None:
            if fp.exists():
                fp.unlink()
        else:
            fp.write_text(old, encoding="utf-8")


def _parse_pytest_counts(output: str) -> Tuple[int, int]:
    passed = 0
    failed = 0
    m_pass = re.search(r"(\d+)\s+passed", output)
    m_fail = re.search(r"(\d+)\s+(?:failed|error)", output)
    if m_pass:
        passed = int(m_pass.group(1))
    if m_fail:
        failed = int(m_fail.group(1))
    return passed, failed


def testing_node(state: ForgeAgentState) -> Dict[str, Any]:
    t0 = time.monotonic()
    session_id = state["session_id"]
    workspace_dir = state.get("workspace_dir", "")
    edits = state.get("proposed_edits", [])
    patch_id = state.get("patch_id")

    backups: List[Tuple[Path, Optional[str]]] = []
    exit_code = 0
    stdout = ""
    stderr = ""
    passed_count = 0
    failed_count = 0
    tests_found = False

    root = Path(workspace_dir)
    if root.is_dir():
        has_python_tests = any(
            p.name.startswith("test_") or p.name.endswith("_test.py") or "tests" in p.parts
            for p in _iter_workspace_files(workspace_dir, max_files=300)
            if p.suffix == ".py"
        )
        if has_python_tests:
            tests_found = True
            try:
                if edits:
                    backups = _apply_edits_temporarily(workspace_dir, edits)
                test_env = os.environ.copy()
                ws_path = Path(workspace_dir).resolve()
                existing_pp = os.environ.get("PYTHONPATH", "")
                test_env["PYTHONPATH"] = f"{ws_path}{os.pathsep}{ws_path / 'src'}{os.pathsep}{existing_pp}".rstrip(os.pathsep)
                proc = subprocess.run(
                    [sys.executable, "-m", "pytest", "-q", "--tb=short"],
                    cwd=workspace_dir,
                    env=test_env,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    shell=False,
                )
                exit_code = proc.returncode
                stdout = proc.stdout[-6000:]
                stderr = proc.stderr[-3000:]
                passed_count, failed_count = _parse_pytest_counts(stdout + "\n" + stderr)
            except subprocess.TimeoutExpired:
                exit_code = 124
                stderr = "Test execution timed out after 60s."
                failed_count = 1
            except Exception as exc:
                exit_code = 1
                stderr = f"Test runner error: {exc}"
                failed_count = 1
            finally:
                # Keep workspace clean until user approves in Phase 7 (unless explicitly applied)
                if backups:
                    _restore_backups(backups)
        else:
            stdout = "No Python pytest suite discovered in workspace."
    else:
        exit_code = 1
        stderr = "Workspace directory does not exist."

    duration_ms = int((time.monotonic() - t0) * 1000)

    try:
        from app.core.database import SessionLocal
        from app.models.session import TestExecution

        db = SessionLocal()
        try:
            db.add(
                TestExecution(
                    session_id=session_id,
                    patch_id=patch_id,
                    exit_code=exit_code,
                    stdout=stdout,
                    stderr=stderr,
                    passed_count=passed_count,
                    failed_count=failed_count,
                    duration_ms=duration_ms,
                )
            )
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        logger.debug(f"Could not persist TestExecution: {exc}")

    test_result = {
        "tests_found": tests_found,
        "exit_code": exit_code,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "stdout": stdout,
        "stderr": stderr,
        "duration_ms": duration_ms,
        "passed": tests_found and exit_code == 0 and failed_count == 0,
    }
    _record_execution(session_id, "TestingAgent", {"edits": len(edits)}, test_result, duration_ms)

    return {
        "current_agent": "TestingAgent",
        "status": "TESTING",
        "test_result": test_result,
        "agent_events": list(state.get("agent_events", [])) + [{"agent": "TestingAgent", "status": "COMPLETED", "duration_ms": duration_ms}],
    }


# ---------------------------------------------------------------------------
# Agent 8: Self-Repair Agent
# ---------------------------------------------------------------------------

def self_repair_node(state: ForgeAgentState) -> Dict[str, Any]:
    t0 = time.monotonic()
    session_id = state["session_id"]
    retry_count = state.get("retry_count", 0) + 1
    test_result = state.get("test_result", {})

    failure_summary = (test_result.get("stderr") or test_result.get("stdout") or "Test failure")[-1500:]
    history = list(state.get("repair_history", []))
    history.append({
        "iteration": retry_count,
        "exit_code": test_result.get("exit_code"),
        "failure_excerpt": failure_summary,
    })

    duration_ms = int((time.monotonic() - t0) * 1000)
    _record_execution(
        session_id,
        "SelfRepairAgent",
        {"retry_count": retry_count},
        {"next_iteration": retry_count + 1, "failure_excerpt": failure_summary[:300]},
        duration_ms,
    )

    return {
        "current_agent": "SelfRepairAgent",
        "status": "REPAIRING",
        "retry_count": retry_count,
        "repair_history": history,
        "agent_events": list(state.get("agent_events", [])) + [{"agent": "SelfRepairAgent", "status": "COMPLETED", "duration_ms": duration_ms}],
    }


# ---------------------------------------------------------------------------
# Agent 7: Code Review Agent
# ---------------------------------------------------------------------------

def code_review_node(state: ForgeAgentState) -> Dict[str, Any]:
    t0 = time.monotonic()
    session_id = state["session_id"]
    diff_content = state.get("diff_content", "")
    test_result = state.get("test_result", {})
    security_findings = state.get("security_findings", [])

    comments: List[str] = []
    critical_sec = [f for f in security_findings if f.get("severity") == "CRITICAL"]

    if not diff_content:
        verdict = "BLOCKED"
        comments.append(state.get("patch_rationale") or "No patch diff was generated.")
    elif not test_result.get("passed", False):
        verdict = "CHANGES_REQUESTED"
        comments.append(
            f"Tests did not pass (exit_code={test_result.get('exit_code')}, failed={test_result.get('failed_count')})."
        )
    elif critical_sec:
        verdict = "CHANGES_REQUESTED"
        comments.append(f"{len(critical_sec)} CRITICAL security findings detected; review required.")
    else:
        verdict = "APPROVED"
        comments.append("Patch diff generated and all discovered tests passed.")

    duration_ms = int((time.monotonic() - t0) * 1000)
    _record_execution(
        session_id,
        "CodeReviewAgent",
        {"has_diff": bool(diff_content), "tests_passed": test_result.get("passed")},
        {"verdict": verdict, "comments": comments},
        duration_ms,
    )

    return {
        "current_agent": "CodeReviewAgent",
        "status": "COMPLETED",
        "review_verdict": verdict,
        "review_comments": comments,
        "agent_events": list(state.get("agent_events", [])) + [{"agent": "CodeReviewAgent", "status": "COMPLETED", "duration_ms": duration_ms}],
    }
