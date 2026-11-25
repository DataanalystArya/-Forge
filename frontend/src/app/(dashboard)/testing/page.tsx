"use client";

import React, { useEffect, useState } from "react";
import {
  CheckCircle2,
  XCircle,
  Play,
  Terminal,
  Loader2,
  RefreshCw,
  Clock,
} from "lucide-react";
import { fetchWithAuth } from "@/lib/utils";

interface Repository {
  id: string;
  full_name: string;
}

interface TestRunItem {
  id: string;
  session_id: string;
  session_title: string;
  repo_id: string;
  repo_name: string;
  command: string;
  passed: number;
  failed: number;
  exit_code: number;
  stdout: string;
  stderr: string;
  duration_ms: number;
  created_at: string;
}

export default function TestingCenterPage() {
  const [repos, setRepos] = useState<Repository[]>([]);
  const [selectedRepoId, setSelectedRepoId] = useState("");
  const [testPath, setTestPath] = useState("");
  const [runs, setRuns] = useState<TestRunItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  useEffect(() => {
    loadInitial();
  }, []);

  async function loadInitial() {
    setLoading(true);
    try {
      const [repoRes, runsRes] = await Promise.all([
        fetchWithAuth("/repositories"),
        fetchWithAuth("/debugging/test-runs"),
      ]);
      if (repoRes.ok) {
        const d = await repoRes.json();
        const list = Array.isArray(d) ? d : d.items || d.repositories || [];
        setRepos(list);
        if (list.length > 0 && !selectedRepoId) {
          setSelectedRepoId(list[0].id);
        }
      }
      if (runsRes.ok) {
        const r = await runsRes.json();
        const list = Array.isArray(r) ? r : [];
        setRuns(list);
        if (list.length > 0 && !expandedId) {
          setExpandedId(list[0].id);
        }
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleRunTests() {
    if (!selectedRepoId) return;
    setRunning(true);
    setFeedback(null);
    try {
      const res = await fetchWithAuth("/debugging/run-tests", {
        method: "POST",
        body: JSON.stringify({ repo_id: selectedRepoId, test_path: testPath }),
      });
      const d = await res.json();
      if (res.ok) {
        setFeedback(
          `Test run finished with exit code ${d.exit_code} (${d.passed} passed, ${d.failed} failed in ${d.duration_ms}ms).`
        );
        await loadInitial();
        if (d.id) setExpandedId(d.id);
      } else {
        setFeedback(`Execution failed: ${d.detail || "Unknown error"}`);
      }
    } catch (err) {
      setFeedback(`Execution failed: ${String(err)}`);
    } finally {
      setRunning(false);
    }
  }

  const passedRuns = runs.filter((r) => r.exit_code === 0).length;
  const failedRuns = runs.filter((r) => r.exit_code !== 0).length;

  return (
    <div className="space-y-6">
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Testing Center</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Automated pytest execution and regression verification in isolated repository workspaces
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <select
            value={selectedRepoId}
            onChange={(e) => setSelectedRepoId(e.target.value)}
            className="bg-[#0A0E17] border border-border rounded-xl px-3 py-2 text-xs text-white font-mono focus:outline-none focus:border-emerald-500"
          >
            {repos.length === 0 ? (
              <option value="">No repositories</option>
            ) : (
              repos.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.full_name}
                </option>
              ))
            )}
          </select>

          <input
            type="text"
            value={testPath}
            onChange={(e) => setTestPath(e.target.value)}
            placeholder="tests/ (optional path)"
            className="bg-[#0A0E17] border border-border rounded-xl px-3 py-2 text-xs text-white font-mono focus:outline-none focus:border-emerald-500 w-44"
          />

          <button
            onClick={handleRunTests}
            disabled={running || !selectedRepoId}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-medium transition"
          >
            {running ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
            <span>{running ? "Running pytest..." : "Run Tests in Sandbox"}</span>
          </button>

          <button
            onClick={loadInitial}
            className="p-2 rounded-xl bg-[#0A0E17] border border-border text-muted-foreground hover:text-white transition"
            title="Refresh test runs"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {feedback && (
        <div className="p-3 rounded-xl bg-cyan-950/30 border border-cyan-800/50 text-cyan-200 text-xs font-mono">
          {feedback}
        </div>
      )}

      {/* KPI Row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="p-4 rounded-2xl bg-[#111827] border border-border/80">
          <div className="text-xs font-mono text-muted-foreground">TOTAL TEST RUNS</div>
          <div className="text-2xl font-bold text-white mt-1">{runs.length}</div>
        </div>
        <div className="p-4 rounded-2xl bg-[#111827] border border-emerald-900/40">
          <div className="text-xs font-mono text-emerald-400">PASSED (EXIT 0)</div>
          <div className="text-2xl font-bold text-white mt-1">{passedRuns}</div>
        </div>
        <div className="p-4 rounded-2xl bg-[#111827] border border-rose-900/40">
          <div className="text-xs font-mono text-rose-400">FAILED / REGRESSION</div>
          <div className="text-2xl font-bold text-white mt-1">{failedRuns}</div>
        </div>
      </div>

      {runs.length === 0 ? (
        <div className="p-12 rounded-2xl bg-[#111827] border border-border/80 text-center">
          {loading ? (
            <Loader2 className="w-8 h-8 mx-auto text-muted-foreground animate-spin mb-3" />
          ) : (
            <Terminal className="w-10 h-10 mx-auto text-muted-foreground/40 mb-3" />
          )}
          <h3 className="text-base font-bold text-white mb-1">
            {loading ? "Loading Test Runs..." : "No Sandbox Test Runs Recorded"}
          </h3>
          <p className="text-xs text-muted-foreground max-w-md mx-auto">
            Select a repository above and click &quot;Run Tests in Sandbox&quot; to execute pytest in an isolated subprocess and inspect real stdout/stderr logs.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {runs.map((r) => {
            const isOpen = expandedId === r.id;
            const passed = r.exit_code === 0;
            return (
              <div
                key={r.id}
                className="rounded-2xl bg-[#111827] border border-border/80 overflow-hidden"
              >
                <button
                  onClick={() => setExpandedId(isOpen ? null : r.id)}
                  className="w-full p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-left hover:bg-[#0A0E17]/40 transition"
                >
                  <div className="flex items-center gap-3">
                    {passed ? (
                      <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
                    ) : (
                      <XCircle className="w-5 h-5 text-rose-400 shrink-0" />
                    )}
                    <div>
                      <div className="text-sm font-bold text-white">
                        {r.repo_name} &bull;{" "}
                        <span className="font-mono text-xs text-cyan-300">{r.session_title}</span>
                      </div>
                      <div className="text-xs font-mono text-muted-foreground mt-0.5">
                        {r.command}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-3 text-xs font-mono">
                    <span className="text-emerald-400">{r.passed} passed</span>
                    <span className="text-rose-400">{r.failed} failed</span>
                    <span className="text-muted-foreground flex items-center gap-1">
                      <Clock className="w-3.5 h-3.5" />
                      {r.duration_ms}ms
                    </span>
                    <span
                      className={`px-2 py-0.5 rounded border ${
                        passed
                          ? "bg-emerald-950/50 border-emerald-800 text-emerald-300"
                          : "bg-rose-950/50 border-rose-800 text-rose-300"
                      }`}
                    >
                      EXIT {r.exit_code}
                    </span>
                  </div>
                </button>

                {isOpen && (
                  <div className="p-4 border-t border-border bg-[#0A0E17] space-y-3">
                    {r.stdout && (
                      <div>
                        <div className="text-[11px] font-mono uppercase text-muted-foreground mb-1">
                          STDOUT
                        </div>
                        <pre className="p-3 rounded-xl bg-black/50 border border-border/60 text-xs font-mono text-slate-200 overflow-x-auto max-h-64">
                          {r.stdout}
                        </pre>
                      </div>
                    )}
                    {r.stderr && (
                      <div>
                        <div className="text-[11px] font-mono uppercase text-rose-400 mb-1">
                          STDERR
                        </div>
                        <pre className="p-3 rounded-xl bg-rose-950/20 border border-rose-900/40 text-xs font-mono text-rose-200 overflow-x-auto max-h-48">
                          {r.stderr}
                        </pre>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
