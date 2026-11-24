import React from "react";
import Link from "next/link";
import {
  Flame,
  Bot,
  GitBranch,
  ShieldAlert,
  Terminal,
  Cpu,
  Layers,
  ArrowRight,
  CheckCircle,
  Code2,
} from "lucide-react";

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-[#0A0E17] text-foreground flex flex-col">
      {/* Top Navigation */}
      <nav className="h-20 border-b border-border/60 px-8 flex items-center justify-between max-w-7xl mx-auto w-full">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-600 via-indigo-600 to-cyan-500 flex items-center justify-center shadow-lg shadow-violet-900/40">
            <Flame className="w-6 h-6 text-white" />
          </div>
          <div>
            <span className="font-extrabold text-xl tracking-wider text-white">FORGE</span>
            <span className="text-[10px] block font-mono text-cyan-400 tracking-widest uppercase">Autonomous AI Platform</span>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <Link
            href="/login"
            className="text-sm font-medium text-muted-foreground hover:text-white px-4 py-2 transition-colors"
          >
            Sign In
          </Link>
          <Link
            href="/register"
            className="text-sm font-medium bg-gradient-to-r from-violet-600 to-cyan-600 hover:from-violet-500 hover:to-cyan-500 text-white px-5 py-2.5 rounded-lg shadow-md shadow-violet-900/30 transition-all flex items-center gap-2"
          >
            <span>Launch Platform</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </nav>

      {/* Hero Section */}
      <main className="flex-1 flex flex-col items-center justify-center px-6 py-20 text-center max-w-5xl mx-auto">
        <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-violet-950/50 border border-violet-800/40 text-violet-300 text-xs font-mono uppercase tracking-wider mb-8">
          <Bot className="w-3.5 h-3.5 text-cyan-400" />
          Multi-Agent Code Reasoning & Self-Repair
        </div>

        <h1 className="text-5xl md:text-6xl lg:text-7xl font-extrabold tracking-tight text-white mb-6 leading-tight">
          From Code Understanding to{" "}
          <span className="bg-gradient-to-r from-violet-400 via-indigo-300 to-cyan-400 bg-clip-text text-transparent">
            Autonomous Engineering.
          </span>
        </h1>

        <p className="text-lg md:text-xl text-muted-foreground max-w-3xl mb-10 leading-relaxed">
          FORGE goes beyond simple autocomplete. It ingests entire repositories, builds AST-driven knowledge graphs,
          investigates root causes, executes isolated tests, iteratively repairs code, and delivers verified GitHub Pull Requests.
        </p>

        <div className="flex flex-col sm:flex-row items-center gap-4 mb-20">
          <Link
            href="/register"
            className="w-full sm:w-auto text-base font-semibold bg-violet-600 hover:bg-violet-500 text-white px-8 py-3.5 rounded-xl shadow-lg shadow-violet-900/40 transition-all flex items-center justify-center gap-2"
          >
            <span>Get Started</span>
            <ArrowRight className="w-5 h-5" />
          </Link>
          <Link
            href="/login"
            className="w-full sm:w-auto text-base font-semibold bg-[#111827] hover:bg-[#1F2937] border border-border text-foreground px-8 py-3.5 rounded-xl transition-all"
          >
            Open Dashboard
          </Link>
        </div>

        {/* Cognitive Loop Strip */}
        <div className="w-full bg-[#111827]/80 border border-border/80 rounded-2xl p-6 backdrop-blur-md mb-20">
          <div className="text-xs font-mono text-cyan-400 uppercase tracking-widest text-left mb-4">
            Autonomous Engineering Workflow
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3 text-center">
            {[
              { step: "01", name: "Understand", desc: "Repository AST & Graph" },
              { step: "02", name: "Analyze", desc: "Architecture & Modules" },
              { step: "03", name: "Plan", desc: "DAG Subtask Plan" },
              { step: "04", name: "Code", desc: "Unified Diff Generation" },
              { step: "05", name: "Test", desc: "Isolated Sandbox Run" },
              { step: "06", name: "Repair", desc: "Self-Repair Loop" },
              { step: "07", name: "Review", desc: "Regression & Quality Gate" },
              { step: "08", name: "Deliver", desc: "Human Gated PR" },
            ].map((item) => (
              <div key={item.step} className="p-3 rounded-lg bg-[#0A0E17]/80 border border-border/60">
                <div className="text-[10px] font-mono text-violet-400 mb-1">{item.step}</div>
                <div className="text-sm font-bold text-white mb-0.5">{item.name}</div>
                <div className="text-[11px] text-muted-foreground">{item.desc}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Core Capabilities Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 text-left w-full">
          <div className="p-6 rounded-xl bg-[#111827] border border-border/80">
            <div className="w-10 h-10 rounded-lg bg-violet-950/70 border border-violet-800/40 flex items-center justify-center text-violet-400 mb-4">
              <Code2 className="w-5 h-5" />
            </div>
            <h3 className="text-lg font-bold text-white mb-2">Hybrid Code RAG</h3>
            <p className="text-sm text-muted-foreground">
              Syntactic code chunking powered by Tree-sitter combined with Qdrant dense vectors and Rank-BM25 sparse tokens.
            </p>
          </div>

          <div className="p-6 rounded-xl bg-[#111827] border border-border/80">
            <div className="w-10 h-10 rounded-lg bg-cyan-950/70 border border-cyan-800/40 flex items-center justify-center text-cyan-400 mb-4">
              <Cpu className="w-5 h-5" />
            </div>
            <h3 className="text-lg font-bold text-white mb-2">8-Agent LangGraph</h3>
            <p className="text-sm text-muted-foreground">
              Specialized agents with strict Pydantic contracts: Planner, Analyst, Bug Detector, Security Auditor, Coder, Tester, Reviewer, and Repair.
            </p>
          </div>

          <div className="p-6 rounded-xl bg-[#111827] border border-border/80">
            <div className="w-10 h-10 rounded-lg bg-emerald-950/70 border border-emerald-800/40 flex items-center justify-center text-emerald-400 mb-4">
              <Terminal className="w-5 h-5" />
            </div>
            <h3 className="text-lg font-bold text-white mb-2">Isolated Test Execution</h3>
            <p className="text-sm text-muted-foreground">
              Code is tested inside unprivileged, resource-constrained sandbox environments with real-time log capture and automatic rollback.
            </p>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-border/60 py-8 px-6 text-center text-xs font-mono text-muted-foreground">
        FORGE &bull; Autonomous AI-Powered Software Engineering Platform &bull; Built with LangGraph, FastAPI & Next.js
      </footer>
    </div>
  );
}
