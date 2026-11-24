"use client";

import React, { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  FolderGit2,
  ChevronRight,
  ChevronDown,
  FileCode,
  Folder,
  FolderOpen,
  ArrowLeft,
  RefreshCw,
  Terminal,
  Layers,
  Code2,
  FileText,
  AlertCircle,
  Database,
  Cpu,
} from "lucide-react";
import { fetchWithAuth } from "@/lib/utils";

// Dynamic import for Monaco Editor without SSR
const MonacoEditor = dynamic(() => import("@monaco-editor/react"), {
  ssr: false,
  loading: () => (
    <div className="h-full w-full flex items-center justify-center bg-[#0D1117] text-muted-foreground font-mono text-sm">
      Initializing Monaco Code Viewer...
    </div>
  ),
});

interface FileTreeNode {
  name: string;
  path: string;
  type: "file" | "directory";
  size?: number;
  language?: string;
  children?: FileTreeNode[];
}

interface RepositoryDetails {
  id: string;
  full_name: string;
  description?: string;
  default_branch: string;
  is_private: boolean;
  status: string;
  total_files: number;
  total_lines: number;
  languages_json?: string;
  indexed_at?: string;
}

interface CodeArtifact {
  id: string;
  file_path: string;
  language?: string;
  entity_type: string;
  entity_name?: string;
  start_line?: number;
  end_line?: number;
}

export default function RepositoryExplorerDetailPage() {
  const params = useParams();
  const repoId = params?.id as string;

  const [repo, setRepo] = useState<RepositoryDetails | null>(null);
  const [tree, setTree] = useState<FileTreeNode[]>([]);
  const [artifacts, setArtifacts] = useState<CodeArtifact[]>([]);
  const [activeTab, setActiveTab] = useState<"tree" | "symbols">("tree");

  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string>("");
  const [fileMeta, setFileMeta] = useState<{ language: string; lines: number; size: number } | null>(null);

  const [expandedDirs, setExpandedDirs] = useState<Record<string, boolean>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [isFileLoading, setIsFileLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load repository metadata, tree, and artifacts
  const loadRepoData = async () => {
    if (!repoId) return;
    try {
      setIsLoading(true);
      setError(null);

      // 1. Fetch Repository Details
      const repoRes = await fetchWithAuth(`/repositories/${repoId}`);
      if (!repoRes.ok) throw new Error("Failed to load repository details.");
      const repoData = await repoRes.json();
      setRepo(repoData);

      // 2. Fetch File Tree
      const treeRes = await fetchWithAuth(`/repositories/${repoId}/tree`);
      if (treeRes.ok) {
        const treeData = await treeRes.json();
        setTree(treeData);

        // Auto-expand top level folders
        const initialExpanded: Record<string, boolean> = {};
        treeData.forEach((item: FileTreeNode) => {
          if (item.type === "directory") initialExpanded[item.path] = true;
        });
        setExpandedDirs(initialExpanded);

        // Auto-select first file if available
        const findFirstFile = (nodes: FileTreeNode[]): string | null => {
          for (const node of nodes) {
            if (node.type === "file") return node.path;
            if (node.children) {
              const f = findFirstFile(node.children);
              if (f) return f;
            }
          }
          return null;
        };
        const first = findFirstFile(treeData);
        if (first) {
          loadFile(first);
        }
      }

      // 3. Fetch Extracted Symbols
      const symRes = await fetchWithAuth(`/repositories/${repoId}/symbols?limit=200`);
      if (symRes.ok) {
        const symData = await symRes.json();
        setArtifacts(symData.artifacts || []);
      }
    } catch (err: any) {
      setError(err.message || "An error occurred.");
    } finally {
      setIsLoading(false);
    }
  };

  const loadFile = async (path: string) => {
    try {
      setIsFileLoading(true);
      setSelectedFile(path);
      const res = await fetchWithAuth(`/repositories/${repoId}/file?path=${encodeURIComponent(path)}`);
      if (res.ok) {
        const data = await res.json();
        setFileContent(data.content);
        setFileMeta({
          language: data.language,
          lines: data.lines,
          size: data.size,
        });
      } else {
        setFileContent("// Unable to read file content.");
        setFileMeta(null);
      }
    } catch (err) {
      setFileContent("// Error loading file.");
    } finally {
      setIsFileLoading(false);
    }
  };

  const toggleDirectory = (dirPath: string) => {
    setExpandedDirs((prev) => ({
      ...prev,
      [dirPath]: !prev[dirPath],
    }));
  };

  useEffect(() => {
    loadRepoData();
  }, [repoId]);

  // Map backend language strings to Monaco editor language IDs
  const getMonacoLanguage = (lang?: string): string => {
    if (!lang) return "plaintext";
    const lower = lang.toLowerCase();
    if (lower.includes("python")) return "python";
    if (lower.includes("typescript")) return "typescript";
    if (lower.includes("javascript")) return "javascript";
    if (lower.includes("json")) return "json";
    if (lower.includes("markdown")) return "markdown";
    if (lower.includes("html")) return "html";
    if (lower.includes("css")) return "css";
    if (lower.includes("rust")) return "rust";
    if (lower.includes("go")) return "go";
    if (lower.includes("c++") || lower.includes("c")) return "cpp";
    if (lower.includes("yaml")) return "yaml";
    if (lower.includes("sql")) return "sql";
    if (lower.includes("shell")) return "shell";
    return "plaintext";
  };

  // Render recursive file tree node
  const renderTreeNodes = (nodes: FileTreeNode[], depth = 0) => {
    return (
      <div className="space-y-0.5">
        {nodes.map((node) => {
          if (node.type === "directory") {
            const isExpanded = !!expandedDirs[node.path];
            return (
              <div key={node.path}>
                <div
                  onClick={() => toggleDirectory(node.path)}
                  style={{ paddingLeft: `${depth * 14 + 10}px` }}
                  className="flex items-center gap-2 py-1.5 px-2 rounded-md hover:bg-[#1E293B]/70 cursor-pointer text-xs font-mono text-muted-foreground hover:text-white transition-colors"
                >
                  {isExpanded ? (
                    <ChevronDown className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                  ) : (
                    <ChevronRight className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                  )}
                  {isExpanded ? (
                    <FolderOpen className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
                  ) : (
                    <Folder className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
                  )}
                  <span className="truncate">{node.name}</span>
                </div>
                {isExpanded && node.children && renderTreeNodes(node.children, depth + 1)}
              </div>
            );
          }

          const isSelected = selectedFile === node.path;
          return (
            <div
              key={node.path}
              onClick={() => loadFile(node.path)}
              style={{ paddingLeft: `${depth * 14 + 24}px` }}
              className={`flex items-center justify-between py-1.5 px-2 rounded-md cursor-pointer text-xs font-mono transition-colors ${
                isSelected
                  ? "bg-violet-600/20 text-violet-300 font-semibold border-l-2 border-violet-500"
                  : "text-muted-foreground hover:text-white hover:bg-[#1E293B]/50"
              }`}
            >
              <div className="flex items-center gap-2 truncate">
                <FileCode className={`w-3.5 h-3.5 shrink-0 ${isSelected ? "text-violet-400" : "text-muted-foreground"}`} />
                <span className="truncate">{node.name}</span>
              </div>
              <span className="text-[10px] text-muted-foreground/60 shrink-0 pl-1">{node.language}</span>
            </div>
          );
        })}
      </div>
    );
  };

  const languagesObj = repo?.languages_json ? JSON.parse(repo.languages_json) : {};

  return (
    <div className="space-y-4 h-[calc(100vh-6rem)] flex flex-col">
      {/* Top Header Bar */}
      <div className="flex items-center justify-between shrink-0 bg-[#111827] border border-border/80 px-5 py-3.5 rounded-2xl">
        <div className="flex items-center gap-4">
          <Link
            href="/repositories"
            className="p-1.5 text-muted-foreground hover:text-white rounded-lg hover:bg-card transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>

          <div>
            <div className="flex items-center gap-3">
              <FolderGit2 className="w-5 h-5 text-violet-400" />
              <h1 className="text-lg font-bold text-white tracking-tight">{repo?.full_name || "Repository"}</h1>
              <span className="text-xs font-mono px-2 py-0.5 rounded bg-emerald-950/60 text-emerald-300 border border-emerald-800">
                {repo?.status || "LOADING"}
              </span>
            </div>
            <div className="flex items-center gap-4 text-xs font-mono text-muted-foreground mt-1">
              <span>{repo?.total_files || 0} Files</span>
              <span>&bull;</span>
              <span>{repo?.total_lines || 0} Lines</span>
              <span>&bull;</span>
              <span>Branch: {repo?.default_branch || "main"}</span>
            </div>
          </div>
        </div>

        {/* Language distribution pills */}
        <div className="hidden md:flex items-center gap-2">
          {Object.entries(languagesObj).map(([lang, pct]) => (
            <span
              key={lang}
              className="px-2.5 py-1 rounded-full bg-[#0A0E17] border border-border text-[11px] font-mono text-cyan-300"
            >
              {lang}: {String(pct)}%
            </span>
          ))}
        </div>
      </div>

      {/* Main Workspace Splitter */}
      <div className="flex-1 flex gap-4 min-h-0 overflow-hidden">
        {/* Left Sidebar: File Tree & Symbols */}
        <div className="w-80 shrink-0 bg-[#111827] border border-border/80 rounded-2xl flex flex-col overflow-hidden">
          {/* Tabs */}
          <div className="flex border-b border-border bg-[#0A0E17] text-xs font-mono">
            <button
              onClick={() => setActiveTab("tree")}
              className={`flex-1 py-2.5 text-center font-medium transition-colors ${
                activeTab === "tree"
                  ? "border-b-2 border-violet-500 text-white bg-[#111827]"
                  : "text-muted-foreground hover:text-white"
              }`}
            >
              Files ({repo?.total_files || 0})
            </button>
            <button
              onClick={() => setActiveTab("symbols")}
              className={`flex-1 py-2.5 text-center font-medium transition-colors ${
                activeTab === "symbols"
                  ? "border-b-2 border-violet-500 text-white bg-[#111827]"
                  : "text-muted-foreground hover:text-white"
              }`}
            >
              AST Symbols ({artifacts.filter((a) => a.entity_type !== "FILE").length})
            </button>
          </div>

          {/* Tab Content */}
          <div className="flex-1 overflow-y-auto p-3">
            {isLoading ? (
              <div className="p-6 text-center text-xs font-mono text-muted-foreground">
                Loading repository structure...
              </div>
            ) : error ? (
              <div className="p-4 text-xs text-rose-400 bg-rose-500/10 rounded-xl border border-rose-500/30">
                {error}
              </div>
            ) : activeTab === "tree" ? (
              tree.length === 0 ? (
                <div className="p-8 text-center text-xs text-muted-foreground font-mono">
                  No source files found in workspace.
                </div>
              ) : (
                renderTreeNodes(tree)
              )
            ) : (
              /* Symbols View */
              <div className="space-y-2">
                {artifacts.filter((a) => a.entity_type !== "FILE").length === 0 ? (
                  <div className="p-8 text-center text-xs text-muted-foreground font-mono">
                    No AST symbols parsed yet.
                  </div>
                ) : (
                  artifacts
                    .filter((a) => a.entity_type !== "FILE")
                    .map((art) => (
                      <div
                        key={art.id}
                        onClick={() => loadFile(art.file_path)}
                        className="p-2.5 rounded-lg bg-[#0A0E17] border border-border hover:border-violet-500/40 cursor-pointer transition-all"
                      >
                        <div className="flex items-center justify-between mb-1">
                          <span
                            className={`text-[9px] font-mono px-1.5 py-0.5 rounded font-bold uppercase ${
                              art.entity_type === "CLASS"
                                ? "bg-cyan-950 text-cyan-300 border border-cyan-800"
                                : "bg-violet-950 text-violet-300 border border-violet-800"
                            }`}
                          >
                            {art.entity_type}
                          </span>
                          <span className="text-[10px] font-mono text-muted-foreground">
                            L{art.start_line}-{art.end_line}
                          </span>
                        </div>
                        <div className="text-xs font-bold text-white font-mono truncate">{art.entity_name}</div>
                        <div className="text-[10px] font-mono text-muted-foreground truncate mt-0.5">
                          {art.file_path}
                        </div>
                      </div>
                    ))
                )}
              </div>
            )}
          </div>
        </div>

        {/* Right Pane: Monaco Code Viewer */}
        <div className="flex-1 bg-[#111827] border border-border/80 rounded-2xl flex flex-col overflow-hidden">
          {/* File Meta Header */}
          <div className="h-11 px-4 border-b border-border bg-[#0A0E17] flex items-center justify-between text-xs font-mono shrink-0">
            <div className="flex items-center gap-2 truncate text-white">
              <FileCode className="w-4 h-4 text-violet-400 shrink-0" />
              <span className="truncate font-semibold">{selectedFile || "No file selected"}</span>
            </div>

            {fileMeta && (
              <div className="flex items-center gap-4 text-muted-foreground text-[11px]">
                <span>Language: <strong className="text-cyan-400">{fileMeta.language}</strong></span>
                <span>Lines: <strong className="text-white">{fileMeta.lines}</strong></span>
                <span>Size: <strong className="text-white">{(fileMeta.size / 1024).toFixed(1)} KB</strong></span>
              </div>
            )}
          </div>

          {/* Monaco Editor Container */}
          <div className="flex-1 relative bg-[#0D1117]">
            {isFileLoading ? (
              <div className="absolute inset-0 flex items-center justify-center bg-[#0D1117] text-muted-foreground font-mono text-xs">
                Loading source code...
              </div>
            ) : selectedFile ? (
              <MonacoEditor
                height="100%"
                language={getMonacoLanguage(fileMeta?.language)}
                theme="vs-dark"
                value={fileContent}
                options={{
                  readOnly: true,
                  minimap: { enabled: true },
                  fontSize: 13,
                  lineNumbers: "on",
                  scrollBeyondLastLine: false,
                  automaticLayout: true,
                  wordWrap: "on",
                  fontFamily: "JetBrains Mono, Menlo, Monaco, Consolas, monospace",
                }}
              />
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-muted-foreground font-mono text-xs p-8 text-center">
                <Code2 className="w-10 h-10 mb-3 text-muted-foreground/30" />
                <p>Select a file from the repository tree to inspect source code.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
