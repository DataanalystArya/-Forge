"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  GitPullRequest,
  GitBranch,
  Check,
  ExternalLink,
  ShieldCheck,
  RefreshCw,
  Plus,
  Lock,
  FileCode,
  AlertCircle,
} from "lucide-react";
import { fetchWithAuth } from "@/lib/utils";

interface PullRequestItem {
  id: string;
  session_id: string;
  repo_id: string;
  branch: string;
  pr_number: number;
  pr_url: string;
  title: string;
  status: string;
  created_at: string;
}

interface DebuggingSessionSummary {
  id: string;
  repo_id: string;
  status: string;
  title: string;
  current_phase: string;
  created_at: string;
}

interface PatchDiffItem {
  patch_id: string;
  iteration: number;
  diff: string;
  rationale: string;
  is_applied: boolean;
}

export default function PullRequestsPage() {
  const [prs, setPrs] = useState<PullRequestItem[]>([]);
  const [loadingPrs, setLoadingPrs] = useState(false);

  // Creation form state
  const [sessions, setSessions] = useState<DebuggingSessionSummary[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string>("");
  const [sessionDiffs, setSessionDiffs] = useState<PatchDiffItem[]>([]);
  const [loadingDiffs, setLoadingDiffs] = useState(false);

  const [prTitle, setPrTitle] = useState("");
  const [prBody, setPrBody] = useState("");
  const [baseBranch, setBaseBranch] = useState("main");
  const [draft, setDraft] = useState(true);
  const [githubToken, setGithubToken] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [statusMessage, setStatusMessage] = useState<{ text: string; error: boolean } | null>(null);

  const loadPRs = useCallback(async () => {
    setLoadingPrs(true);
    try {
      const res = await fetchWithAuth("/automation/pull-requests");
      if (res.ok) {
        const data = await res.json();
        setPrs(Array.isArray(data) ? data : (data.items || []));
      }
    } catch (err) {
      console.error("Failed to load pull requests", err);
    } finally {
      setLoadingPrs(false);
    }
  }, []);

  const loadSessions = useCallback(async () => {
    try {
      const res = await fetchWithAuth("/debugging/sessions");
      if (res.ok) {
        const data = await res.json();
        const list = Array.isArray(data) ? data : (data.items || []);
        setSessions(list);
        if (list.length > 0 && !selectedSessionId) {
          setSelectedSessionId(list[0].id);
          setPrTitle(`fix: resolve ${list[0].title}`);
          setPrBody(`Automated patch synthesized and verified by FORGE.\n\n- Task: ${list[0].title}`);
        }
      }
    } catch (err) {
      console.error("Failed to load sessions", err);
    }
  }, [selectedSessionId]);

  useEffect(() => {
    loadPRs();
    loadSessions();
  }, [loadPRs, loadSessions]);

  // Load diffs when session selection changes
  useEffect(() => {
    if (!selectedSessionId) return;
    async function fetchDiffs() {
      setLoadingDiffs(true);
      try {
        const res = await fetchWithAuth(`/automation/sessions/${selectedSessionId}/diff`);
        if (res.ok) {
          const data = await res.json();
          setSessionDiffs(data.patches || []);
        }
      } catch (err) {
        console.error("Failed to load session diff", err);
      } finally {
        setLoadingDiffs(false);
      }
    }
    fetchDiffs();
  }, [selectedSessionId]);

  async function handleCreatePR() {
    if (!selectedSessionId || !githubToken.trim()) {
      setStatusMessage({ text: "GitHub Personal Access Token is required to create a PR.", error: true });
      return;
    }
    setIsSubmitting(true);
    setStatusMessage(null);
    try {
      const res = await fetchWithAuth(`/automation/sessions/${selectedSessionId}/create-pr`, {
        method: "POST",
        body: JSON.stringify({
          session_id: selectedSessionId,
          title: prTitle,
          body: prBody,
          base_branch: baseBranch,
          draft: draft,
          github_token: githubToken,
        }),
      });
      const data = await res.json();
      if (res.ok && data.ok) {
        setStatusMessage({ text: `Pull Request #${data.pr_number} created successfully!`, error: false });
        await loadPRs();
      } else {
        setStatusMessage({ text: `Error: ${data.detail || data.error || "Failed to create PR"}`, error: true });
      }
    } catch (err) {
      setStatusMessage({ text: `Failed to create PR: ${String(err)}`, error: true });
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Pull Request & Automation Center</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Human-in-the-Loop approval gate for branch creation, commits, diff inspection, and GitHub Pull Requests
          </p>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-violet-950/40 border border-violet-800/40 text-violet-300 text-xs font-mono">
          <GitPullRequest className="w-3.5 h-3.5 text-violet-400" />
          <span>HUMAN APPROVAL REQUIRED</span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Create PR Form */}
        <div className="p-6 rounded-2xl bg-[#111827] border border-border/80 space-y-4">
          <h3 className="text-base font-bold text-white flex items-center gap-2">
            <Plus className="w-4 h-4 text-cyan-400" />
            <span>Create GitHub Pull Request</span>
          </h3>

          <div>
            <label className="text-xs font-medium text-muted-foreground block mb-1">Approved Debugging Session</label>
            <select
              value={selectedSessionId}
              onChange={(e) => {
                setSelectedSessionId(e.target.value);
                const s = sessions.find((x) => x.id === e.target.value);
                if (s) {
                  setPrTitle(`fix: resolve ${s.title}`);
                  setPrBody(`Automated patch synthesized and verified by FORGE.\n\n- Task: ${s.title}`);
                }
              }}
              className="w-full bg-[#0A0E17] border border-border rounded-xl p-2.5 text-sm text-foreground focus:outline-none focus:border-violet-500"
            >
              {sessions.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.title} ({s.status})
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium text-muted-foreground block mb-1">Base Branch</label>
              <input
                type="text"
                value={baseBranch}
                onChange={(e) => setBaseBranch(e.target.value)}
                placeholder="main"
                className="w-full bg-[#0A0E17] border border-border rounded-xl p-2.5 text-sm text-foreground focus:outline-none focus:border-violet-500 font-mono"
              />
            </div>
            <div className="flex items-center pt-5">
              <label className="flex items-center gap-2 cursor-pointer text-xs text-muted-foreground">
                <input
                  type="checkbox"
                  checked={draft}
                  onChange={(e) => setDraft(e.target.checked)}
                  className="rounded border-border bg-[#0A0E17] text-violet-600 focus:ring-0"
                />
                <span>Create as Draft PR (Recommended)</span>
              </label>
            </div>
          </div>

          <div>
            <label className="text-xs font-medium text-muted-foreground block mb-1">PR Title</label>
            <input
              type="text"
              value={prTitle}
              onChange={(e) => setPrTitle(e.target.value)}
              placeholder="fix: address bug in module"
              className="w-full bg-[#0A0E17] border border-border rounded-xl p-2.5 text-sm text-foreground focus:outline-none focus:border-violet-500"
            />
          </div>

          <div>
            <label className="text-xs font-medium text-muted-foreground block mb-1">PR Description / Body</label>
            <textarea
              rows={3}
              value={prBody}
              onChange={(e) => setPrBody(e.target.value)}
              placeholder="Summary of changes and sandbox verification results..."
              className="w-full bg-[#0A0E17] border border-border rounded-xl p-2.5 text-xs text-foreground focus:outline-none focus:border-violet-500 font-mono"
            />
          </div>

          <div>
            <label className="text-xs font-medium text-muted-foreground block mb-1 flex items-center justify-between">
              <span>GitHub Personal Access Token (PAT)</span>
              <span className="text-[10px] text-amber-400 font-mono flex items-center gap-1">
                <Lock className="w-3 h-3" /> Never stored on disk
              </span>
            </label>
            <input
              type="password"
              value={githubToken}
              onChange={(e) => setGithubToken(e.target.value)}
              placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
              className="w-full bg-[#0A0E17] border border-border rounded-xl p-2.5 text-xs text-foreground focus:outline-none focus:border-violet-500 font-mono"
            />
          </div>

          {statusMessage && (
            <div
              className={`p-3 rounded-xl border text-xs font-mono flex items-center gap-2 ${
                statusMessage.error
                  ? "bg-rose-950/40 border-rose-800 text-rose-300"
                  : "bg-emerald-950/40 border-emerald-800 text-emerald-300"
              }`}
            >
              {statusMessage.error ? <AlertCircle className="w-4 h-4 shrink-0" /> : <Check className="w-4 h-4 shrink-0" />}
              <span>{statusMessage.text}</span>
            </div>
          )}

          <button
            onClick={handleCreatePR}
            disabled={isSubmitting || !selectedSessionId}
            className="w-full py-3 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white font-medium rounded-xl text-sm flex items-center justify-center gap-2 transition"
          >
            {isSubmitting ? <RefreshCw className="w-4 h-4 animate-spin" /> : <GitPullRequest className="w-4 h-4" />}
            <span>Approve & Open GitHub Pull Request</span>
          </button>
        </div>

        {/* Patch Preview & Pull Request History */}
        <div className="space-y-6">
          {/* Patches in selected session */}
          <div className="p-6 rounded-2xl bg-[#111827] border border-border/80 space-y-3">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <FileCode className="w-4 h-4 text-violet-400" />
              <span>Approved Patches in Selected Session ({sessionDiffs.length})</span>
            </h3>

            {loadingDiffs ? (
              <div className="p-4 text-xs text-muted-foreground text-center">Loading diffs...</div>
            ) : sessionDiffs.length === 0 ? (
              <div className="p-4 rounded-xl bg-[#0A0E17] border border-border text-xs text-muted-foreground text-center">
                No patches found in this session yet.
              </div>
            ) : (
              sessionDiffs.map((p, idx) => (
                <div key={idx} className="p-3 rounded-xl bg-[#0A0E17] border border-border space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-mono text-cyan-300">Iteration {p.iteration}</span>
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-mono ${
                        p.is_applied ? "bg-emerald-950/60 text-emerald-300" : "bg-amber-950/60 text-amber-300"
                      }`}
                    >
                      {p.is_applied ? "Applied" : "Pending Approval"}
                    </span>
                  </div>
                  <pre className="p-2.5 rounded bg-[#050811] text-[11px] font-mono text-gray-300 overflow-x-auto max-h-[140px]">
                    {p.diff || "/* No diff content */"}
                  </pre>
                </div>
              ))
            )}
          </div>

          {/* Existing Pull Requests Table */}
          <div className="p-6 rounded-2xl bg-[#111827] border border-border/80 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <GitBranch className="w-4 h-4 text-emerald-400" />
                <span>Pull Request Registry ({prs.length})</span>
              </h3>
              <button onClick={loadPRs} className="text-muted-foreground hover:text-white transition">
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            </div>

            {prs.length === 0 ? (
              <div className="p-6 rounded-xl bg-[#0A0E17] border border-border text-xs text-muted-foreground text-center">
                No pull requests created yet.
              </div>
            ) : (
              <div className="space-y-2">
                {prs.map((pr) => (
                  <div
                    key={pr.id}
                    className="p-3.5 rounded-xl bg-[#0A0E17] border border-border flex items-center justify-between text-xs"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-white">#{pr.pr_number}</span>
                        <span className="text-muted-foreground truncate max-w-[200px]">{pr.title}</span>
                      </div>
                      <div className="text-[11px] text-muted-foreground font-mono mt-0.5">Branch: {pr.branch}</div>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-emerald-950/60 text-emerald-300">
                        {pr.status}
                      </span>
                      {pr.pr_url && (
                        <a
                          href={pr.pr_url}
                          target="_blank"
                          rel="noreferrer"
                          className="p-1.5 rounded-lg bg-border/40 hover:bg-border text-cyan-300 transition"
                        >
                          <ExternalLink className="w-3.5 h-3.5" />
                        </a>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
