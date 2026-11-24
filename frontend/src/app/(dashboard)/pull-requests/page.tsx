"use client";

import React from "react";
import { GitPullRequest, GitBranch, Check, X, ShieldAlert } from "lucide-react";

export default function PullRequestsPage() {
  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Pull Request Center</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Human-in-the-Loop review gate for proposed commits, branches, and GitHub Pull Requests
          </p>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-violet-950/40 border border-violet-800/40 text-violet-300 text-xs font-mono">
          <GitPullRequest className="w-3.5 h-3.5 text-violet-400" />
          <span>HUMAN APPROVAL REQUIRED</span>
        </div>
      </div>

      <div className="p-12 rounded-2xl bg-[#111827] border border-border/80 text-center">
        <GitBranch className="w-10 h-10 mx-auto text-muted-foreground/40 mb-3" />
        <h3 className="text-base font-bold text-white mb-1">No Pending Pull Requests</h3>
        <p className="text-xs text-muted-foreground max-w-md mx-auto">
          FORGE never merges or creates PRs automatically. When a self-repaired patch passes code review, it awaits your explicit approval here.
        </p>
      </div>
    </div>
  );
}
