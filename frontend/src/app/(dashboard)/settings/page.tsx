"use client";

import React, { useEffect, useState } from "react";
import {
  Key,
  Cpu,
  Github,
  Database,
  Shield,
  Save,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Zap,
} from "lucide-react";
import { fetchWithAuth } from "@/lib/utils";

interface InfraStatus {
  database?: { status: string; backend: string };
  qdrant?: { status: string; mode: string };
  graph?: { status: string; backend: string };
}

const PROVIDER_DEFAULTS: Record<string, { model: string; baseUrl: string }> = {
  openai: { model: "gpt-4o-mini", baseUrl: "" },
  gemini: {
    model: "gemini-2.0-flash",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai/",
  },
  openrouter: { model: "openai/gpt-4o-mini", baseUrl: "https://openrouter.ai/api/v1" },
  ollama: { model: "llama3.2", baseUrl: "http://localhost:11434/v1" },
  custom: { model: "gpt-4o-mini", baseUrl: "" },
};

export default function SettingsPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testingLlm, setTestingLlm] = useState(false);

  const [modelProvider, setModelProvider] = useState("openai");
  const [modelName, setModelName] = useState("gpt-4o-mini");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiKeyMasked, setApiKeyMasked] = useState("");
  const [apiKeySet, setApiKeySet] = useState(false);

  const [githubToken, setGithubToken] = useState("");
  const [githubTokenSet, setGithubTokenSet] = useState(false);
  const [githubUsername, setGithubUsername] = useState<string | null>(null);

  const [sandboxTimeout, setSandboxTimeout] = useState(60);
  const [maxRetries, setMaxRetries] = useState(3);
  const [infra, setInfra] = useState<InfraStatus>({});
  const [llmConfigured, setLlmConfigured] = useState(false);

  const [feedback, setFeedback] = useState<{ text: string; error: boolean } | null>(null);
  const [probeResult, setProbeResult] = useState<{
    ok: boolean;
    message: string;
  } | null>(null);

  useEffect(() => {
    loadSettings();
  }, []);

  async function loadSettings() {
    setLoading(true);
    try {
      const res = await fetchWithAuth("/settings");
      if (res.ok) {
        const d = await res.json();
        setModelProvider(d.llm_provider || "openai");
        setModelName(d.llm_model || "gpt-4o-mini");
        setBaseUrl(d.openai_base_url || "");
        setApiKeySet(Boolean(d.openai_api_key_set));
        setApiKeyMasked(d.openai_api_key_masked || "");
        setGithubTokenSet(Boolean(d.github_token_set));
        setGithubUsername(d.github_username || null);
        setSandboxTimeout(d.sandbox_timeout ?? 60);
        setMaxRetries(d.max_retries ?? 3);
        setInfra(d.infrastructure || {});
        setLlmConfigured(Boolean(d.llm_configured));
      }
    } catch {
      setFeedback({ text: "Failed to load settings from backend.", error: true });
    } finally {
      setLoading(false);
    }
  }

  function handleProviderChange(next: string) {
    setModelProvider(next);
    const preset = PROVIDER_DEFAULTS[next];
    if (preset) {
      setModelName(preset.model);
      setBaseUrl(preset.baseUrl);
    }
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setFeedback(null);
    try {
      const payload: Record<string, unknown> = {
        llm_provider: modelProvider,
        llm_model: modelName,
        openai_base_url: baseUrl,
        sandbox_timeout: sandboxTimeout,
        max_retries: maxRetries,
      };
      if (apiKey.trim()) payload.openai_api_key = apiKey.trim();
      if (githubToken.trim()) payload.github_token = githubToken.trim();

      const res = await fetchWithAuth("/settings", {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        const d = await res.json();
        setApiKey("");
        setGithubToken("");
        setApiKeySet(Boolean(d.openai_api_key_set));
        setApiKeyMasked(d.openai_api_key_masked || "");
        setGithubTokenSet(Boolean(d.github_token_set));
        setLlmConfigured(Boolean(d.llm_configured));
        setInfra(d.infrastructure || {});
        setFeedback({ text: "Settings encrypted & persisted to backend.", error: false });
      } else {
        const err = await res.json().catch(() => ({}));
        setFeedback({ text: err.detail || "Failed to save settings.", error: true });
      }
    } catch (err) {
      setFeedback({ text: `Network error: ${String(err)}`, error: true });
    } finally {
      setSaving(false);
    }
  }

  async function handleTestLlm() {
    setTestingLlm(true);
    setProbeResult(null);
    try {
      const res = await fetchWithAuth("/settings/test-llm", { method: "POST" });
      const d = await res.json();
      if (d.ok) {
        setProbeResult({
          ok: true,
          message: `Connected to ${d.model} (${d.latency_ms}ms, ${d.total_tokens} tokens). Reply: "${d.reply}"`,
        });
      } else {
        setProbeResult({
          ok: false,
          message: d.error || "LLM connection probe failed.",
        });
      }
    } catch (err) {
      setProbeResult({ ok: false, message: `Probe failed: ${String(err)}` });
    } finally {
      setTestingLlm(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground p-8 font-mono">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span>Loading platform settings...</span>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Top Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Platform Settings</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Configure live LLM credentials, GitHub PAT, sandbox parameters, and inspect database connectivity
          </p>
        </div>

        <div
          className={`flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-mono ${
            llmConfigured
              ? "bg-emerald-950/60 border-emerald-800 text-emerald-300"
              : "bg-amber-950/50 border-amber-800 text-amber-300"
          }`}
        >
          {llmConfigured ? (
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          ) : (
            <AlertCircle className="w-4 h-4 text-amber-400" />
          )}
          <span>{llmConfigured ? "LIVE LLM CONFIGURED" : "DETERMINISTIC FALLBACK MODE"}</span>
        </div>
      </div>

      {feedback && (
        <div
          className={`p-3 rounded-xl border text-xs font-mono flex items-center gap-2 ${
            feedback.error
              ? "bg-rose-950/40 border-rose-800 text-rose-300"
              : "bg-emerald-950/40 border-emerald-800 text-emerald-300"
          }`}
        >
          {feedback.error ? <AlertCircle className="w-4 h-4" /> : <CheckCircle2 className="w-4 h-4" />}
          <span>{feedback.text}</span>
        </div>
      )}

      <form onSubmit={handleSave} className="space-y-6">
        {/* Model Configuration */}
        <div className="p-6 rounded-2xl bg-[#111827] border border-border/80 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-white font-bold text-base">
              <Cpu className="w-5 h-5 text-violet-400" />
              <span>Model Orchestration & LLM Gateway</span>
            </div>
            <button
              type="button"
              onClick={handleTestLlm}
              disabled={testingLlm}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#0A0E17] hover:bg-slate-800 border border-border text-xs font-mono text-cyan-300 transition disabled:opacity-50"
            >
              {testingLlm ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
              <span>Test LLM Connection</span>
            </button>
          </div>

          {probeResult && (
            <div
              className={`p-3 rounded-xl border text-xs font-mono ${
                probeResult.ok
                  ? "bg-emerald-950/30 border-emerald-800 text-emerald-300"
                  : "bg-rose-950/30 border-rose-800 text-rose-300"
              }`}
            >
              {probeResult.message}
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
            <div>
              <label className="block text-xs font-mono uppercase tracking-wider text-muted-foreground mb-1.5">
                Provider
              </label>
              <select
                value={modelProvider}
                onChange={(e) => handleProviderChange(e.target.value)}
                className="w-full bg-[#0A0E17] border border-border rounded-xl px-4 py-2.5 text-sm text-foreground focus:outline-none focus:border-violet-500 font-mono"
              >
                <option value="openai">OpenAI API</option>
                <option value="gemini">Google Gemini (OpenAI-compat)</option>
                <option value="openrouter">OpenRouter</option>
                <option value="ollama">Local Ollama (localhost:11434)</option>
                <option value="custom">Custom OpenAI-Compatible</option>
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

            <div>
              <label className="block text-xs font-mono uppercase tracking-wider text-muted-foreground mb-1.5">
                API Key {apiKeySet && <span className="text-emerald-400">({apiKeyMasked})</span>}
              </label>
              <div className="relative">
                <Key className="w-4 h-4 text-muted-foreground absolute left-3.5 top-3" />
                <input
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={apiKeySet ? "Leave blank to keep existing key" : "sk-... or AIza..."}
                  className="w-full bg-[#0A0E17] border border-border rounded-xl pl-10 pr-4 py-2.5 text-sm text-foreground focus:outline-none focus:border-violet-500 font-mono"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-mono uppercase tracking-wider text-muted-foreground mb-1.5">
                Base URL (Optional)
              </label>
              <input
                type="text"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="https://api.openai.com/v1"
                className="w-full bg-[#0A0E17] border border-border rounded-xl px-4 py-2.5 text-sm text-foreground focus:outline-none focus:border-violet-500 font-mono"
              />
            </div>
          </div>
        </div>

        {/* GitHub Integration */}
        <div className="p-6 rounded-2xl bg-[#111827] border border-border/80 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-white font-bold text-base">
              <Github className="w-5 h-5 text-slate-300" />
              <span>GitHub Automation Token (Encrypted at Rest)</span>
            </div>
            {githubTokenSet && (
              <span className="text-xs font-mono text-emerald-400">
                Connected {githubUsername ? `(@${githubUsername})` : ""}
              </span>
            )}
          </div>
          <div>
            <input
              type="password"
              value={githubToken}
              onChange={(e) => setGithubToken(e.target.value)}
              placeholder={
                githubTokenSet
                  ? "GitHub PAT stored securely (enter new token to replace)"
                  : "ghp_... (repo scope required for private repos & draft PRs)"
              }
              className="w-full bg-[#0A0E17] border border-border rounded-xl px-4 py-2.5 text-sm text-foreground focus:outline-none focus:border-violet-500 font-mono"
            />
          </div>
        </div>

        {/* Execution & Sandbox Parameters */}
        <div className="p-6 rounded-2xl bg-[#111827] border border-border/80 space-y-4">
          <div className="flex items-center gap-2 text-white font-bold text-base">
            <Shield className="w-5 h-5 text-cyan-400" />
            <span>Sandbox Execution & Self-Repair Bounds</span>
          </div>

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
            <span>Live Infrastructure Connectivity</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs font-mono pt-2">
            <div className="p-3 rounded-xl bg-[#0A0E17] border border-border">
              <div className="text-muted-foreground mb-1">Relational DB</div>
              <div className="text-emerald-400 font-semibold uppercase">
                {infra.database?.backend || "sqlite"} ({infra.database?.status || "connected"})
              </div>
            </div>
            <div className="p-3 rounded-xl bg-[#0A0E17] border border-border">
              <div className="text-muted-foreground mb-1">Qdrant Vector Store</div>
              <div className="text-cyan-400 font-semibold uppercase">
                {infra.qdrant?.mode || "local_disk"} ({infra.qdrant?.status || "connected"})
              </div>
            </div>
            <div className="p-3 rounded-xl bg-[#0A0E17] border border-border">
              <div className="text-muted-foreground mb-1">Knowledge Graph</div>
              <div className="text-violet-400 font-semibold uppercase">
                {infra.graph?.backend || "networkx_disk"} ({infra.graph?.status || "connected"})
              </div>
            </div>
          </div>
        </div>

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={saving}
            className="inline-flex items-center gap-2 px-6 py-2.5 rounded-xl bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white text-sm font-medium transition-all shadow-md shadow-violet-900/30"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            <span>{saving ? "Saving..." : "Save Settings"}</span>
          </button>
        </div>
      </form>
    </div>
  );
}
