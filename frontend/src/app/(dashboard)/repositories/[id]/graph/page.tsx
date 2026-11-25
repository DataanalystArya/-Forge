"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  Node,
  Edge,
  MarkerType,
} from "reactflow";
import "reactflow/dist/style.css";
import {
  ArrowLeft,
  Share2,
  RefreshCw,
  Search,
  Database,
  Layers,
  Sparkles,
  Cpu,
  Info,
} from "lucide-react";
import { fetchWithAuth } from "@/lib/utils";

interface GraphSummary {
  repo_id: string;
  nodes: number;
  edges: number;
  available: boolean;
  backend: string;
  node_labels?: Record<string, number>;
  edge_relations?: Record<string, number>;
}

export default function RepositoryGraphPage() {
  const params = useParams();
  const repoId = params?.id as string;

  const [summary, setSummary] = useState<GraphSummary | null>(null);
  const [symbolQuery, setSymbolQuery] = useState("");
  const [depth, setDepth] = useState(2);
  const [isExtracting, setIsExtracting] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  // Fetch graph summary
  const loadSummary = useCallback(async () => {
    try {
      const res = await fetchWithAuth(`/graph/repositories/${repoId}/summary`);
      if (res.ok) {
        const data = await res.json();
        setSummary(data);
      }
    } catch (err) {
      console.error("Failed to load graph summary", err);
    }
  }, [repoId]);

  useEffect(() => {
    loadSummary();
  }, [loadSummary]);

  // Extract graph
  async function handleExtract() {
    setIsExtracting(true);
    setErrorMsg(null);
    try {
      const res = await fetchWithAuth(`/graph/repositories/${repoId}/extract`, {
        method: "POST",
      });
      if (res.ok) {
        await loadSummary();
        // Load default context
        handleQuerySubgraph("main");
      } else {
        const err = await res.json();
        setErrorMsg(err.detail || "Graph extraction failed");
      }
    } catch (err) {
      setErrorMsg(String(err));
    } finally {
      setIsExtracting(false);
    }
  }

  // Query subgraph
  async function handleQuerySubgraph(symbolToSearch?: string) {
    const sym = symbolToSearch || symbolQuery.trim();
    if (!sym) {
      setErrorMsg("Enter a symbol (class, function, or file name) to query");
      return;
    }
    setIsSearching(true);
    setErrorMsg(null);
    try {
      const res = await fetchWithAuth(
        `/graph/repositories/${repoId}/subgraph?symbol=${encodeURIComponent(sym)}&depth=${depth}`
      );
      if (res.ok) {
        const data = await res.json();
        if (data.nodes && data.nodes.length > 0) {
          // Layout nodes circularly / in a grid
          const count = data.nodes.length;
          const radius = Math.max(180, count * 28);
          const formattedNodes: Node[] = data.nodes.map((n: any, idx: number) => {
            const angle = (idx / count) * 2 * Math.PI;
            const x = 400 + radius * Math.cos(angle);
            const y = 300 + radius * Math.sin(angle);
            const labelType = n.data?.type || "Symbol";

            let bg = "#1E293B";
            let border = "#475569";
            let text = "#F8FAFC";
            if (labelType === "Class") {
              bg = "#2E1065";
              border = "#8B5CF6";
              text = "#DDD6FE";
            } else if (labelType === "Function") {
              bg = "#083344";
              border = "#06B6D4";
              text = "#CFFAFE";
            } else if (labelType === "File") {
              bg = "#172554";
              border = "#3B82F6";
              text = "#DBEAFE";
            }

            return {
              id: n.id,
              data: {
                label: (
                  <div className="p-2 text-center">
                    <span className="text-[9px] uppercase font-mono tracking-wider opacity-70 block">
                      {labelType}
                    </span>
                    <strong className="text-xs font-mono">{n.data?.label || n.id}</strong>
                  </div>
                ),
              },
              position: { x, y },
              style: {
                background: bg,
                border: `1.5px solid ${border}`,
                borderRadius: "10px",
                color: text,
                minWidth: "120px",
              },
            };
          });

          const formattedEdges: Edge[] = (data.edges || []).map((e: any, idx: number) => ({
            id: e.id || `e-${idx}`,
            source: e.source,
            target: e.target,
            label: e.label || "",
            animated: e.label === "CALLS",
            style: { stroke: "#64748B", strokeWidth: 1.5 },
            labelStyle: { fill: "#94A3B8", fontSize: 10, fontFamily: "monospace" },
            markerEnd: { type: MarkerType.ArrowClosed, color: "#64748B" },
          }));

          setNodes(formattedNodes);
          setEdges(formattedEdges);
        } else {
          setErrorMsg(`No code entities matched symbol "${sym}". Try "class", "def", or a filename.`);
        }
      }
    } catch (err) {
      setErrorMsg(String(err));
    } finally {
      setIsSearching(false);
    }
  }

  return (
    <div className="space-y-4 h-[calc(100vh-6rem)] flex flex-col">
      {/* Top Header Bar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between shrink-0 bg-[#111827] border border-border/80 px-5 py-3.5 rounded-2xl gap-4">
        <div className="flex items-center gap-4">
          <Link
            href={`/repositories/${repoId}`}
            className="p-1.5 text-muted-foreground hover:text-white rounded-lg hover:bg-card transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>

          <div>
            <div className="flex items-center gap-3">
              <Share2 className="w-5 h-5 text-violet-400" />
              <h1 className="text-lg font-bold text-white tracking-tight">Code Knowledge Graph (GraphRAG)</h1>
              <span className="text-xs font-mono px-2 py-0.5 rounded bg-cyan-950/60 text-cyan-300 border border-cyan-800">
                {summary?.backend ? summary.backend.toUpperCase() : "FALLBACK"}
              </span>
            </div>
            <div className="flex items-center gap-3 text-xs font-mono text-muted-foreground mt-1">
              <span>{summary?.nodes || 0} Nodes</span>
              <span>&bull;</span>
              <span>{summary?.edges || 0} Relationship Edges</span>
              <span>&bull;</span>
              <span>Backend: {summary?.backend === "neo4j" ? "Neo4j Cypher" : "NetworkX In-Memory"}</span>
            </div>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={handleExtract}
            disabled={isExtracting}
            className="px-3 py-1.5 rounded-xl bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white text-xs font-medium flex items-center gap-1.5 transition"
          >
            {isExtracting ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
            <span>Extract AST Graph</span>
          </button>

          <button
            onClick={loadSummary}
            className="p-1.5 text-muted-foreground hover:text-white rounded-lg bg-[#0A0E17] border border-border"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Query Bar */}
      <div className="shrink-0 bg-[#111827] border border-border/80 px-5 py-3 rounded-2xl flex flex-col sm:flex-row items-center gap-3">
        <div className="relative flex-1 w-full">
          <Search className="w-4 h-4 text-muted-foreground absolute left-3 top-2.5" />
          <input
            type="text"
            value={symbolQuery}
            onChange={(e) => setSymbolQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleQuerySubgraph()}
            placeholder="Search class, function, or file symbol to visualize graph neighborhood..."
            className="w-full bg-[#0A0E17] border border-border rounded-xl pl-9 pr-3 py-2 text-xs text-foreground focus:outline-none focus:border-violet-500 font-mono"
          />
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto">
          <label className="text-xs font-mono text-muted-foreground shrink-0">Hops: {depth}</label>
          <input
            type="range"
            min={1}
            max={4}
            value={depth}
            onChange={(e) => setDepth(Number(e.target.value))}
            className="w-20 accent-violet-500"
          />

          <button
            onClick={() => handleQuerySubgraph()}
            disabled={isSearching}
            className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white rounded-xl text-xs font-medium font-mono shrink-0 transition"
          >
            {isSearching ? "Searching..." : "Explore Graph"}
          </button>
        </div>
      </div>

      {errorMsg && (
        <div className="p-3 bg-amber-950/40 border border-amber-800 text-amber-300 text-xs rounded-xl font-mono shrink-0">
          {errorMsg}
        </div>
      )}

      {/* React Flow Canvas */}
      <div className="flex-1 bg-[#0A0E17] border border-border/80 rounded-2xl overflow-hidden relative">
        {nodes.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center p-8 text-muted-foreground font-mono text-xs">
            <Share2 className="w-10 h-10 mb-3 text-muted-foreground/30" />
            <p className="max-w-md">
              Extract the code knowledge graph and query a symbol (e.g. &quot;class&quot;, &quot;user&quot;, or a function name) to
              render the connected AST knowledge graph.
            </p>
          </div>
        ) : (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            fitView
          >
            <Background color="#1E293B" gap={16} />
            <Controls className="bg-[#111827] border-border text-white fill-white" />
            <MiniMap
              nodeColor={(n) => {
                if (n.style?.background) return n.style.background as string;
                return "#334155";
              }}
              style={{ backgroundColor: "#0A0E17" }}
            />
          </ReactFlow>
        )}
      </div>
    </div>
  );
}
