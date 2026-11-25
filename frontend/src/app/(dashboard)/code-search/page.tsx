"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  Clock,
  Code2,
  Database,
  ExternalLink,
  FileCode2,
  Layers,
  Loader2,
  RefreshCw,
  Search,
  Sparkles,
  Zap,
} from "lucide-react";
import { API_BASE_URL, fetchWithAuth } from "@/lib/utils";
import Link from "next/link";

// ─── Types ───────────────────────────────────────────────────────────────────

interface Repository {
  id: string;
  full_name: string;
  status: string;
}

interface IndexStatus {
  run_id: string;
  repository_id: string;
  status: string; // PENDING | RUNNING | COMPLETED | FAILED
  total_files: number;
  processed_files: number;
  total_chunks: number;
  embedded_chunks: number;
  skipped_chunks: number;
  error_message: string | null;
  embedding_model: string | null;
  vector_mode: string | null; // "server" | "memory" | "unavailable"
  qdrant_available: boolean | null;
}

interface SearchResult {
  chunk_id: string;
  repository_id: string;
  file_path: string;
  symbol_name: string | null;
  symbol_type: string;
  start_line: number;
  end_line: number;
  language: string | null;
  chunk_content: string;
  score: number;
  retrieval_method: string;
}

interface SearchResponse {
  query: string;
  method: string;
  results: SearchResult[];
  total: number;
  latency_ms: number;
  qdrant_available: boolean;
  vector_mode: string;
}

type SearchMethod = "hybrid" | "semantic" | "bm25";

// ─── Helpers ─────────────────────────────────────────────────────────────────

function statusColor(s: string) {
  if (s === "COMPLETED") return "text-emerald-400";
  if (s === "RUNNING" || s === "PENDING") return "text-amber-400";
  if (s === "FAILED") return "text-red-400";
  return "text-muted-foreground";
}

function statusIcon(s: string) {
  if (s === "COMPLETED") return <CheckCircle2 className="w-4 h-4 text-emerald-400" />;
  if (s === "RUNNING" || s === "PENDING")
    return <Loader2 className="w-4 h-4 text-amber-400 animate-spin" />;
  if (s === "FAILED") return <AlertCircle className="w-4 h-4 text-red-400" />;
  return <Clock className="w-4 h-4 text-muted-foreground" />;
}

function methodBadge(m: string) {
  if (m === "semantic")
    return (
      <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-violet-900/50 text-violet-300 border border-violet-700/40">
        VECTOR
      </span>
    );
  if (m === "bm25")
    return (
      <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-cyan-900/50 text-cyan-300 border border-cyan-700/40">
        BM25
      </span>
    );
  return (
    <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-indigo-900/50 text-indigo-300 border border-indigo-700/40">
      HYBRID
    </span>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function CodeSearchPage() {
  const [repos, setRepos] = useState<Repository[]>([]);
  const [repoId, setRepoId] = useState<string>("");
  const [repoDropOpen, setRepoDropOpen] = useState(false);

  const [indexStatus, setIndexStatus] = useState<IndexStatus | null>(null);
  const [indexLoading, setIndexLoading] = useState(false);
  const [indexError, setIndexError] = useState<string | null>(null);

  const [query, setQuery] = useState("");
  const [method, setMethod] = useState<SearchMethod>("hybrid");
  const [topK, setTopK] = useState(10);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searchResponse, setSearchResponse] = useState<SearchResponse | null>(null);

  const [expandedChunks, setExpandedChunks] = useState<Set<string>>(new Set());
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Load repositories ────────────────────────────────────────────────────

  useEffect(() => {
    fetchWithAuth(`${API_BASE_URL}/repositories`)
      .then((r) => r.json())
      .then((data) => {
        const list: Repository[] = Array.isArray(data) ? data : (data.items || data.repositories || []);
        setRepos(list);
        if (list.length > 0 && !repoId) setRepoId(list[0].id);
      })
      .catch(() => {});
    return () => {
      if (pollRef.current) clearTimeout(pollRef.current);
    };
  }, []);

  // ── Load index status when repo changes ──────────────────────────────────

  useEffect(() => {
    if (!repoId) return;
    setIndexStatus(null);
    setIndexError(null);
    setSearchResponse(null);
    fetchIndexStatus(repoId);
  }, [repoId]);

  const fetchIndexStatus = useCallback(
    (id: string) => {
      fetchWithAuth(`${API_BASE_URL}/rag/repositories/${id}/status`)
        .then((r) => {
          if (r.ok) return r.json();
          return null;
        })
        .then((data: IndexStatus | null) => {
          if (!data) return;
          setIndexStatus(data);
          // Poll while running
          if (data.status === "RUNNING" || data.status === "PENDING") {
            pollRef.current = setTimeout(() => fetchIndexStatus(id), 2000);
          }
        })
        .catch(() => {});
    },
    []
  );

  // ── Trigger indexing ─────────────────────────────────────────────────────

  const handleIndex = async (force = false) => {
    if (!repoId) return;
    setIndexLoading(true);
    setIndexError(null);
    if (pollRef.current) clearTimeout(pollRef.current);

    try {
      const r = await fetchWithAuth(
        `${API_BASE_URL}/rag/repositories/${repoId}/index`,
        {
          method: "POST",
          body: JSON.stringify({ force }),
        }
      );
      const data = await r.json();
      if (!r.ok) {
        setIndexError(data.detail ?? "Failed to start indexing.");
      } else {
        setIndexStatus(data);
        pollRef.current = setTimeout(() => fetchIndexStatus(repoId), 1500);
      }
    } catch {
      setIndexError("Network error.");
    } finally {
      setIndexLoading(false);
    }
  };

  // ── Search ───────────────────────────────────────────────────────────────

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || !repoId) return;
    setSearching(true);
    setSearchError(null);
    setSearchResponse(null);

    try {
      const r = await fetchWithAuth(`${API_BASE_URL}/rag/search`, {
        method: "POST",
        body: JSON.stringify({
          query: query.trim(),
          repository_id: repoId,
          method,
          top_k: topK,
        }),
      });
      const data = await r.json();
      if (!r.ok) {
        setSearchError(data.detail ?? "Search failed.");
      } else {
        setSearchResponse(data);
      }
    } catch {
      setSearchError("Network error.");
    } finally {
      setSearching(false);
    }
  };

  const selectedRepo = repos.find((r) => r.id === repoId);
  const isIndexed = indexStatus?.status === "COMPLETED";
  const isRunning =
    indexStatus?.status === "RUNNING" || indexStatus?.status === "PENDING";

  // ─────────────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">
            Code Intelligence &amp; Hybrid RAG
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Natural language and symbol search powered by sentence-transformers, Qdrant, and BM25
          </p>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-cyan-950/40 border border-cyan-800/40 text-cyan-300 text-xs font-mono">
          <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
          <span>PHASE 3 RAG</span>
        </div>
      </div>

      {/* Repository Selector + Index Controls */}
      <div className="p-5 rounded-2xl bg-[#111827] border border-border/80 space-y-4">
        <div className="flex flex-col sm:flex-row gap-3">
          {/* Repo dropdown */}
          <div className="relative flex-1">
            <button
              onClick={() => setRepoDropOpen((x) => !x)}
              className="w-full flex items-center justify-between gap-2 px-4 py-2.5 rounded-xl bg-[#0A0E17] border border-border text-sm text-foreground hover:border-violet-500 transition-colors"
            >
              <span className="font-mono truncate">
                {selectedRepo ? selectedRepo.full_name : "Select a repository…"}
              </span>
              <ChevronDown className="w-4 h-4 text-muted-foreground shrink-0" />
            </button>
            {repoDropOpen && (
              <div className="absolute z-20 mt-1 w-full rounded-xl bg-[#111827] border border-border shadow-xl">
                {repos.length === 0 ? (
                  <div className="px-4 py-3 text-sm text-muted-foreground">
                    No repositories found. Add one first.
                  </div>
                ) : (
                  repos.map((repo) => (
                    <button
                      key={repo.id}
                      onClick={() => {
                        setRepoId(repo.id);
                        setRepoDropOpen(false);
                      }}
                      className="w-full text-left px-4 py-2.5 text-sm font-mono hover:bg-violet-900/20 transition-colors first:rounded-t-xl last:rounded-b-xl"
                    >
                      {repo.full_name}
                      <span className="ml-2 text-xs text-muted-foreground">
                        [{repo.status}]
                      </span>
                    </button>
                  ))
                )}
              </div>
            )}
          </div>

          {/* Index button */}
          <button
            onClick={() => handleIndex(false)}
            disabled={!repoId || isRunning || indexLoading}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-violet-600 hover:bg-violet-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors"
          >
            {indexLoading || isRunning ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Zap className="w-4 h-4" />
            )}
            {isRunning ? "Indexing…" : isIndexed ? "Re-Index" : "Index Repository"}
          </button>

          {isIndexed && (
            <button
              onClick={() => handleIndex(true)}
              disabled={isRunning || indexLoading}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#0A0E17] border border-border hover:border-violet-500 disabled:opacity-50 text-sm text-muted-foreground hover:text-white transition-colors"
              title="Force full re-index"
            >
              <RefreshCw className="w-4 h-4" />
              Force
            </button>
          )}
        </div>

        {/* Index Status Badge */}
        {indexStatus && (
          <div className="flex flex-wrap items-center gap-3 text-xs font-mono">
            <span className={`flex items-center gap-1.5 ${statusColor(indexStatus.status)}`}>
              {statusIcon(indexStatus.status)}
              {indexStatus.status}
            </span>
            {indexStatus.status !== "PENDING" && (
              <>
                <span className="text-muted-foreground">
                  {indexStatus.embedded_chunks}/{indexStatus.total_chunks} chunks
                </span>
                {indexStatus.skipped_chunks > 0 && (
                  <span className="text-muted-foreground">
                    {indexStatus.skipped_chunks} unchanged
                  </span>
                )}
                <span className="text-muted-foreground">
                  {indexStatus.total_files} files
                </span>
                {indexStatus.embedding_model && (
                  <span className="px-2 py-0.5 rounded bg-violet-900/30 text-violet-300 border border-violet-700/30">
                    {indexStatus.embedding_model}
                  </span>
                )}
                {indexStatus.vector_mode && (
                  <span
                    className={`px-2 py-0.5 rounded border ${
                      indexStatus.vector_mode === "server"
                        ? "bg-emerald-900/30 text-emerald-300 border-emerald-700/30"
                        : indexStatus.vector_mode === "memory"
                        ? "bg-amber-900/30 text-amber-300 border-amber-700/30"
                        : "bg-red-900/30 text-red-300 border-red-700/30"
                    }`}
                  >
                    qdrant: {indexStatus.vector_mode}
                  </span>
                )}
              </>
            )}
            {/* Running progress bar */}
            {isRunning && indexStatus.total_chunks > 0 && (
              <div className="flex-1 min-w-[120px] h-1.5 bg-[#0A0E17] rounded-full overflow-hidden">
                <div
                  className="h-full bg-violet-500 rounded-full transition-all"
                  style={{
                    width: `${Math.round(
                      (indexStatus.embedded_chunks / indexStatus.total_chunks) * 100
                    )}%`,
                  }}
                />
              </div>
            )}
          </div>
        )}

        {indexError && (
          <p className="text-xs text-red-400 font-mono flex items-center gap-1.5">
            <AlertCircle className="w-3.5 h-3.5" />
            {indexError}
          </p>
        )}
      </div>

      {/* Search Bar */}
      <form onSubmit={handleSearch} className="p-5 rounded-2xl bg-[#111827] border border-border/80 space-y-3">
        <div className="relative">
          <Search className="w-5 h-5 text-muted-foreground absolute left-4 top-3.5" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. 'authentication function' or 'class Calculator'"
            className="w-full bg-[#0A0E17] border border-border rounded-xl pl-12 pr-4 py-3 text-sm text-foreground focus:outline-none focus:border-violet-500 font-mono placeholder:text-muted-foreground/50"
          />
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* Method selector */}
          <div className="flex items-center gap-1 p-1 rounded-lg bg-[#0A0E17] border border-border">
            {(["hybrid", "semantic", "bm25"] as SearchMethod[]).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMethod(m)}
                className={`px-3 py-1 rounded-md text-xs font-mono transition-colors ${
                  method === m
                    ? "bg-violet-600 text-white"
                    : "text-muted-foreground hover:text-white"
                }`}
              >
                {m.toUpperCase()}
              </button>
            ))}
          </div>

          {/* Top-K */}
          <div className="flex items-center gap-2 text-xs font-mono text-muted-foreground">
            <span>top-k:</span>
            <select
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
              className="bg-[#0A0E17] border border-border rounded px-2 py-1 text-foreground text-xs"
            >
              {[5, 10, 20, 30].map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
          </div>

          <button
            type="submit"
            disabled={!query.trim() || !repoId || searching}
            className="ml-auto flex items-center gap-2 px-5 py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors"
          >
            {searching ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Search className="w-4 h-4" />
            )}
            Search
          </button>
        </div>
      </form>

      {/* Search Error */}
      {searchError && (
        <div className="p-4 rounded-xl bg-red-900/20 border border-red-700/40 text-red-300 text-sm font-mono flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          {searchError}
        </div>
      )}

      {/* Search Results */}
      {searchResponse && (
        <div className="space-y-3">
          {/* Meta bar */}
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-mono text-muted-foreground px-1">
            <span>
              {searchResponse.total} result{searchResponse.total !== 1 ? "s" : ""} for{" "}
              <span className="text-white">"{searchResponse.query}"</span>
            </span>
            <div className="flex items-center gap-3">
              {methodBadge(searchResponse.method)}
              <span>{searchResponse.latency_ms.toFixed(1)} ms</span>
              <span
                className={
                  searchResponse.qdrant_available ? "text-emerald-400" : "text-amber-400"
                }
              >
                qdrant: {searchResponse.vector_mode}
              </span>
            </div>
          </div>

          {searchResponse.results.length === 0 ? (
            <div className="p-10 rounded-2xl bg-[#111827] border border-border/80 text-center">
              <FileCode2 className="w-10 h-10 mx-auto text-muted-foreground/30 mb-3" />
              <p className="text-sm text-muted-foreground">
                No chunks matched your query. Try different keywords or index the repository first.
              </p>
            </div>
          ) : (
            searchResponse.results.map((result) => {
              const isExpanded = expandedChunks.has(result.chunk_id);
              const lines = result.chunk_content.split("\n");
              const preview = lines.slice(0, 6).join("\n");
              const hasMore = lines.length > 6;

              return (
                <div
                  key={result.chunk_id}
                  className="rounded-xl bg-[#111827] border border-border/80 overflow-hidden hover:border-violet-500/40 transition-colors"
                >
                  {/* Result header */}
                  <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 border-b border-border/60">
                    <div className="flex items-center gap-2 min-w-0">
                      <Code2 className="w-4 h-4 text-violet-400 shrink-0" />
                      <span className="text-xs font-mono text-violet-300 truncate">
                        {result.file_path}
                      </span>
                      <span className="text-xs text-muted-foreground shrink-0">
                        L{result.start_line}–{result.end_line}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {result.symbol_name && (
                        <span className="px-2 py-0.5 rounded text-xs font-mono bg-[#0A0E17] text-cyan-300 border border-cyan-700/30">
                          {result.symbol_type}: {result.symbol_name}
                        </span>
                      )}
                      {result.language && (
                        <span className="text-xs text-muted-foreground font-mono">
                          {result.language}
                        </span>
                      )}
                      {methodBadge(result.retrieval_method)}
                      <span className="text-xs font-mono text-emerald-400">
                        {(result.score * 100).toFixed(1)}%
                      </span>
                      <Link
                        href={`/repositories/${result.repository_id}?file=${encodeURIComponent(result.file_path)}`}
                        className="text-muted-foreground hover:text-white transition-colors"
                        title="Open in Explorer"
                      >
                        <ExternalLink className="w-3.5 h-3.5" />
                      </Link>
                    </div>
                  </div>

                  {/* Code preview */}
                  <div className="relative">
                    <pre className="p-4 text-xs font-mono text-slate-300 bg-[#0A0E17] overflow-x-auto leading-5 whitespace-pre-wrap">
                      {isExpanded ? result.chunk_content : preview}
                    </pre>
                    {hasMore && (
                      <button
                        onClick={() =>
                          setExpandedChunks((prev) => {
                            const next = new Set(prev);
                            if (isExpanded) next.delete(result.chunk_id);
                            else next.add(result.chunk_id);
                            return next;
                          })
                        }
                        className="w-full py-1.5 text-xs font-mono text-muted-foreground hover:text-white bg-[#111827] border-t border-border/60 transition-colors"
                      >
                        {isExpanded
                          ? "▲ Collapse"
                          : `▼ Show ${lines.length - 6} more lines`}
                      </button>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}

      {/* Empty state */}
      {!searchResponse && !searchError && (
        <div className="p-12 rounded-2xl bg-[#111827] border border-border/80 text-center">
          <Database className="w-10 h-10 mx-auto text-muted-foreground/30 mb-3" />
          <h3 className="text-base font-bold text-white mb-1">
            {!repoId
              ? "Select a Repository"
              : !isIndexed
              ? "Index a Repository to Enable Code RAG"
              : "Enter a Query to Search"}
          </h3>
          <p className="text-xs text-muted-foreground max-w-md mx-auto">
            {!repoId
              ? "Choose a repository from the dropdown above."
              : !isIndexed
              ? 'Click "Index Repository" to chunk and embed your code with sentence-transformers (all-MiniLM-L6-v2).'
              : "Type a natural language question or symbol name and press Search."}
          </p>
          {isIndexed && indexStatus && (
            <div className="mt-4 flex flex-wrap justify-center gap-4 text-xs font-mono text-muted-foreground">
              <span className="flex items-center gap-1">
                <Layers className="w-3.5 h-3.5" />
                {indexStatus.embedded_chunks} chunks indexed
              </span>
              <span className="flex items-center gap-1">
                <FileCode2 className="w-3.5 h-3.5" />
                {indexStatus.total_files} files
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
