"use client";

import React, { useEffect, useState } from "react";
import {
  ShieldAlert,
  ShieldCheck,
  Lock,
  Play,
  Loader2,
  RefreshCw,
  AlertTriangle,
} from "lucide-react";
import { fetchWithAuth } from "@/lib/utils";

interface Repository {
  id: string;
  full_name: string;
}

interface SecurityFindingItem {
  id?: string;
  session_id?: string;
  repo_id?: string;
  repo_name?: string;
  rule_id: string;
  severity: string;
  file_path: string;
  line_number: number;
  message: string;
  recommendation: string;
}

export default function SecurityCenterPage() {
  const [repos, setRepos] = useState<Repository[]>([]);
  const [selectedRepoId, setSelectedRepoId] = useState("");
  const [findings, setFindings] = useState<SecurityFindingItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [scanFeedback, setScanFeedback] = useState<string | null>(null);

  useEffect(() => {
    loadInitial();
  }, []);

  async function loadInitial() {
    setLoading(true);
    try {
      const [repoRes, findRes] = await Promise.all([
        fetchWithAuth("/repositories"),
        fetchWithAuth("/debugging/security-findings"),
      ]);
      if (repoRes.ok) {
        const d = await repoRes.json();
        const list = Array.isArray(d) ? d : d.items || d.repositories || [];
        setRepos(list);
        if (list.length > 0 && !selectedRepoId) {
          setSelectedRepoId(list[0].id);
        }
      }
      if (findRes.ok) {
        const f = await findRes.json();
        setFindings(Array.isArray(f) ? f : []);
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleRunScan() {
    if (!selectedRepoId) return;
    setScanning(true);
    setScanFeedback(null);
    try {
      const res = await fetchWithAuth("/debugging/security-scan", {
        method: "POST",
        body: JSON.stringify({ repo_id: selectedRepoId }),
      });
      const d = await res.json();
      if (res.ok) {
        setScanFeedback(
          `Scanned ${d.files_scanned} files — found ${d.findings_count} security issue(s).`
        );
        await loadInitial();
      } else {
        setScanFeedback(`Scan failed: ${d.detail || "Unknown error"}`);
      }
    } catch (err) {
      setScanFeedback(`Scan failed: ${String(err)}`);
    } finally {
      setScanning(false);
    }
  }

  const criticalCount = findings.filter((f) => f.severity === "CRITICAL").length;
  const highCount = findings.filter((f) => f.severity === "HIGH").length;
  const mediumCount = findings.filter((f) => f.severity === "MEDIUM").length;

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Security Audit Center</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Static AST analysis, secret leak detection, and unsafe execution rule verification
          </p>
        </div>

        <div className="flex items-center gap-2">
          <select
            value={selectedRepoId}
            onChange={(e) => setSelectedRepoId(e.target.value)}
            className="bg-[#0A0E17] border border-border rounded-xl px-3 py-2 text-xs text-white font-mono focus:outline-none focus:border-amber-500"
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

          <button
            onClick={handleRunScan}
            disabled={scanning || !selectedRepoId}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white text-xs font-medium transition"
          >
            {scanning ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
            <span>{scanning ? "Scanning..." : "Run Security Audit"}</span>
          </button>

          <button
            onClick={loadInitial}
            className="p-2 rounded-xl bg-[#0A0E17] border border-border text-muted-foreground hover:text-white transition"
            title="Refresh findings"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {scanFeedback && (
        <div className="p-3 rounded-xl bg-amber-950/30 border border-amber-800/50 text-amber-200 text-xs font-mono">
          {scanFeedback}
        </div>
      )}

      {/* Severity Summary */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="p-4 rounded-2xl bg-[#111827] border border-rose-900/40">
          <div className="text-xs font-mono text-rose-400">CRITICAL</div>
          <div className="text-2xl font-bold text-white mt-1">{criticalCount}</div>
        </div>
        <div className="p-4 rounded-2xl bg-[#111827] border border-amber-900/40">
          <div className="text-xs font-mono text-amber-400">HIGH</div>
          <div className="text-2xl font-bold text-white mt-1">{highCount}</div>
        </div>
        <div className="p-4 rounded-2xl bg-[#111827] border border-cyan-900/40">
          <div className="text-xs font-mono text-cyan-400">MEDIUM</div>
          <div className="text-2xl font-bold text-white mt-1">{mediumCount}</div>
        </div>
      </div>

      {findings.length === 0 ? (
        <div className="p-12 rounded-2xl bg-[#111827] border border-border/80 text-center">
          {loading ? (
            <Loader2 className="w-8 h-8 mx-auto text-muted-foreground animate-spin mb-3" />
          ) : (
            <ShieldCheck className="w-10 h-10 mx-auto text-emerald-400/60 mb-3" />
          )}
          <h3 className="text-base font-bold text-white mb-1">
            {loading ? "Loading Security Findings..." : "No Security Vulnerabilities Recorded"}
          </h3>
          <p className="text-xs text-muted-foreground max-w-md mx-auto">
            Select a repository above and click &quot;Run Security Audit&quot; to inspect source files for injection risks, hardcoded secrets, and unsafe deserialization.
          </p>
        </div>
      ) : (
        <div className="rounded-2xl bg-[#111827] border border-border/80 overflow-hidden">
          <div className="p-4 border-b border-border flex items-center justify-between">
            <h2 className="text-sm font-bold text-white flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-amber-400" />
              <span>Recorded Security Findings ({findings.length})</span>
            </h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-[#0A0E17] text-muted-foreground font-mono uppercase">
                <tr>
                  <th className="px-4 py-3">Severity</th>
                  <th className="px-4 py-3">Rule</th>
                  <th className="px-4 py-3">Repository</th>
                  <th className="px-4 py-3">Location</th>
                  <th className="px-4 py-3">Description & Remediation</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/50">
                {findings.map((f, i) => (
                  <tr key={f.id || `${f.rule_id}-${i}`} className="hover:bg-[#0A0E17]/60">
                    <td className="px-4 py-3">
                      <span
                        className={`px-2 py-0.5 rounded font-mono text-[10px] font-bold ${
                          f.severity === "CRITICAL"
                            ? "bg-rose-950/70 text-rose-300 border border-rose-800"
                            : f.severity === "HIGH"
                            ? "bg-amber-950/70 text-amber-300 border border-amber-800"
                            : "bg-cyan-950/70 text-cyan-300 border border-cyan-800"
                        }`}
                      >
                        {f.severity}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono text-violet-300">{f.rule_id}</td>
                    <td className="px-4 py-3 text-muted-foreground font-mono">{f.repo_name}</td>
                    <td className="px-4 py-3 font-mono text-cyan-300">
                      {f.file_path}:{f.line_number}
                    </td>
                    <td className="px-4 py-3">
                      <div className="text-white">{f.message}</div>
                      {f.recommendation && (
                        <div className="text-emerald-400/90 text-[11px] mt-0.5">
                          Fix: {f.recommendation}
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
