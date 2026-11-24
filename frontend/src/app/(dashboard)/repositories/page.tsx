"use client";

import React, { useEffect, useState } from "react";
import {
  FolderGit2,
  Plus,
  GitBranch,
  Search,
  ExternalLink,
  Trash2,
  AlertCircle,
  CheckCircle2,
  Clock,
  Layers,
  FileCode,
} from "lucide-react";
import { fetchWithAuth } from "@/lib/utils";

interface RepositoryItem {
  id: string;
  full_name: string;
  description?: string;
  default_branch: string;
  is_private: boolean;
  status: string;
  total_files: number;
  total_lines: number;
  created_at: string;
}

export default function RepositoriesPage() {
  const [repos, setRepos] = useState<RepositoryItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newRepoName, setNewRepoName] = useState("");
  const [newRepoDesc, setNewRepoDesc] = useState("");
  const [newRepoBranch, setNewRepoBranch] = useState("main");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadRepositories = async () => {
    try {
      setIsLoading(true);
      const res = await fetchWithAuth("/repositories");
      if (res.ok) {
        const data = await res.json();
        setRepos(data.items || []);
      }
    } catch (err) {
      console.error("Failed to load repositories:", err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadRepositories();
  }, []);

  const handleCreateRepo = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      const res = await fetchWithAuth("/repositories", {
        method: "POST",
        body: JSON.stringify({
          full_name: newRepoName.trim(),
          description: newRepoDesc.trim() || undefined,
          default_branch: newRepoBranch.trim() || "main",
          is_private: false,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to register repository.");
      }

      setIsModalOpen(false);
      setNewRepoName("");
      setNewRepoDesc("");
      loadRepositories();
    } catch (err: any) {
      setError(err.message || "An error occurred.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeleteRepo = async (id: string, name: string) => {
    if (!confirm(`Are you sure you want to delete ${name}?`)) return;
    try {
      const res = await fetchWithAuth(`/repositories/${id}`, {
        method: "DELETE",
      });
      if (res.ok) {
        setRepos((prev) => prev.filter((r) => r.id !== id));
      }
    } catch (err) {
      console.error("Failed to delete repository:", err);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Repository Explorer</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Manage repositories ingested for AST structural analysis, Code RAG, and knowledge graph extraction
          </p>
        </div>

        <button
          onClick={() => setIsModalOpen(true)}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium shadow-md shadow-violet-900/30 transition-all"
        >
          <Plus className="w-4 h-4" />
          <span>Register Repository</span>
        </button>
      </div>

      {/* Repositories List */}
      {isLoading ? (
        <div className="p-12 text-center text-muted-foreground font-mono">
          Loading repository index from database...
        </div>
      ) : repos.length === 0 ? (
        <div className="p-12 rounded-2xl bg-[#111827] border border-border/80 text-center max-w-lg mx-auto my-12">
          <FolderGit2 className="w-12 h-12 mx-auto text-muted-foreground/50 mb-4" />
          <h3 className="text-lg font-bold text-white mb-1">No Repositories Connected</h3>
          <p className="text-sm text-muted-foreground mb-6">
            Register your first GitHub repository or local codebase to enable Code RAG and multi-agent debugging.
          </p>
          <button
            onClick={() => setIsModalOpen(true)}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium transition-all"
          >
            <Plus className="w-4 h-4" />
            <span>Connect Repository</span>
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {repos.map((repo) => (
            <div
              key={repo.id}
              className="p-5 rounded-2xl bg-[#111827] border border-border/80 flex flex-col justify-between hover:border-violet-500/40 transition-colors shadow-sm"
            >
              <div>
                <div className="flex items-start justify-between gap-2 mb-3">
                  <div className="flex items-center gap-2 text-white font-bold text-base">
                    <FolderGit2 className="w-5 h-5 text-violet-400 shrink-0" />
                    <span className="truncate">{repo.full_name}</span>
                  </div>
                  <button
                    onClick={() => handleDeleteRepo(repo.id, repo.full_name)}
                    className="text-muted-foreground hover:text-rose-400 p-1 rounded transition-colors"
                    title="Delete Repository"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>

                <p className="text-xs text-muted-foreground line-clamp-2 mb-4">
                  {repo.description || "No description provided."}
                </p>

                <div className="flex items-center gap-3 text-xs font-mono text-muted-foreground mb-4">
                  <span className="flex items-center gap-1">
                    <GitBranch className="w-3.5 h-3.5 text-cyan-400" />
                    {repo.default_branch}
                  </span>
                  <span>&bull;</span>
                  <span>{repo.is_private ? "Private" : "Public"}</span>
                  <span>&bull;</span>
                  <span className="text-emerald-400 font-semibold">{repo.status}</span>
                </div>
              </div>

              <div className="pt-4 border-t border-border flex items-center justify-between text-xs font-mono text-muted-foreground">
                <span className="flex items-center gap-1">
                  <FileCode className="w-3.5 h-3.5" />
                  {repo.total_files} Files
                </span>
                <span className="text-violet-400 hover:text-violet-300 font-sans cursor-pointer font-medium">
                  Inspect AST &rarr;
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Ingestion Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#111827] border border-border rounded-2xl p-6 w-full max-w-lg shadow-2xl">
            <h3 className="text-xl font-bold text-white mb-2">Connect New Repository</h3>
            <p className="text-xs text-muted-foreground mb-6">
              Enter repository details to initiate structural parsing and AST chunk generation.
            </p>

            {error && (
              <div className="mb-4 p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 flex items-center gap-2 text-xs text-rose-400">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <form onSubmit={handleCreateRepo} className="space-y-4">
              <div>
                <label className="block text-xs font-mono uppercase tracking-wider text-muted-foreground mb-1.5">
                  Repository Name (owner/repo)
                </label>
                <input
                  type="text"
                  required
                  value={newRepoName}
                  onChange={(e) => setNewRepoName(e.target.value)}
                  placeholder="facebook/react"
                  className="w-full bg-[#0A0E17] border border-border rounded-xl px-4 py-2.5 text-sm text-foreground focus:outline-none focus:border-violet-500 font-mono"
                />
              </div>

              <div>
                <label className="block text-xs font-mono uppercase tracking-wider text-muted-foreground mb-1.5">
                  Description
                </label>
                <input
                  type="text"
                  value={newRepoDesc}
                  onChange={(e) => setNewRepoDesc(e.target.value)}
                  placeholder="Primary user-facing web library"
                  className="w-full bg-[#0A0E17] border border-border rounded-xl px-4 py-2.5 text-sm text-foreground focus:outline-none focus:border-violet-500"
                />
              </div>

              <div>
                <label className="block text-xs font-mono uppercase tracking-wider text-muted-foreground mb-1.5">
                  Default Branch
                </label>
                <input
                  type="text"
                  value={newRepoBranch}
                  onChange={(e) => setNewRepoBranch(e.target.value)}
                  placeholder="main"
                  className="w-full bg-[#0A0E17] border border-border rounded-xl px-4 py-2.5 text-sm text-foreground focus:outline-none focus:border-violet-500 font-mono"
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-4 border-t border-border mt-6">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 text-sm text-muted-foreground hover:text-white transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-5 py-2.5 bg-violet-600 hover:bg-violet-500 text-white rounded-xl text-sm font-medium transition-all shadow-md shadow-violet-900/30 disabled:opacity-50"
                >
                  {isSubmitting ? "Registering..." : "Register Repository"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
