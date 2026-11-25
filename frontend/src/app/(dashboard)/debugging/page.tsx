"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import {
  Bug,
  Terminal,
  Play,
  CheckCircle2,
  XCircle,
  History,
  AlertTriangle,
  ShieldCheck,
  RefreshCw,
  GitBranch,
  FileCode,
  Check,
  ArrowRight,
  Code2,
  Cpu,
  FolderGit2,
  ExternalLink,
  Sparkles,
} from "lucide-react";
import { fetchWithAuth } from "@/lib/utils";

interface Repository {
  id: string;
  full_name: string;
  status: string;
}

interface DebuggingSessionSummary {
  id: string;
  repo_id: string;
  status: string;
  title: string;
  current_phase: string;
  retry_count: number;
  created_at: string;
  updated_at: string;
}

interface AgentExecutionItem {
  agent: string;
  status: string;
  duration_ms: number;
  created_at: string;
  output_summary: string;
  error?: string;
}

interface PatchItem {
  id: string;
  iteration: number;
  diff: string;
  rationale: string;
  is_applied: boolean;
  created_at: string;
}

interface SecurityFindingItem {
  rule_id: string;
  severity: string;
  file_path: string;
  line_number: number;
  message: string;
  recommendation: string;
}

interface TestResultItem {
  id: string;
  passed: number;
  failed: number;
  exit_code: number;
  stdout: string;
  stderr: string;
  duration_ms: number;
  created_at: string;
}

interface SessionDetail {
  id: string;
  repo_id: string;
  status: string;
  title: string;
  description: string;
  current_phase: string;
  retry_count: number;
  created_at: string;
  updated_at: string;
  agent_executions: AgentExecutionItem[];
  patches: PatchItem[];
  security_findings: SecurityFindingItem[];
  test_results: TestResultItem[];
}

export default function DebuggingPage() {
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [selectedRepoId, setSelectedRepoId] = useState<string>("");
  const [issueTitle, setIssueTitle] = useState("Audit codebase for runtime anomalies & test failures");
  const [issueDesc, setIssueDesc] = useState("Execute AST security audit, locate root cause of errors, and synthesize verified patch.");
  const [errorLogs, setErrorLogs] = useState("");
  const [maxRetries, setMaxRetries] = useState(3);
  const [isLaunching, setIsLaunching] = useState(false);
  const [launchMessage, setLaunchMessage] = useState<{ text: string; error: boolean } | null>(null);

  const [sessions, setSessions] = useState<DebuggingSessionSummary[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [sessionDetail, setSessionDetail] = useState<SessionDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [approvalStatus, setApprovalStatus] = useState<string | null>(null);
  const [isApproving, setIsApproving] = useState(false);

  // Load repositories safely (no trailing slash, handles items wrapper)
  useEffect(() => {
    async function loadRepos() {
      try {
        const res = await fetchWithAuth("/repositories");
        if (res.ok) {
          const data = await res.json();
          const list: Repository[] = Array.isArray(data)
            ? data
            : (data.items || data.repositories || []);
          setRepositories(list);
          if (list.length > 0) {
            setSelectedRepoId((prev) => prev || list[0].id);
          }
        }
      } catch (err) {
        console.error("Failed to load repositories", err);
      }
    }
    loadRepos();
  }, []);

  // Load sessions safely
  const loadSessions = useCallback(async () => {
    try {
      const res = await fetchWithAuth("/debugging/sessions");
      if (res.ok) {
        const data = await res.json();
        const list: DebuggingSessionSummary[] = Array.isArray(data)
          ? data
          : (data.items || []);
        setSessions(list);
        if (list.length > 0 && !selectedSessionId) {
          setSelectedSessionId(list[0].id);
        }
      }
    } catch (err) {
      console.error("Failed to load debugging sessions", err);
    }
  }, [selectedSessionId]);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  // Load single session detail
  const loadSessionDetail = useCallback(async (id: string) => {
    setLoadingDetail(true);
    try {
      const res = await fetchWithAuth(`/debugging/sessions/${id}`);
      if (res.ok) {
        const data = await res.json();
        setSessionDetail({
          ...data,
          agent_executions: data.agent_executions || [],
          patches: data.patches || [],
          security_findings: data.security_findings || [],
          test_results: data.test_results || [],
        });
      }
    } catch (err) {
      console.error("Failed to load session detail", err);
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  useEffect(() => {
    if (selectedSessionId) {
      loadSessionDetail(selectedSessionId);
    }
  }, [selectedSessionId, loadSessionDetail]);

  // Auto-refresh running sessions every 3 seconds
  useEffect(() => {
    if (!sessionDetail) return;
    const isFinished = sessionDetail.status === "COMPLETED" || sessionDetail.status === "FAILED";
    if (isFinished) return;

    const timer = setInterval(() => {
      if (selectedSessionId) {
        loadSessionDetail(selectedSessionId);
      }
      loadSessions();
    }, 3000);
    return () => clearInterval(timer);
  }, [sessionDetail, selectedSessionId, loadSessionDetail, loadSessions]);

  // Quick fill with sample bug trace
  function handleFillSample() {
    setIssueTitle("Fix AssertionError in matrix serialization test");
    setIssueDesc("Function bad_fn accepts mutable default argument and fails exception handling contract during matrix transform.");
    setErrorLogs('File "test_matrix.py", line 42, in test_transform\n  assert bad_fn() == 2\nAssertionError: assert 0 == 2\nTraceback (most recent call last):\n  File "matrix.py", line 12, in bad_fn\n    return eval("1 + 1")');
  }

  // Launch new debugging session
  async function handleLaunch() {
    if (!selectedRepoId) {
      setLaunchMessage({ text: "Please select a target repository first.", error: true });
      return;
    }
    setIsLaunching(true);
    setLaunchMessage(null);
    setApprovalStatus(null);
    try {
      const res = await fetchWithAuth("/debugging/sessions", {
        method: "POST",
        body: JSON.stringify({
          repo_id: selectedRepoId,
          title: issueTitle || "Autonomous Debugging Session",
          description: issueDesc || "Scan for bugs and execute verified repair",
          error_logs: errorLogs,
          max_retries: maxRetries,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setLaunchMessage({ text: `Debugging session #${data.session_id.slice(0, 8)} launched successfully!`, error: false });
        await loadSessions();
        setSelectedSessionId(data.session_id);
      } else {
        const errData = await res.json();
        setLaunchMessage({ text: `Failed to launch: ${errData.detail || "Server error"}`, error: true });
      }
    } catch (err) {
      setLaunchMessage({ text: `Network error: ${String(err)}`, error: true });
    } finally {
      setIsLaunching(false);
    }
  }

  // Approve & apply patch
  async function handleApprove(patchId: string) {
    if (!selectedSessionId) return;
    setIsApproving(true);
    setApprovalStatus(null);
    try {
      const res = await fetchWithAuth(`/automation/sessions/${selectedSessionId}/approve`, {
        method: "POST",
        body: JSON.stringify({
          patch_id: patchId,
          commit_message: `forge: apply verified fix for ${sessionDetail?.title || "issue"}`,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setApprovalStatus(`Branch "${data.branch}" created and patch committed successfully!`);
        await loadSessionDetail(selectedSessionId);
      } else {
        const errData = await res.json();
        setApprovalStatus(`Approval error: ${errData.detail || "Failed to apply"}`);
      }
    } catch (err) {
      setApprovalStatus(`Approval error: ${String(err)}`);
    } finally {
      setIsApproving(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">AI Debugging & Self-Repair Workspace</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Autonomous AST root-cause localization, minimal patch synthesis, isolated pytest verification, and bounded self-repair
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleFillSample}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#111827] border border-border text-xs font-mono text-cyan-300 hover:text-white hover:border-cyan-500/50 transition"
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>Load Sample Bug</span>
          </button>
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-violet-950/40 border border-violet-800/40 text-violet-300 text-xs font-mono">
            <Terminal className="w-3.5 h-3.5 text-violet-400" />
            <span>PHASE 6 ENGINE</span>
          </div>
        </div>
      </div>

      {/* Warning if no repositories */}
      {repositories.length === 0 && (
        <div className="p-4 rounded-2xl bg-amber-950/30 border border-amber-800/50 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />
            <div className="text-xs text-amber-200">
              <span className="font-bold">No connected repositories found.</span> You need to register or upload a repository first before initiating an automated debugging session.
            </div>
          </div>
          <Link
            href="/repositories"
            className="px-3.5 py-1.5 rounded-xl bg-amber-600 hover:bg-amber-500 text-white text-xs font-medium shrink-0 transition"
          >
            Go to Repository Explorer
          </Link>
        </div>
      )}

      {/* Main Grid: Launch Form (Left) & Sessions List (Right) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Launch Column */}
        <div className="lg:col-span-2 p-6 rounded-2xl bg-[#111827] border border-border/80 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <Bug className="w-4 h-4 text-rose-400" />
              <span>Launch Debugging Session</span>
            </h3>
            <span className="text-xs text-muted-foreground font-mono">LangGraph State Machine</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-medium text-muted-foreground block mb-1">Target Repository</label>
              <select
                value={selectedRepoId}
                onChange={(e) => setSelectedRepoId(e.target.value)}
                className="w-full bg-[#0A0E17] border border-border rounded-xl p-2.5 text-sm text-foreground focus:outline-none focus:border-violet-500"
              >
                {repositories.length === 0 ? (
                  <option value="">No repositories available</option>
                ) : (
                  repositories.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.full_name} ({r.status})
                    </option>
                  ))
                )}
              </select>
            </div>

            <div>
              <label className="text-xs font-medium text-muted-foreground block mb-1">Max Self-Repair Retries</label>
              <select
                value={maxRetries}
                onChange={(e) => setMaxRetries(Number(e.target.value))}
                className="w-full bg-[#0A0E17] border border-border rounded-xl p-2.5 text-sm text-foreground focus:outline-none focus:border-violet-500"
              >
                <option value={1}>1 Attempt (Fast Scan)</option>
                <option value={2}>2 Attempts</option>
                <option value={3}>3 Attempts (Standard Recommended)</option>
                <option value={5}>5 Attempts (Exhaustive Loop)</option>
              </select>
            </div>
          </div>

          <div>
            <label className="text-xs font-medium text-muted-foreground block mb-1">Task / Issue Title</label>
            <input
              type="text"
              value={issueTitle}
              onChange={(e) => setIssueTitle(e.target.value)}
              placeholder="e.g. Audit calc.py for AST bugs and eval() vulnerabilities"
              className="w-full bg-[#0A0E17] border border-border rounded-xl p-2.5 text-sm text-foreground focus:outline-none focus:border-violet-500 font-sans"
            />
          </div>

          <div>
            <label className="text-xs font-medium text-muted-foreground block mb-1">Problem Description</label>
            <textarea
              rows={2}
              value={issueDesc}
              onChange={(e) => setIssueDesc(e.target.value)}
              placeholder="Describe reproduction steps, expected vs actual behavior, or target constraints..."
              className="w-full bg-[#0A0E17] border border-border rounded-xl p-2.5 text-sm text-foreground focus:outline-none focus:border-violet-500 font-sans"
            />
          </div>

          <div>
            <label className="text-xs font-medium text-muted-foreground block mb-1">Error Logs / Stack Trace (Optional)</label>
            <textarea
              rows={3}
              value={errorLogs}
              onChange={(e) => setErrorLogs(e.target.value)}
              placeholder="Paste pytest tracebacks, exception lines, or terminal outputs..."
              className="w-full bg-[#0A0E17] border border-border rounded-xl p-2.5 text-xs text-foreground focus:outline-none focus:border-violet-500 font-mono"
            />
          </div>

          {launchMessage && (
            <div
              className={`p-3 rounded-xl border text-xs font-mono flex items-center gap-2 ${
                launchMessage.error
                  ? "bg-rose-950/40 border-rose-800 text-rose-300"
                  : "bg-emerald-950/40 border-emerald-800 text-emerald-300"
              }`}
            >
              {launchMessage.error ? <XCircle className="w-4 h-4 shrink-0" /> : <Check className="w-4 h-4 shrink-0" />}
              <span>{launchMessage.text}</span>
            </div>
          )}

          <button
            onClick={handleLaunch}
            disabled={isLaunching || !selectedRepoId}
            className="w-full py-3 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white font-medium rounded-xl text-sm flex items-center justify-center gap-2 transition shadow-lg shadow-violet-900/20"
          >
            {isLaunching ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
            <span>Initiate Autonomous Debugging & Self-Repair Workflow</span>
          </button>
        </div>

        {/* Sessions Column */}
        <div className="p-6 rounded-2xl bg-[#111827] border border-border/80 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <History className="w-4 h-4 text-violet-400" />
                <span>Debugging Sessions</span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-[#0A0E17] border border-border text-muted-foreground font-mono">
                  {sessions.length}
                </span>
              </h3>
              <button
                onClick={loadSessions}
                className="p-1.5 text-muted-foreground hover:text-white rounded-lg bg-[#0A0E17] border border-border transition"
                title="Refresh sessions"
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            </div>

            <div className="space-y-2 max-h-[380px] overflow-y-auto pr-1">
              {sessions.length === 0 ? (
                <div className="text-xs text-muted-foreground py-12 text-center font-mono">
                  <Terminal className="w-6 h-6 mx-auto text-muted-foreground/40 mb-2" />
                  No debugging sessions yet.
                  <p className="text-[11px] text-muted-foreground/60 mt-1">
                    Select a repository and click &quot;Initiate&quot; to start.
                  </p>
                </div>
              ) : (
                sessions.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => setSelectedSessionId(s.id)}
                    className={`w-full text-left p-3 rounded-xl border text-xs transition ${
                      selectedSessionId === s.id
                        ? "bg-violet-950/40 border-violet-500 text-white shadow-sm"
                        : "bg-[#0A0E17] border-border hover:border-border/80 text-muted-foreground"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-white truncate max-w-[170px]">{s.title}</span>
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] uppercase font-mono ${
                          s.status === "COMPLETED"
                            ? "bg-emerald-950/60 text-emerald-300 border border-emerald-800/40"
                            : s.status === "FAILED"
                            ? "bg-rose-950/60 text-rose-300 border border-rose-800/40"
                            : "bg-amber-950/60 text-amber-300 border border-amber-800/40"
                        }`}
                      >
                        {s.status}
                      </span>
                    </div>
                    <div className="flex items-center justify-between mt-1 text-[11px] text-muted-foreground font-mono">
                      <span>Phase: {s.current_phase || "Initializing"}</span>
                      <span>Retries: {s.retry_count}</span>
                    </div>
                  </button>
                ))
              )}
            </div>
          </div>

          <div className="pt-4 border-t border-border text-[11px] font-mono text-muted-foreground">
            Zero Fake Success Policy &bull; Pytest verification strictly enforced.
          </div>
        </div>
      </div>

      {/* Selected Session Detail Workspace */}
      {sessionDetail && (
        <div className="space-y-6 pt-2">
          {/* Header Banner */}
          <div className="p-6 rounded-2xl bg-[#111827] border border-border/80 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold text-white">{sessionDetail.title}</h2>
                <span
                  className={`px-2 py-0.5 rounded text-xs font-mono uppercase ${
                    sessionDetail.status === "COMPLETED"
                      ? "bg-emerald-950/60 text-emerald-300 border border-emerald-800"
                      : sessionDetail.status === "FAILED"
                      ? "bg-rose-950/60 text-rose-300 border border-rose-800"
                      : "bg-amber-950/60 text-amber-300 border border-amber-800"
                  }`}
                >
                  {sessionDetail.status}
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                Current Phase: <span className="font-mono text-cyan-300">{sessionDetail.current_phase}</span> &bull; Self-Repair Retries:{" "}
                <span className="font-mono text-violet-300">{sessionDetail.retry_count}</span> &bull; Session ID:{" "}
                <span className="font-mono text-muted-foreground">{sessionDetail.id.slice(0, 8)}</span>
              </p>
            </div>

            <div className="flex items-center gap-3">
              {approvalStatus && (
                <div className="p-2.5 rounded-xl bg-emerald-950/40 border border-emerald-800/40 text-emerald-300 text-xs font-mono flex items-center gap-2">
                  <Check className="w-3.5 h-3.5 shrink-0" />
                  <span>{approvalStatus}</span>
                  <Link
                    href="/pull-requests"
                    className="ml-2 text-cyan-300 underline font-semibold flex items-center gap-1"
                  >
                    <span>View in PR Center</span>
                    <ArrowRight className="w-3 h-3" />
                  </Link>
                </div>
              )}
              <button
                onClick={() => selectedSessionId && loadSessionDetail(selectedSessionId)}
                className="p-2 rounded-xl bg-[#0A0E17] border border-border text-muted-foreground hover:text-white transition"
                title="Refresh detail"
              >
                <RefreshCw className={`w-4 h-4 ${loadingDetail ? "animate-spin" : ""}`} />
              </button>
            </div>
          </div>

          {/* Multi-Agent Executions Timeline */}
          <div className="p-6 rounded-2xl bg-[#111827] border border-border/80">
            <h3 className="text-sm font-bold text-white flex items-center gap-2 mb-4">
              <Cpu className="w-4 h-4 text-cyan-400" />
              <span>Multi-Agent Collective Step Trace</span>
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
              {[
                "PlannerAgent",
                "RepositoryAnalysisAgent",
                "BugDetectionAgent",
                "SecurityAuditAgent",
                "CodingAgent",
                "TestingAgent",
                "SelfRepairAgent",
                "CodeReviewAgent",
              ].map((name) => {
                const execs = sessionDetail.agent_executions || [];
                const exec = execs.find((e) => e.agent === name);
                const isCompleted = exec?.status === "COMPLETED";
                const isFailed = exec?.status === "FAILED";
                return (
                  <div
                    key={name}
                    className={`p-3 rounded-xl border text-center transition ${
                      isCompleted
                        ? "bg-emerald-950/30 border-emerald-800 text-emerald-300"
                        : isFailed
                        ? "bg-rose-950/30 border-rose-800 text-rose-300"
                        : "bg-[#0A0E17] border-border/60 text-muted-foreground/60"
                    }`}
                  >
                    <div className="text-[11px] font-mono truncate">{name.replace("Agent", "")}</div>
                    <div className="text-[10px] font-mono mt-1">
                      {isCompleted ? `${exec?.duration_ms || 0}ms` : isFailed ? "Failed" : "Pending"}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Patches & Code Diffs */}
          <div className="p-6 rounded-2xl bg-[#111827] border border-border/80 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <FileCode className="w-4 h-4 text-violet-400" />
                <span>Synthesized Patches & Unified Diffs ({(sessionDetail.patches || []).length})</span>
              </h3>
            </div>

            {(sessionDetail.patches || []).length === 0 ? (
              <div className="p-6 rounded-xl bg-[#0A0E17] border border-border text-xs text-muted-foreground text-center font-mono">
                No patches generated yet. If tests pass without defects, patch generation is skipped.
              </div>
            ) : (
              sessionDetail.patches.map((p) => (
                <div key={p.id} className="p-4 rounded-xl bg-[#0A0E17] border border-border space-y-3">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-mono font-bold text-cyan-300">Iteration {p.iteration}</span>
                      <span className="text-xs text-muted-foreground">&bull; {p.rationale || "Automated fix patch"}</span>
                    </div>

                    <div className="flex items-center gap-2">
                      {p.is_applied ? (
                        <span className="px-2.5 py-1 rounded-full bg-emerald-950/60 border border-emerald-800 text-emerald-300 text-xs font-mono flex items-center gap-1.5">
                          <Check className="w-3.5 h-3.5" />
                          <span>Applied to Branch</span>
                        </span>
                      ) : (
                        <button
                          onClick={() => handleApprove(p.id)}
                          disabled={isApproving}
                          className="px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-medium flex items-center gap-1.5 transition"
                        >
                          <GitBranch className="w-3.5 h-3.5" />
                          <span>Approve & Apply Patch</span>
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Unified Diff View */}
                  <pre className="p-3.5 rounded-lg bg-[#050811] border border-border/60 text-xs font-mono overflow-x-auto text-gray-300 max-h-[320px]">
                    {p.diff
                      ? p.diff.split("\n").map((line, i) => {
                          const isAdd = line.startsWith("+") && !line.startsWith("+++");
                          const isRem = line.startsWith("-") && !line.startsWith("---");
                          const isHdr = line.startsWith("@@") || line.startsWith("---") || line.startsWith("+++");
                          return (
                            <div
                              key={i}
                              className={
                                isAdd
                                  ? "text-emerald-400 bg-emerald-950/20"
                                  : isRem
                                  ? "text-rose-400 bg-rose-950/20"
                                  : isHdr
                                  ? "text-cyan-400 font-bold"
                                  : "text-gray-300"
                              }
                            >
                              {line}
                            </div>
                          );
                        })
                      : "/* No diff content */"}
                  </pre>
                </div>
              ))
            )}
          </div>

          {/* Test Execution Sandbox Results */}
          <div className="p-6 rounded-2xl bg-[#111827] border border-border/80 space-y-4">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Terminal className="w-4 h-4 text-emerald-400" />
              <span>Sandbox Test Suite Executions ({(sessionDetail.test_results || []).length})</span>
            </h3>

            {(sessionDetail.test_results || []).length === 0 ? (
              <div className="p-6 rounded-xl bg-[#0A0E17] border border-border text-xs text-muted-foreground text-center font-mono">
                No test results recorded yet.
              </div>
            ) : (
              sessionDetail.test_results.map((t, idx) => (
                <div key={t.id || idx} className="p-4 rounded-xl bg-[#0A0E17] border border-border space-y-2">
                  <div className="flex items-center justify-between text-xs font-mono">
                    <div className="flex items-center gap-3">
                      <span className="text-emerald-400 font-bold">{t.passed} Passed</span>
                      <span className="text-rose-400 font-bold">{t.failed} Failed</span>
                      <span className="text-muted-foreground">Exit Code: {t.exit_code}</span>
                    </div>
                    <span className="text-muted-foreground">{t.duration_ms}ms</span>
                  </div>

                  {t.stdout && (
                    <pre className="p-3 rounded-lg bg-[#050811] text-[11px] font-mono text-gray-300 overflow-x-auto max-h-[160px]">
                      {t.stdout}
                    </pre>
                  )}
                  {t.stderr && (
                    <pre className="p-3 rounded-lg bg-rose-950/20 border border-rose-900/30 text-[11px] font-mono text-rose-300 overflow-x-auto max-h-[120px]">
                      {t.stderr}
                    </pre>
                  )}
                </div>
              ))
            )}
          </div>

          {/* Security Findings Audit */}
          <div className="p-6 rounded-2xl bg-[#111827] border border-border/80 space-y-4">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-amber-400" />
              <span>Security Audit Findings ({(sessionDetail.security_findings || []).length})</span>
            </h3>

            {(sessionDetail.security_findings || []).length === 0 ? (
              <div className="p-6 rounded-xl bg-[#0A0E17] border border-border text-xs text-emerald-400 text-center font-mono">
                No security vulnerabilities discovered in this session.
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {sessionDetail.security_findings.map((f, idx) => (
                  <div key={idx} className="p-3.5 rounded-xl bg-[#0A0E17] border border-border space-y-1.5 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-rose-400 font-bold">{f.rule_id}</span>
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-mono uppercase bg-rose-950/60 text-rose-300">
                        {f.severity}
                      </span>
                    </div>
                    <div className="text-white font-medium">{f.message}</div>
                    <div className="text-muted-foreground font-mono text-[11px]">
                      {f.file_path}:{f.line_number}
                    </div>
                    {f.recommendation && (
                      <div className="text-[11px] text-cyan-300/80 pt-1 border-t border-border/40">
                        Fix: {f.recommendation}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
