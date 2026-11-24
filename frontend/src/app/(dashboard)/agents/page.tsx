"use client";

import React from "react";
import {
  Bot,
  BrainCircuit,
  FileSearch,
  Bug,
  ShieldCheck,
  Code2,
  CheckCircle2,
  FileCheck,
  Wrench,
  Activity,
  Terminal,
} from "lucide-react";

const AGENT_SPECIFICATIONS = [
  {
    id: "planner",
    name: "1. Planner Agent",
    icon: BrainCircuit,
    color: "text-violet-400",
    bgColor: "bg-violet-950/40 border-violet-800/40",
    role: "Task Decomposition & Workflow Sequencing",
    input: "Developer Request, Issue description, Stack trace",
    output: "ExecutionPlan (Subtasks, DAG dependencies, Expected outcome)",
    guardrail: "Deterministic acyclic execution plan; rejects ill-formed goals",
    status: "READY",
  },
  {
    id: "repo_analyst",
    name: "2. Repository Analysis Agent",
    icon: FileSearch,
    color: "text-cyan-400",
    bgColor: "bg-cyan-950/40 border-cyan-800/40",
    role: "Codebase Architecture & Dependency Profiling",
    input: "Raw directory structure, AST symbols, Package manifests",
    output: "RepositorySummary (Frameworks, Entry points, Module map)",
    guardrail: "Read-only access; parses package specs and AST trees",
    status: "READY",
  },
  {
    id: "bug_detector",
    name: "3. Bug Detection Agent",
    icon: Bug,
    color: "text-rose-400",
    bgColor: "bg-rose-950/40 border-rose-800/40",
    role: "Root Cause Investigation & Error Tracing",
    input: "Error logs, Stack traces, Code RAG retrieved context",
    output: "BugReport (Confidence, File references, Line boundaries, Evidence)",
    guardrail: "Separates confirmed bugs from hypotheses; verifies line numbers",
    status: "READY",
  },
  {
    id: "security_auditor",
    name: "4. Security Audit Agent",
    icon: ShieldCheck,
    color: "text-amber-400",
    bgColor: "bg-amber-950/40 border-amber-800/40",
    role: "Vulnerability & Secret Scanning",
    input: "Target source files, Semgrep rule configurations",
    output: "SecurityAuditReport (CWE tags, Severity rating, Remediation)",
    guardrail: "Explicitly states static limitations; disallows hallucinated CVEs",
    status: "READY",
  },
  {
    id: "coder",
    name: "5. Coding Agent",
    icon: Code2,
    color: "text-indigo-400",
    bgColor: "bg-indigo-950/40 border-indigo-800/40",
    role: "Context-Aware Patch Synthesis",
    input: "Task specification, Target files, Surrounding AST dependencies",
    output: "ProposedPatch (Unified diff, Impacted symbols, Rationale)",
    guardrail: "Minimizes diff blast radius; adheres strictly to project style",
    status: "READY",
  },
  {
    id: "tester",
    name: "6. Testing Agent",
    icon: CheckCircle2,
    color: "text-emerald-400",
    bgColor: "bg-emerald-950/40 border-emerald-800/40",
    role: "Isolated Automated Test Execution",
    input: "Sandbox workspace, Generated patch diff, Test suite",
    output: "TestExecutionReport (Exit code, Passed/Failed count, Captured stdout)",
    guardrail: "Executes inside isolated container without network or root access",
    status: "READY",
  },
  {
    id: "reviewer",
    name: "7. Code Review Agent",
    icon: FileCheck,
    color: "text-blue-400",
    bgColor: "bg-blue-950/40 border-blue-800/40",
    role: "Independent Regression & Quality Verification",
    input: "Unified diff, Original source AST, Sandbox test outputs",
    output: "ReviewReport (Approval verdict, Performance risks, Style comments)",
    guardrail: "Evaluates maintainability and security implications before delivery",
    status: "READY",
  },
  {
    id: "self_repair",
    name: "8. Self-Repair Agent",
    icon: Wrench,
    color: "text-orange-400",
    bgColor: "bg-orange-950/40 border-orange-800/40",
    role: "Closed-Loop Error Correction",
    input: "Sandbox failure logs, Prior patch history, Diagnostic context",
    output: "RepairAction (Revised patch prompt for Coder or Termination)",
    guardrail: "Bounded retry limit (max 3); stops execution thrashing",
    status: "READY",
  },
];

export default function AgentControlCenterPage() {
  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Agent Control Center</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Registry and state inspection for the 8 specialized agents comprising the LangGraph orchestration engine
          </p>
        </div>

        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-950/40 border border-emerald-800/40 text-emerald-300 text-xs font-mono">
          <Activity className="w-3.5 h-3.5 text-emerald-400 animate-pulse" />
          <span>ALL AGENTS REGISTERED</span>
        </div>
      </div>

      {/* Agents Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {AGENT_SPECIFICATIONS.map((agent) => {
          const Icon = agent.icon;
          return (
            <div
              key={agent.id}
              className="p-6 rounded-2xl bg-[#111827] border border-border/80 flex flex-col justify-between hover:border-violet-500/40 transition-colors shadow-sm"
            >
              <div>
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className={`w-10 h-10 rounded-xl flex items-center justify-center border ${agent.bgColor}`}>
                      <Icon className={`w-5 h-5 ${agent.color}`} />
                    </div>
                    <div>
                      <h3 className="text-base font-bold text-white leading-tight">{agent.name}</h3>
                      <span className="text-xs text-muted-foreground">{agent.role}</span>
                    </div>
                  </div>

                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950/60 text-emerald-300 border border-emerald-800/40">
                    {agent.status}
                  </span>
                </div>

                <div className="space-y-2.5 text-xs font-mono mb-4 pt-3 border-t border-border/60">
                  <div>
                    <span className="text-cyan-400 font-semibold">INPUT: </span>
                    <span className="text-muted-foreground">{agent.input}</span>
                  </div>
                  <div>
                    <span className="text-violet-400 font-semibold">OUTPUT: </span>
                    <span className="text-muted-foreground">{agent.output}</span>
                  </div>
                  <div>
                    <span className="text-amber-400 font-semibold">GUARDRAIL: </span>
                    <span className="text-muted-foreground">{agent.guardrail}</span>
                  </div>
                </div>
              </div>

              <div className="pt-3 border-t border-border/60 flex items-center justify-between text-xs font-mono text-muted-foreground">
                <span>Orchestrator: LangGraph State Machine</span>
                <span className="text-cyan-400">Pydantic Enforced</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
