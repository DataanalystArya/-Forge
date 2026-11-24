"use client";

import React from "react";
import { CheckCircle2, Play, Terminal, Layers } from "lucide-react";

export default function TestingCenterPage() {
  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Testing Center</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Automated unit, regression, and integration test executions in isolated sandboxes
          </p>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-950/40 border border-emerald-800/40 text-emerald-300 text-xs font-mono">
          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
          <span>DOCKER ISOLATION</span>
        </div>
      </div>

      <div className="p-12 rounded-2xl bg-[#111827] border border-border/80 text-center">
        <Terminal className="w-10 h-10 mx-auto text-muted-foreground/40 mb-3" />
        <h3 className="text-base font-bold text-white mb-1">No Active Sandbox Test Runs</h3>
        <p className="text-xs text-muted-foreground max-w-md mx-auto">
          When the Testing Agent runs tests against generated patches, stdout/stderr streams and exit codes appear in real time here.
        </p>
      </div>
    </div>
  );
}
