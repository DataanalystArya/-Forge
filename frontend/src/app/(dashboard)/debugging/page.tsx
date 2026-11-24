"use client";

import React, { useState } from "react";
import { Bug, Terminal, Play, CheckCircle2, History, AlertTriangle } from "lucide-react";

export default function DebuggingPage() {
  const [issueDesc, setIssueDesc] = useState("");
  const [errorLogs, setErrorLogs] = useState("");

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">AI Debugging Workspace</h1>
          <p className="text-sm text-muted-foreground mt-1">
            End-to-end autonomous root cause analysis, patch synthesis, sandbox verification, and self-repair
          </p>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-violet-950/40 border border-violet-800/40 text-violet-300 text-xs font-mono">
          <Terminal className="w-3.5 h-3.5 text-violet-400" />
          <span>PHASE 6 ENGINE</span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="p-6 rounded-2xl bg-[#111827] border border-border/80 space-y-4">
          <h3 className="text-base font-bold text-white flex items-center gap-2">
            <Bug className="w-4 h-4 text-rose-400" />
            <span>Problem Description</span>
          </h3>
          <textarea
            rows={4}
            value={issueDesc}
            onChange={(e) => setIssueDesc(e.target.value)}
            placeholder="Describe the bug, unexpected behavior, or reproduction steps..."
            className="w-full bg-[#0A0E17] border border-border rounded-xl p-3.5 text-sm text-foreground focus:outline-none focus:border-violet-500 font-sans"
          />

          <h3 className="text-base font-bold text-white flex items-center gap-2 pt-2">
            <Terminal className="w-4 h-4 text-cyan-400" />
            <span>Error Logs / Stack Trace (Optional)</span>
          </h3>
          <textarea
            rows={5}
            value={errorLogs}
            onChange={(e) => setErrorLogs(e.target.value)}
            placeholder="Paste pytest failure traces, traceback logs, or exception outputs..."
            className="w-full bg-[#0A0E17] border border-border rounded-xl p-3.5 text-xs text-foreground focus:outline-none focus:border-violet-500 font-mono"
          />

          <button
            disabled
            className="w-full py-3 bg-violet-600/50 cursor-not-allowed text-white/70 font-medium rounded-xl text-sm flex items-center justify-center gap-2"
          >
            <Play className="w-4 h-4" />
            <span>Initiate Autonomous Debugging (Configured in Phase 6)</span>
          </button>
        </div>

        <div className="p-6 rounded-2xl bg-[#111827] border border-border/80 flex flex-col justify-between">
          <div>
            <h3 className="text-base font-bold text-white flex items-center gap-2 mb-4">
              <History className="w-4 h-4 text-violet-400" />
              <span>Self-Repair Lifecycle</span>
            </h3>

            <div className="space-y-3 text-xs font-mono">
              {[
                { label: "1. Intake & Planning", desc: "Planner decomposes issue into targeted subtasks" },
                { label: "2. Code RAG Retrieval", desc: "Fetch affected functions and calling contexts" },
                { label: "3. Root Cause Investigation", desc: "Bug Detector confirms flaw location" },
                { label: "4. Patch Generation", desc: "Coding Agent produces minimal unified diff" },
                { label: "5. Sandbox Test Execution", desc: "Isolated Pytest runner verifies behavior" },
                { label: "6. Self-Repair Correction", desc: "Re-tries if test fails (bounded to 3 iterations)" },
                { label: "7. Review & HITL Gate", desc: "Code Review Agent inspects before PR proposal" },
              ].map((step, idx) => (
                <div key={idx} className="p-2.5 rounded-lg bg-[#0A0E17] border border-border/60">
                  <div className="text-cyan-400 font-bold">{step.label}</div>
                  <div className="text-muted-foreground mt-0.5">{step.desc}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="pt-4 border-t border-border text-[11px] font-mono text-muted-foreground">
            Zero Unverified Patches &bull; All changes must pass isolated sandbox tests.
          </div>
        </div>
      </div>
    </div>
  );
}
