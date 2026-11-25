"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  FolderGit2,
  Bug,
  GitPullRequest,
  CheckCircle2,
  Plus,
  ArrowUpRight,
  Clock,
  Terminal,
  Activity,
  Shield,
  Layers,
} from "lucide-react";
import { fetchWithAuth } from "@/lib/utils";

interface DashboardStats {
  total_repositories: number;
  total_sessions: number;
  active_sessions: number;
  total_tests_passed: number;
  total_tests_failed: number;
  test_pass_rate: number;
  total_pull_requests: number;
  recent_sessions: Array<{
    id: string;
    title: string;
    status: string;
    current_phase: string;
    repository_id: string;
    created_at: string | null;
  }>;
}

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const loadStats = async () => {
    try {
      const res = await fetchWithAuth("/dashboard/stats");
      if (res.ok) {
        const data = await res.json();
        setStats(data);
      }
    } catch (e) {
      console.error("Failed to load dashboard statistics:", e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadStats();
  }, []);

  return (
    <div className="space-y-8">
      {/* Title & Quick Action */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Engineering Control Center</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Real-time status of connected repositories, agentic workflows, and self-repair cycles
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Link
            href="/repositories"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium transition-all shadow-md shadow-violet-900/30"
          >
            <Plus className="w-4 h-4" />
            <span>Connect Repository</span>
          </Link>
        </div>
      </div>

      {/* KPI Cards Strip */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-5 rounded-2xl bg-[#111827] border border-border/80">
          <div className="flex items-center justify-between text-muted-foreground mb-3">
            <span className="text-xs font-mono uppercase tracking-wider">Repositories</span>
            <FolderGit2 className="w-4 h-4 text-violet-400" />
          </div>
          <div className="text-3xl font-extrabold text-white font-mono">
            {isLoading ? "..." : stats?.total_repositories ?? 0}
          </div>
          <div className="text-xs text-muted-foreground mt-2 flex items-center gap-1">
            <span>Registered in database</span>
          </div>
        </div>

        <Link
          href="/debugging"
          className="p-5 rounded-2xl bg-[#111827] border border-border/80 hover:border-cyan-500/50 transition-all cursor-pointer block group"
        >
          <div className="flex items-center justify-between text-muted-foreground group-hover:text-cyan-300 mb-3">
            <span className="text-xs font-mono uppercase tracking-wider">Active Debugging</span>
            <Bug className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="text-3xl font-extrabold text-white font-mono">
            {isLoading ? "..." : stats?.active_sessions ?? 0}
          </div>
          <div className="text-xs text-cyan-400 mt-2 flex items-center justify-between">
            <span>In-flight agent tasks</span>
            <ArrowUpRight className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity" />
          </div>
        </Link>

        <div className="p-5 rounded-2xl bg-[#111827] border border-border/80">
          <div className="flex items-center justify-between text-muted-foreground mb-3">
            <span className="text-xs font-mono uppercase tracking-wider">Test Pass Rate</span>
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-3xl font-extrabold text-white font-mono">
            {isLoading ? "..." : `${stats?.test_pass_rate ?? 0}%`}
          </div>
          <div className="text-xs text-muted-foreground mt-2 flex items-center gap-1">
            <span>Verified in sandbox</span>
          </div>
        </div>

        <div className="p-5 rounded-2xl bg-[#111827] border border-border/80">
          <div className="flex items-center justify-between text-muted-foreground mb-3">
            <span className="text-xs font-mono uppercase tracking-wider">Pull Requests</span>
            <GitPullRequest className="w-4 h-4 text-violet-400" />
          </div>
          <div className="text-3xl font-extrabold text-white font-mono">
            {isLoading ? "..." : stats?.total_pull_requests ?? 0}
          </div>
          <div className="text-xs text-muted-foreground mt-2 flex items-center gap-1">
            <span>Approved deliveries</span>
          </div>
        </div>
      </div>

      {/* Main Grid: Architecture / Agent Pipeline & Recent Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Agent Orchestration Pipeline Overview */}
        <div className="lg:col-span-2 p-6 rounded-2xl bg-[#111827] border border-border/80 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <Activity className="w-5 h-5 text-cyan-400" />
                <span>Autonomous Agent Pipeline</span>
              </h2>
              <span className="text-xs font-mono px-2.5 py-1 rounded-full bg-violet-950/60 text-violet-300 border border-violet-800/40">
                LangGraph State Machine
              </span>
            </div>
            <p className="text-sm text-muted-foreground mb-6">
              The continuous multi-agent cycle executes upon each task trigger, coordinating through structured Pydantic state checkpoints:
            </p>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
              {[
                { name: "1. Planner", role: "Task DAG", status: "Active" },
                { name: "2. Repo Analyst", role: "AST & Arch", status: "Active" },
                { name: "3. Bug Detector", role: "Root Cause", status: "Active" },
                { name: "4. Security Audit", role: "Semgrep", status: "Active" },
                { name: "5. Coding Agent", role: "Patch Diff", status: "Active" },
                { name: "6. Testing Agent", role: "Pytest Box", status: "Active" },
                { name: "7. Code Review", role: "Sanity Gate", status: "Active" },
                { name: "8. Self-Repair", role: "Auto Fix", status: "Active" },
              ].map((agent) => (
                <div key={agent.name} className="p-3 rounded-xl bg-[#0A0E17] border border-border">
                  <div className="flex items-center justify-between mb-1">
                    <span className="w-2 h-2 rounded-full bg-emerald-400" />
                    <span className="text-[10px] font-mono text-cyan-400 uppercase">{agent.status}</span>
                  </div>
                  <div className="text-xs font-bold text-white">{agent.name}</div>
                  <div className="text-[11px] text-muted-foreground font-mono">{agent.role}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="pt-4 border-t border-border flex items-center justify-between text-xs text-muted-foreground font-mono">
            <span>Defensive Sandbox: Isolated Non-Root Container</span>
            <Link href="/agents" className="text-violet-400 hover:text-violet-300 flex items-center gap-1 font-sans font-medium">
              <span>View Control Center</span>
              <ArrowUpRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        </div>

        {/* Recent Debugging Sessions */}
        <div className="p-6 rounded-2xl bg-[#111827] border border-border/80 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <Clock className="w-5 h-5 text-violet-400" />
                <span>Recent Sessions</span>
              </h2>
              <Link href="/debugging" className="text-xs font-mono text-cyan-400 hover:underline flex items-center gap-1">
                <span>View All</span>
                <ArrowUpRight className="w-3 h-3" />
              </Link>
            </div>

            {stats?.recent_sessions && stats.recent_sessions.length > 0 ? (
              <div className="space-y-3">
                {stats.recent_sessions.map((s) => (
                  <Link
                    key={s.id}
                    href="/debugging"
                    className="p-3 rounded-xl bg-[#0A0E17] border border-border hover:border-violet-500/50 transition-all block group"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-white truncate max-w-[180px] group-hover:text-violet-300 transition-colors">
                        {s.title}
                      </span>
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-violet-950 text-violet-300 border border-violet-800">
                        {s.current_phase}
                      </span>
                    </div>
                    <div className="text-[11px] text-muted-foreground font-mono mt-1 flex items-center justify-between">
                      <span>Status: {s.status}</span>
                      <span className="text-[10px] text-cyan-400 opacity-0 group-hover:opacity-100 transition-opacity">Open &rarr;</span>
                    </div>
                  </Link>
                ))}
              </div>
            ) : (
              <div className="py-12 text-center text-muted-foreground">
                <Terminal className="w-8 h-8 mx-auto text-muted-foreground/40 mb-2" />
                <p className="text-sm">No debugging sessions recorded yet.</p>
                <p className="text-xs text-muted-foreground/80 mt-1">
                  Connect a repository to initiate an automated session.
                </p>
              </div>
            )}
          </div>

          <Link
            href="/repositories"
            className="w-full mt-4 py-2.5 px-3 rounded-xl bg-[#1E293B] hover:bg-[#334155] text-xs font-medium text-white text-center transition-colors block"
          >
            Manage Repositories
          </Link>
        </div>
      </div>
    </div>
  );
}
