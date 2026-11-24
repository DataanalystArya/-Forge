"use client";

import React, { useState } from "react";
import {
  Settings,
  Key,
  Cpu,
  Github,
  Database,
  Shield,
  Save,
  CheckCircle2,
} from "lucide-react";

export default function SettingsPage() {
  const [modelProvider, setModelProvider] = useState("openai");
  const [modelName, setModelName] = useState("gpt-4o");
  const [sandboxTimeout, setSandboxTimeout] = useState(60);
  const [maxRetries, setMaxRetries] = useState(3);
  const [saved, setSaved] = useState(false);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  };

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Top Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Platform Settings</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Configure agentic execution models, isolated sandbox parameters, and integration endpoints
          </p>
        </div>

        {saved && (
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-950/60 border border-emerald-800 text-emerald-300 text-xs font-mono">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span>Preferences Saved</span>
          </div>
        )}
      </div>

      <form onSubmit={handleSave} className="space-y-6">
        {/* Model Configuration */}
        <div className="p-6 rounded-2xl bg-[#111827] border border-border/80 space-y-4">
          <div className="flex items-center gap-2 text-white font-bold text-base">
            <Cpu className="w-5 h-5 text-violet-400" />
            <span>Model Orchestration & LLM Gateway</span>
          </div>
          <p className="text-xs text-muted-foreground">
            Configure the primary model used by the Planner, Coding, and Reviewer agents.
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
            <div>
              <label className="block text-xs font-mono uppercase tracking-wider text-muted-foreground mb-1.5">
                Provider
              </label>
              <select
                value={modelProvider}
                onChange={(e) => setModelProvider(e.target.value)}
                className="w-full bg-[#0A0E17] border border-border rounded-xl px-4 py-2.5 text-sm text-foreground focus:outline-none focus:border-violet-500 font-mono"
              >
                <option value="openai">OpenAI API (Primary)</option>
                <option value="anthropic">Anthropic Claude (Future)</option>
                <option value="gemini">Google Gemini (Future)</option>
                <option value="ollama">Local Ollama / vLLM (Future)</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-mono uppercase tracking-wider text-muted-foreground mb-1.5">
                Model Name
              </label>
              <input
                type="text"
                value={modelName}
                onChange={(e) => setModelName(e.target.value)}
                className="w-full bg-[#0A0E17] border border-border rounded-xl px-4 py-2.5 text-sm text-foreground focus:outline-none focus:border-violet-500 font-mono"
              />
            </div>
          </div>
        </div>

        {/* Execution & Sandbox Parameters */}
        <div className="p-6 rounded-2xl bg-[#111827] border border-border/80 space-y-4">
          <div className="flex items-center gap-2 text-white font-bold text-base">
            <Shield className="w-5 h-5 text-cyan-400" />
            <span>Sandbox Execution & Self-Repair Bounds</span>
          </div>
          <p className="text-xs text-muted-foreground">
            Defensive execution limits applied to isolated container runs and iterative repair cycles.
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
            <div>
              <label className="block text-xs font-mono uppercase tracking-wider text-muted-foreground mb-1.5">
                Execution Timeout (Seconds)
              </label>
              <input
                type="number"
                min={10}
                max={300}
                value={sandboxTimeout}
                onChange={(e) => setSandboxTimeout(Number(e.target.value))}
                className="w-full bg-[#0A0E17] border border-border rounded-xl px-4 py-2.5 text-sm text-foreground focus:outline-none focus:border-violet-500 font-mono"
              />
            </div>

            <div>
              <label className="block text-xs font-mono uppercase tracking-wider text-muted-foreground mb-1.5">
                Max Self-Repair Iterations
              </label>
              <input
                type="number"
                min={1}
                max={5}
                value={maxRetries}
                onChange={(e) => setMaxRetries(Number(e.target.value))}
                className="w-full bg-[#0A0E17] border border-border rounded-xl px-4 py-2.5 text-sm text-foreground focus:outline-none focus:border-violet-500 font-mono"
              />
            </div>
          </div>
        </div>

        {/* Infrastructure & Knowledge Stores */}
        <div className="p-6 rounded-2xl bg-[#111827] border border-border/80 space-y-4">
          <div className="flex items-center gap-2 text-white font-bold text-base">
            <Database className="w-5 h-5 text-emerald-400" />
            <span>Infrastructure Connectivity</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs font-mono pt-2">
            <div className="p-3 rounded-xl bg-[#0A0E17] border border-border">
              <div className="text-muted-foreground mb-1">Database</div>
              <div className="text-emerald-400 font-semibold">PostgreSQL / SQLite</div>
            </div>
            <div className="p-3 rounded-xl bg-[#0A0E17] border border-border">
              <div className="text-muted-foreground mb-1">Vector DB</div>
              <div className="text-cyan-400 font-semibold">Qdrant (:6333)</div>
            </div>
            <div className="p-3 rounded-xl bg-[#0A0E17] border border-border">
              <div className="text-muted-foreground mb-1">Knowledge Graph</div>
              <div className="text-violet-400 font-semibold">Neo4j (:7687)</div>
            </div>
          </div>
        </div>

        <div className="flex justify-end">
          <button
            type="submit"
            className="inline-flex items-center gap-2 px-6 py-2.5 rounded-xl bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium transition-all shadow-md shadow-violet-900/30"
          >
            <Save className="w-4 h-4" />
            <span>Save Settings</span>
          </button>
        </div>
      </form>
    </div>
  );
}
