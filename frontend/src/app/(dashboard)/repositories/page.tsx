"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
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
  Github,
  Upload,
  Key,
  Shield,
  ArrowRight,
  Download,
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

interface GitHubAccountStatus {
  is_connected: boolean;
  username?: string;
  avatar_url?: string;
  connected_at?: string;
}

interface GitHubRemoteRepo {
  id: number;
  name: string;
  full_name: string;
  description?: string;
  private: boolean;
  clone_url: string;
  default_branch: string;
  language?: string;
}

export default function RepositoriesPage() {
  const router = useRouter();
  const [repos, setRepos] = useState<RepositoryItem[]>([]);
  const [githubStatus, setGithubStatus] = useState<GitHubAccountStatus>({ is_connected: false });
  const [githubRepos, setGithubRepos] = useState<GitHubRemoteRepo[]>([]);
  const [activeTab, setActiveTab] = useState<"ingested" | "github">("ingested");

  const [isLoading, setIsLoading] = useState(true);
  const [isGithubLoading, setIsGithubLoading] = useState(false);

  // Modals
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isPatModalOpen, setIsPatModalOpen] = useState(false);
  const [isZipModalOpen, setIsZipModalOpen] = useState(false);

  // Form states
  const [newRepoName, setNewRepoName] = useState("");
  const [newRepoDesc, setNewRepoDesc] = useState("");
  const [newRepoBranch, setNewRepoBranch] = useState("main");
  const [patToken, setPatToken] = useState("");
  const [zipRepoName, setZipRepoName] = useState("");
  const [selectedZipFile, setSelectedZipFile] = useState<File | null>(null);

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

  const loadGithubStatus = async () => {
    try {
      const res = await fetchWithAuth("/github/status");
      if (res.ok) {
        const data = await res.json();
        setGithubStatus(data);
        if (data.is_connected) {
          loadGithubRepos();
        }
      }
    } catch (err) {
      console.error("Failed to load GitHub status:", err);
    }
  };

  const loadGithubRepos = async () => {
    try {
      setIsGithubLoading(true);
      const res = await fetchWithAuth("/github/repos");
      if (res.ok) {
        const data = await res.json();
        setGithubRepos(data.repositories || []);
      }
    } catch (err) {
      console.error("Failed to load GitHub repos:", err);
    } finally {
      setIsGithubLoading(false);
    }
  };

  useEffect(() => {
    loadRepositories();
    loadGithubStatus();
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

      setIsCreateModalOpen(false);
      setNewRepoName("");
      setNewRepoDesc("");
      loadRepositories();
    } catch (err: any) {
      setError(err.message || "An error occurred.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleConnectPAT = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      const res = await fetchWithAuth("/github/connect-pat", {
        method: "POST",
        body: JSON.stringify({ token: patToken.trim() }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to connect GitHub account.");

      setGithubStatus(data);
      setIsPatModalOpen(false);
      setPatToken("");
      loadGithubRepos();
      setActiveTab("github");
    } catch (err: any) {
      setError(err.message || "Connection failed.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleImportGithubRepo = async (remoteRepo: GitHubRemoteRepo) => {
    try {
      setIsSubmitting(true);
      // 1. Create repository record
      const createRes = await fetchWithAuth("/repositories", {
        method: "POST",
        body: JSON.stringify({
          full_name: remoteRepo.full_name,
          description: remoteRepo.description,
          default_branch: remoteRepo.default_branch,
          is_private: remoteRepo.private,
          clone_url: remoteRepo.clone_url,
        }),
      });
      const repo = await createRes.json();
      if (!createRes.ok) throw new Error(repo.detail || "Failed to register repo.");

      // 2. Trigger Clone & Scan
      const cloneRes = await fetchWithAuth(`/repositories/${repo.id}/clone`, {
        method: "POST",
      });
      if (!cloneRes.ok) {
        const cData = await cloneRes.json();
        throw new Error(cData.detail || "Clone failed.");
      }

      loadRepositories();
      router.push(`/repositories/${repo.id}`);
    } catch (err: any) {
      alert(`Import failed: ${err.message}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleUploadZip = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedZipFile || !zipRepoName) return;
    setError(null);
    setIsSubmitting(true);

    try {
      // 1. Create repo record
      const createRes = await fetchWithAuth("/repositories", {
        method: "POST",
        body: JSON.stringify({
          full_name: zipRepoName.trim(),
          description: "Ingested via local ZIP archive",
          default_branch: "main",
          is_private: false,
        }),
      });
      const repo = await createRes.json();
      if (!createRes.ok) throw new Error(repo.detail || "Failed to register repository.");

      // 2. Upload archive
      const formData = new FormData();
      formData.append("file", selectedZipFile);

      const uploadRes = await fetchWithAuth(`/repositories/${repo.id}/upload-zip`, {
        method: "POST",
        body: formData,
      });

      if (!uploadRes.ok) {
        const uData = await uploadRes.json();
        throw new Error(uData.detail || "ZIP upload failed.");
      }

      setIsZipModalOpen(false);
      setSelectedZipFile(null);
      setZipRepoName("");
      loadRepositories();
      router.push(`/repositories/${repo.id}`);
    } catch (err: any) {
      setError(err.message || "Upload failed.");
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
            Connect GitHub repositories, ingest ZIP archives, and explore source code with Tree-sitter AST analysis
          </p>
        </div>

        <div className="flex items-center gap-3">
          {githubStatus.is_connected ? (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-[#111827] border border-border text-xs font-mono text-muted-foreground">
              <Github className="w-4 h-4 text-white" />
              <span>Connected as <strong className="text-cyan-400">{githubStatus.username}</strong></span>
            </div>
          ) : (
            <button
              onClick={() => setIsPatModalOpen(true)}
              className="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl bg-[#111827] hover:bg-[#1E293B] border border-border text-white text-xs font-medium transition-all"
            >
              <Github className="w-4 h-4" />
              <span>Connect GitHub</span>
            </button>
          )}

          <button
            onClick={() => setIsZipModalOpen(true)}
            className="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl bg-[#111827] hover:bg-[#1E293B] border border-border text-white text-xs font-medium transition-all"
          >
            <Upload className="w-4 h-4 text-cyan-400" />
            <span>Upload ZIP</span>
          </button>

          <button
            onClick={() => setIsCreateModalOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-violet-600 hover:bg-violet-500 text-white text-xs font-medium shadow-md shadow-violet-900/30 transition-all"
          >
            <Plus className="w-4 h-4" />
            <span>Register Repo</span>
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-border/80 gap-6 text-sm font-medium">
        <button
          onClick={() => setActiveTab("ingested")}
          className={`pb-3 transition-colors ${
            activeTab === "ingested"
              ? "border-b-2 border-violet-500 text-white font-bold"
              : "text-muted-foreground hover:text-white"
          }`}
        >
          Ingested Repositories ({repos.length})
        </button>

        <button
          onClick={() => {
            if (!githubStatus.is_connected) {
              setIsPatModalOpen(true);
            } else {
              setActiveTab("github");
            }
          }}
          className={`pb-3 transition-colors flex items-center gap-2 ${
            activeTab === "github"
              ? "border-b-2 border-violet-500 text-white font-bold"
              : "text-muted-foreground hover:text-white"
          }`}
        >
          <Github className="w-4 h-4" />
          <span>GitHub Accessible Repos ({githubRepos.length})</span>
        </button>
      </div>

      {/* Ingested Tab */}
      {activeTab === "ingested" ? (
        isLoading ? (
          <div className="p-12 text-center text-muted-foreground font-mono text-sm">
            Loading repository index from database...
          </div>
        ) : repos.length === 0 ? (
          <div className="p-12 rounded-2xl bg-[#111827] border border-border/80 text-center max-w-lg mx-auto my-12">
            <FolderGit2 className="w-12 h-12 mx-auto text-muted-foreground/50 mb-4" />
            <h3 className="text-lg font-bold text-white mb-1">No Repositories Ingested Yet</h3>
            <p className="text-xs text-muted-foreground mb-6">
              Connect your GitHub account, clone a remote repository, or upload a local ZIP archive to begin code exploration.
            </p>
            <div className="flex items-center justify-center gap-3">
              <button
                onClick={() => setIsPatModalOpen(true)}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-[#1E293B] hover:bg-[#334155] text-white text-xs font-medium"
              >
                <Github className="w-4 h-4" />
                <span>Connect GitHub</span>
              </button>
              <button
                onClick={() => setIsZipModalOpen(true)}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-violet-600 hover:bg-violet-500 text-white text-xs font-medium shadow-md shadow-violet-900/30"
              >
                <Upload className="w-4 h-4" />
                <span>Upload ZIP</span>
              </button>
            </div>
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
                    <div className="flex items-center gap-2 text-white font-bold text-base truncate">
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
                    <span
                      className={`font-semibold ${
                        repo.status === "READY"
                          ? "text-emerald-400"
                          : repo.status === "PARSING"
                          ? "text-amber-400 animate-pulse"
                          : "text-muted-foreground"
                      }`}
                    >
                      {repo.status}
                    </span>
                  </div>
                </div>

                <div className="pt-4 border-t border-border flex items-center justify-between text-xs font-mono text-muted-foreground">
                  <span className="flex items-center gap-1">
                    <FileCode className="w-3.5 h-3.5" />
                    {repo.total_files} Files &bull; {repo.total_lines} Lines
                  </span>
                  <Link
                    href={`/repositories/${repo.id}`}
                    className="text-violet-400 hover:text-violet-300 font-sans font-medium flex items-center gap-1"
                  >
                    <span>Explore Code</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )
      ) : (
        /* GitHub Repositories Tab */
        isGithubLoading ? (
          <div className="p-12 text-center text-muted-foreground font-mono text-sm">
            Fetching repositories from GitHub API...
          </div>
        ) : githubRepos.length === 0 ? (
          <div className="p-12 text-center text-muted-foreground font-mono text-sm">
            No accessible GitHub repositories found.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {githubRepos.map((gr) => (
              <div
                key={gr.id}
                className="p-5 rounded-2xl bg-[#111827] border border-border/80 flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <div className="flex items-center gap-2 text-white font-bold text-sm truncate">
                      <Github className="w-4 h-4 text-cyan-400 shrink-0" />
                      <span className="truncate">{gr.full_name}</span>
                    </div>
                    {gr.private && (
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-violet-950 text-violet-300 border border-violet-800">
                        Private
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground line-clamp-2 mb-4">
                    {gr.description || "No description provided."}
                  </p>
                  <div className="text-xs font-mono text-muted-foreground mb-4">
                    Language: <span className="text-cyan-400">{gr.language || "Unknown"}</span> &bull; Branch: {gr.default_branch}
                  </div>
                </div>

                <div className="pt-3 border-t border-border flex items-center justify-between">
                  <a
                    href={`https://github.com/${gr.full_name}`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs text-muted-foreground hover:text-white flex items-center gap-1 font-mono"
                  >
                    <span>View on GitHub</span>
                    <ExternalLink className="w-3 h-3" />
                  </a>
                  <button
                    onClick={() => handleImportGithubRepo(gr)}
                    disabled={isSubmitting}
                    className="px-3 py-1.5 rounded-lg bg-violet-600 hover:bg-violet-500 text-white text-xs font-medium transition-all shadow-sm"
                  >
                    {isSubmitting ? "Ingesting..." : "Clone & Ingest"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )
      )}

      {/* Modal: Connect GitHub PAT */}
      {isPatModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#111827] border border-border rounded-2xl p-6 w-full max-w-lg shadow-2xl">
            <div className="flex items-center gap-3 mb-2">
              <Github className="w-6 h-6 text-white" />
              <h3 className="text-xl font-bold text-white">Connect GitHub Account</h3>
            </div>
            <p className="text-xs text-muted-foreground mb-4">
              Enter a GitHub Personal Access Token (classic or fine-grained with <code>repo</code> and <code>read:user</code> scopes).
            </p>

            <div className="p-3 mb-4 rounded-xl bg-violet-950/30 border border-violet-800/40 text-xs text-violet-300 flex items-start gap-2">
              <Shield className="w-4 h-4 shrink-0 text-violet-400 mt-0.5" />
              <span>
                Tokens are encrypted with AES-GCM at rest using your system secret key and are never transmitted to frontend clients.
              </span>
            </div>

            {error && (
              <div className="mb-4 p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 flex items-center gap-2 text-xs text-rose-400">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <form onSubmit={handleConnectPAT} className="space-y-4">
              <div>
                <label className="block text-xs font-mono uppercase tracking-wider text-muted-foreground mb-1.5">
                  Personal Access Token (ghp_... or github_pat_...)
                </label>
                <div className="relative">
                  <Key className="w-4 h-4 text-muted-foreground absolute left-3.5 top-3" />
                  <input
                    type="password"
                    required
                    value={patToken}
                    onChange={(e) => setPatToken(e.target.value)}
                    placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
                    className="w-full bg-[#0A0E17] border border-border rounded-xl pl-10 pr-4 py-2.5 text-sm text-foreground focus:outline-none focus:border-violet-500 font-mono"
                  />
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 pt-4 border-t border-border">
                <button
                  type="button"
                  onClick={() => setIsPatModalOpen(false)}
                  className="px-4 py-2 text-sm text-muted-foreground hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-5 py-2.5 bg-violet-600 hover:bg-violet-500 text-white rounded-xl text-sm font-medium transition-all shadow-md shadow-violet-900/30 disabled:opacity-50"
                >
                  {isSubmitting ? "Verifying..." : "Connect Account"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Upload ZIP Archive */}
      {isZipModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#111827] border border-border rounded-2xl p-6 w-full max-w-lg shadow-2xl">
            <div className="flex items-center gap-3 mb-2">
              <Upload className="w-6 h-6 text-cyan-400" />
              <h3 className="text-xl font-bold text-white">Upload Repository Archive</h3>
            </div>
            <p className="text-xs text-muted-foreground mb-4">
              Upload a source code ZIP archive (up to 50 MB compressed). Validated with Zip Slip and symlink guards.
            </p>

            {error && (
              <div className="mb-4 p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 flex items-center gap-2 text-xs text-rose-400">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <form onSubmit={handleUploadZip} className="space-y-4">
              <div>
                <label className="block text-xs font-mono uppercase tracking-wider text-muted-foreground mb-1.5">
                  Repository Identifier (e.g. org/project)
                </label>
                <input
                  type="text"
                  required
                  value={zipRepoName}
                  onChange={(e) => setZipRepoName(e.target.value)}
                  placeholder="local/sample-service"
                  className="w-full bg-[#0A0E17] border border-border rounded-xl px-4 py-2.5 text-sm text-foreground focus:outline-none focus:border-violet-500 font-mono"
                />
              </div>

              <div>
                <label className="block text-xs font-mono uppercase tracking-wider text-muted-foreground mb-1.5">
                  ZIP File
                </label>
                <input
                  type="file"
                  required
                  accept=".zip"
                  onChange={(e) => setSelectedZipFile(e.target.files?.[0] || null)}
                  className="w-full bg-[#0A0E17] border border-border rounded-xl px-4 py-2 text-xs text-muted-foreground file:mr-4 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-mono file:bg-violet-600 file:text-white hover:file:bg-violet-500"
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-4 border-t border-border">
                <button
                  type="button"
                  onClick={() => setIsZipModalOpen(false)}
                  className="px-4 py-2 text-sm text-muted-foreground hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting || !selectedZipFile}
                  className="px-5 py-2.5 bg-violet-600 hover:bg-violet-500 text-white rounded-xl text-sm font-medium transition-all shadow-md shadow-violet-900/30 disabled:opacity-50"
                >
                  {isSubmitting ? "Extracting & Scanning..." : "Upload & Ingest"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Register Repo */}
      {isCreateModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#111827] border border-border rounded-2xl p-6 w-full max-w-lg shadow-2xl">
            <h3 className="text-xl font-bold text-white mb-2">Register Repository</h3>
            <p className="text-xs text-muted-foreground mb-6">
              Enter remote repository details to initiate structural parsing and AST chunk generation.
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
                  onClick={() => setIsCreateModalOpen(false)}
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
