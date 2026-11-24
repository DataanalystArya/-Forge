"use client";

import React, { useState } from "react";
import { Search, Code2, FileText, Database, Sparkles } from "lucide-react";

export default function CodeSearchPage() {
  const [query, setQuery] = useState("");

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Code Intelligence & Hybrid RAG</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Natural language and exact symbol search powered by Tree-sitter AST, Qdrant dense embeddings, and BM25
          </p>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-cyan-950/40 border border-cyan-800/40 text-cyan-300 text-xs font-mono">
          <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
          <span>PHASE 3 RAG READY</span>
        </div>
      </div>

      <div className="p-6 rounded-2xl bg-[#111827] border border-border/80">
        <div className="relative">
          <Search className="w-5 h-5 text-muted-foreground absolute left-4 top-3.5" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search symbols, functions, or ask: 'Where is user authentication token refreshed?'"
            className="w-full bg-[#0A0E17] border border-border rounded-xl pl-12 pr-4 py-3 text-sm text-foreground focus:outline-none focus:border-violet-500 font-mono"
          />
        </div>
        <div className="flex items-center gap-4 text-xs font-mono text-muted-foreground mt-3 px-1">
          <span>Search Modes: Dense Vector (Cosine) &bull; Sparse BM25 &bull; Cross-Encoder Rerank</span>
        </div>
      </div>

      <div className="p-12 rounded-2xl bg-[#111827] border border-border/80 text-center">
        <Database className="w-10 h-10 mx-auto text-muted-foreground/40 mb-3" />
        <h3 className="text-base font-bold text-white mb-1">Index a Repository to Enable Code RAG</h3>
        <p className="text-xs text-muted-foreground max-w-md mx-auto">
          Once a repository is ingested in Phase 2 & 3, AST chunks, function symbols, and semantic embeddings will populate here.
        </p>
      </div>
    </div>
  );
}
