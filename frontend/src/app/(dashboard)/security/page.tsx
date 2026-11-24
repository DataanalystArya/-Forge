"use client";

import React from "react";
import { ShieldAlert, ShieldCheck, Lock, AlertTriangle, FileText } from "lucide-react";

export default function SecurityCenterPage() {
  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Security Audit Center</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Static analysis, secret leak detection, and Semgrep security rule verification
          </p>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-amber-950/40 border border-amber-800/40 text-amber-300 text-xs font-mono">
          <ShieldAlert className="w-3.5 h-3.5 text-amber-400" />
          <span>SEMGREP ENGINE READY</span>
        </div>
      </div>

      <div className="p-12 rounded-2xl bg-[#111827] border border-border/80 text-center">
        <Lock className="w-10 h-10 mx-auto text-muted-foreground/40 mb-3" />
        <h3 className="text-base font-bold text-white mb-1">No Security Vulnerabilities Recorded</h3>
        <p className="text-xs text-muted-foreground max-w-md mx-auto">
          Security audits are executed automatically by the Security Audit Agent during repository ingestion and patch review.
        </p>
      </div>
    </div>
  );
}
