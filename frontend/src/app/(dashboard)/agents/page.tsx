"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactFlow, {
  Background,
  Controls,
  Edge,
  MarkerType,
  Node,
} from "reactflow";
import "reactflow/dist/style.css";
import {
  Activity,
  AlertCircle,
  Bot,
  CheckCircle2,
  Clock,
  Loader2,
  Play,
  RefreshCw,
  Terminal,
  Zap,
} from "lucide-react";
import { API_BASE_URL, fetchWithAuth } from "@/lib/utils";

interface RepoItem {
  id: string;
  full_name: string;
  status: string;
}

interface AgentExecutionItem {
  id: string;
  agent_name: string;
  status: string;
  duration_ms: number;
  output: Record<string, unknown>;
  error: string | null;
  created_at: string;
}

interface SessionSummary {
  id: string;
  repository_id: string;
  title: string;
  status: string;
  current_phase: string;
  retry_count: number;
  created_at: string;
}

interface SessionDetail extends SessionSummary {
  description: string;
  llm_configured: boolean;
  executions: AgentExecutionItem[];
}

const DAG_LAYOUT: Array<{ id: string; label: string; x: number; y: number }> = [
  { id: "PlannerAgent", label: "1. Planner", x: 20, y: 80 },
  { id: "RepositoryAnalysisAgent", label: "2. Repo Analyst", x: 210, y: 80 },
  { id: "BugDetectionAgent", label: "3. Bug Detector", x: 400, y: 80 },
  { id: "SecurityAuditAgent", label: "4. Security Audit", x: 590, y: 80 },
  { id: "CodingAgent", label: "5. Coding Agent", x: 780, y: 80 },
  { id: "TestingAgent", label: "6. Testing Agent", x: 970, y: 80 },
  { id: "SelfRepairAgent", label: "8. Self-Repair", x: 875, y: 210 },
  { id: "CodeReviewAgent", label: "7. Code Review", x: 1160, y: 80 },
];

const DAG_EDGES: Edge[] = [
  { id: "e1", source: "PlannerAgent", target: "RepositoryAnalysisAgent", animated: true, markerEnd: { type: MarkerType.ArrowClosed } },
  { id: "e2", source: "RepositoryAnalysisAgent", target: "BugDetectionAgent", animated: true, markerEnd: { type: MarkerType.ArrowClosed } },
  { id: "e3", source: "BugDetectionAgent", target: "SecurityAuditAgent", animated: true, markerEnd: { type: MarkerType.ArrowClosed } },
  { id: "e4", source: "SecurityAuditAgent", target: "CodingAgent", animated: true, markerEnd: { type: MarkerType.ArrowClosed } },
  { id: "e5", source: "CodingAgent", target: "TestingAgent", animated: true, markerEnd: { type: MarkerType.ArrowClosed } },
  { id: "e6", source: "TestingAgent", target: "CodeReviewAgent", label: "pass", markerEnd: { type: MarkerType.ArrowClosed } },
  { id: "e7", source: "TestingAgent", target: "SelfRepairAgent", label: "fail", style: { stroke: "#f43f5e" }, markerEnd: { type: MarkerType.ArrowClosed } },
  { id: "e8", source: "SelfRepairAgent", target: "CodingAgent", label: "retry", style: { stroke: "#f59e0b" }, markerEnd: { type: MarkerType.ArrowClosed } },
];

export default function AgentsPage() {
  const [repos, setRepos] = useState<RepoItem[]>([]);
  const [selectedRepo, setSelectedRepo] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [errorLogs, setErrorLogs] = useState("");
  const [llmConfigured, setLlmConfigured] = useState<boolean | null>(null);
  const [llmModel, setLlmModel] = useState<string>("gpt-4o-mini");

  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeSession, setActiveSession] = useState<SessionDetail | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [errMsg, setErrMsg] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadInitial = useCallback(() => {
    fetchWithAuth(`${API_BASE_URL}/agents/specs`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d) {
          setLlmConfigured(Boolean(d.llm_configured));
          setLlmModel(d.llm_model || "gpt-4o-mini");
        }
      })
      .catch(() => {});

    fetchWithAuth(`${API_BASE_URL}/repositories`)
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => {
        const list = Array.isArray(data) ? data : (data.items || data.repositories || []);
        setRepos(list);
        if (list.length > 0 && !selectedRepo) setSelectedRepo(list[0].id);
      })
      .catch(() => {});

    fetchWithAuth(`${API_BASE_URL}/agents/sessions`)
      .then((r) => (r.ok ? r.json() : []))
      .then((list: SessionSummary[]) => {
        if (Array.isArray(list)) {
          setSessions(list);
          if (list.length > 0 && !activeSession) {
            fetchSessionDetail(list[0].id);
          }
        }
      })
      .catch(() => {});
  }, []);

  const fetchSessionDetail = useCallback((sessionId: string) => {
    fetchWithAuth(`${API_BASE_URL}/agents/sessions/${sessionId}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((detail: SessionDetail | null) => {
        if (!detail) return;
        setActiveSession(detail);
        if (detail.status !== "COMPLETED" && detail.status !== "FAILED") {
          pollRef.current = setTimeout(() => fetchSessionDetail(sessionId), 1500);
        }
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    loadInitial();
    return () => {
      if (pollRef.current) clearTimeout(pollRef.current);
    };
  }, [loadInitial]);

  const handleLaunch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedRepo || !title.trim() || !description.trim()) return;
    setSubmitting(true);
    setErrMsg(null);
    if (pollRef.current) clearTimeout(pollRef.current);

    try {
      const r = await fetchWithAuth(`${API_BASE_URL}/agents/sessions`, {
        method: "POST",
        body: JSON.stringify({
          repository_id: selectedRepo,
          title: title.trim(),
          description: description.trim(),
          error_logs: errorLogs.trim(),
          max_retries: 3,
        }),
      });
      const data = await r.json();
      if (!r.ok) {
        setErrMsg(data.detail || "Failed to launch agent session.");
      } else {
        setTitle("");
        setDescription("");
        setErrorLogs("");
        fetchSessionDetail(data.id);
        fetchWithAuth(`${API_BASE_URL}/agents/sessions`)
          .then((res) => (res.ok ? res.json() : []))
          .then((list) => Array.isArray(list) && setSessions(list))
          .catch(() => {});
      }
    } catch {
      setErrMsg("Network error launching agent session.");
    } finally {
      setSubmitting(false);
    }
  };

  const flowNodes: Node[] = useMemo(() => {
    const executed = new Map<string, AgentExecutionItem>();
    for (const ex of activeSession?.executions ?? []) {
      executed.set(ex.agent_name, ex);
    }
    return DAG_LAYOUT.map((n) => {
      const ex = executed.get(n.id);
      const isCurrent = activeSession?.current_phase === n.id && activeSession.status !== "COMPLETED";
      const bg = ex
        ? ex.status === "FAILED"
          ? "#450a0a"
          : "#064e3b"
        : isCurrent
        ? "#3b0764"
        : "#111827";
      const border = ex
        ? ex.status === "FAILED"
          ? "#f43f5e"
          : "#10b981"
        : isCurrent
        ? "#8b5cf6"
        : "#374151";

      return {
        id: n.id,
        position: { x: n.x, y: n.y },
        data: {
          label: (
            <div className="text-left">
              <div className="text-xs font-bold text-white">{n.label}</div>
              <div className="text-[10px] font-mono text-slate-300 mt-0.5">
                {ex ? `${ex.status} (${ex.duration_ms}ms)` : isCurrent ? "RUNNING" : "IDLE"}
              </div>
            </div>
          ),
        },
        style: {
          background: bg,
          border: `1.5px solid ${border}`,
          borderRadius: 10,
          padding: "8px 12px",
          width: 155,
          color: "#f8fafc",
        },
      };
    });
  }, [activeSession]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">
            Agent Control Center (LangGraph)
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            8-agent LangGraph state machine with RAG, AST/Security auditing, pytest verification, and bounded self-repair
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div
            className={`flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-mono ${
              llmConfigured
                ? "bg-emerald-950/40 border-emerald-700/40 text-emerald-300"
                : "bg-amber-950/40 border-amber-700/40 text-amber-300"
            }`}
          >
            <Zap className="w-3.5 h-3.5" />
            <span>
              {llmConfigured === null
                ? "Checking LLM..."
                : llmConfigured
                ? `LLM: ${llmModel}`
                : "Static/RAG Mode (No OPENAI_API_KEY)"}
            </span>
          </div>
          <button
            onClick={loadInitial}
            className="p-2 rounded-xl bg-[#111827] border border-border hover:border-violet-500 text-muted-foreground hover:text-white"
            title="Refresh"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Live LangGraph DAG */}
      <div className="rounded-2xl bg-[#0A0E17] border border-border/80 overflow-hidden">
        <div className="px-4 py-2.5 bg-[#111827] border-b border-border/80 flex items-center justify-between text-xs font-mono">
          <span className="flex items-center gap-2 text-violet-300">
            <Bot className="w-4 h-4" />
            LangGraph Orchestration DAG
          </span>
          {activeSession && (
            <span className="text-muted-foreground">
              Session: <span className="text-white">{activeSession.title}</span> &bull;{" "}
              <span className="text-cyan-400">{activeSession.status}</span>
            </span>
          )}
        </div>
        <div className="h-[310px] w-full">
          <ReactFlow nodes={flowNodes} edges={DAG_EDGES} fitView proOptions={{ hideAttribution: true }}>
            <Background color="#1f2937" gap={18} />
            <Controls />
          </ReactFlow>
        </div>
      </div>

      {/* Launch Form + Session History */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <form
          onSubmit={handleLaunch}
          className="lg:col-span-2 p-5 rounded-2xl bg-[#111827] border border-border/80 space-y-4"
        >
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <Play className="w-4 h-4 text-violet-400" />
            Launch Multi-Agent Session
          </h2>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-mono text-muted-foreground block mb-1">Repository</label>
              <select
                value={selectedRepo}
                onChange={(e) => setSelectedRepo(e.target.value)}
                className="w-full bg-[#0A0E17] border border-border rounded-xl px-3 py-2 text-sm text-foreground font-mono"
              >
                {repos.length === 0 && <option value="">No repositories</option>}
                {repos.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.full_name} [{r.status}]
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs font-mono text-muted-foreground block mb-1">Task / Issue Title</label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Audit escape() and fix edge case"
                className="w-full bg-[#0A0E17] border border-border rounded-xl px-3 py-2 text-sm text-foreground"
                required
              />
            </div>
          </div>

          <div>
            <label className="text-xs font-mono text-muted-foreground block mb-1">Description / Objective</label>
            <textarea
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe the bug, failing behavior, or security audit target..."
              className="w-full bg-[#0A0E17] border border-border rounded-xl px-3 py-2 text-sm text-foreground"
              required
            />
          </div>

          <div>
            <label className="text-xs font-mono text-muted-foreground block mb-1">
              Error Logs / Stack Trace (optional)
            </label>
            <textarea
              rows={2}
              value={errorLogs}
              onChange={(e) => setErrorLogs(e.target.value)}
              placeholder='File "app/main.py", line 42 ...'
              className="w-full bg-[#0A0E17] border border-border rounded-xl px-3 py-2 text-xs font-mono text-foreground"
            />
          </div>

          {errMsg && (
            <div className="text-xs text-red-400 font-mono flex items-center gap-1.5">
              <AlertCircle className="w-4 h-4" />
              {errMsg}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting || !selectedRepo}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white text-sm font-semibold"
          >
            {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Activity className="w-4 h-4" />}
            Run 8-Agent Workflow
          </button>
        </form>

        {/* Recent Sessions */}
        <div className="p-5 rounded-2xl bg-[#111827] border border-border/80 space-y-3">
          <h2 className="text-base font-bold text-white">Recent Sessions</h2>
          <div className="space-y-2 max-h-[260px] overflow-y-auto pr-1">
            {sessions.length === 0 ? (
              <p className="text-xs text-muted-foreground">No agent sessions yet.</p>
            ) : (
              sessions.map((s) => (
                <button
                  key={s.id}
                  onClick={() => fetchSessionDetail(s.id)}
                  className={`w-full text-left p-3 rounded-xl border transition-colors ${
                    activeSession?.id === s.id
                      ? "bg-violet-950/30 border-violet-500/60"
                      : "bg-[#0A0E17] border-border hover:border-violet-500/40"
                  }`}
                >
                  <div className="text-xs font-bold text-white truncate">{s.title}</div>
                  <div className="flex items-center justify-between text-[11px] font-mono text-muted-foreground mt-1">
                    <span>{s.status}</span>
                    <span>retries: {s.retry_count}</span>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Execution Trace */}
      {activeSession && (
        <div className="p-5 rounded-2xl bg-[#111827] border border-border/80 space-y-3">
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <Terminal className="w-4 h-4 text-cyan-400" />
            Agent Execution Trace ({activeSession.executions.length} steps)
          </h2>
          <div className="space-y-2">
            {activeSession.executions.map((ex) => (
              <div
                key={ex.id}
                className="p-3 rounded-xl bg-[#0A0E17] border border-border/70 flex flex-col gap-2"
              >
                <div className="flex items-center justify-between text-xs font-mono">
                  <span className="flex items-center gap-2 text-white font-semibold">
                    {ex.status === "COMPLETED" ? (
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                    ) : (
                      <Clock className="w-3.5 h-3.5 text-amber-400" />
                    )}
                    {ex.agent_name}
                  </span>
                  <span className="text-muted-foreground">{ex.duration_ms} ms</span>
                </div>
                <pre className="text-[11px] font-mono text-slate-300 overflow-x-auto whitespace-pre-wrap max-h-40">
                  {JSON.stringify(ex.output, null, 2)}
                </pre>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
