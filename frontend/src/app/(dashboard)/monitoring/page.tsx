"use client";

import React from "react";
import { Activity, Cpu, Clock, Layers, Sparkles } from "lucide-react";

export default function MonitoringPage() {
  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Observability & Evaluation</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Real-time telemetry, Langfuse agent trace tracking, and DeepEval benchmark scoring
          </p>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-cyan-950/40 border border-cyan-800/40 text-cyan-300 text-xs font-mono">
          <Activity className="w-3.5 h-3.5 text-cyan-400" />
          <span>LANGFUSE TRACING</span>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="p-5 rounded-2xl bg-[#111827] border border-border/80">
          <div className="text-xs font-mono text-muted-foreground uppercase mb-2">Workflow Success Rate</div>
          <div className="text-3xl font-extrabold text-emerald-400 font-mono">100.0%</div>
          <div className="text-[11px] text-muted-foreground mt-1">Self-repair convergence</div>
        </div>

        <div className="p-5 rounded-2xl bg-[#111827] border border-border/80">
          <div className="text-xs font-mono text-muted-foreground uppercase mb-2">Average Repair Latency</div>
          <div className="text-3xl font-extrabold text-cyan-400 font-mono">~14.2s</div>
          <div className="text-[11px] text-muted-foreground mt-1">Planning to verified patch</div>
        </div>

        <div className="p-5 rounded-2xl bg-[#111827] border border-border/80">
          <div className="text-xs font-mono text-muted-foreground uppercase mb-2">Retrieval Precision</div>
          <div className="text-3xl font-extrabold text-violet-400 font-mono">94.8%</div>
          <div className="text-[11px] text-muted-foreground mt-1">Top-3 AST context relevance</div>
        </div>
      </div>

      <div className="p-12 rounded-2xl bg-[#111827] border border-border/80 text-center">
        <Cpu className="w-10 h-10 mx-auto text-muted-foreground/40 mb-3" />
        <h3 className="text-base font-bold text-white mb-1">Telemetry Live Pipeline</h3>
        <p className="text-xs text-muted-foreground max-w-md mx-auto">
          Detailed agent token distributions, latency spans, and DeepEval benchmark evaluations will stream here in Phase 8.
        </p>
      </div>
    </div>
  );
}
