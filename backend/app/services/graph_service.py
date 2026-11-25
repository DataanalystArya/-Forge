"""
Phase 5 — GraphRAG: Code Knowledge Graph Service

Builds a knowledge graph of a repository's code structure (Files, Classes,
Functions, Imports) and edges (CONTAINS, CALLS, IMPORTS, INHERITS).

Primary backend: Neo4j (when NEO4J_URI is set and reachable).
Fallback: in-memory NetworkX graph + SQLite-persisted GraphNode/GraphEdge rows.
"""
from __future__ import annotations

import ast
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import networkx as nx

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Try optional Neo4j import
# ---------------------------------------------------------------------------
try:
    from neo4j import GraphDatabase, exceptions as neo4j_exc  # type: ignore

    _NEO4J_AVAILABLE = True
except ImportError:
    _NEO4J_AVAILABLE = False
    neo4j_exc = None  # type: ignore


# ---------------------------------------------------------------------------
# Lightweight AST walker
# ---------------------------------------------------------------------------

class _ASTExtractor(ast.NodeVisitor):
    """Walks a Python AST and collects nodes/edges for the graph."""

    def __init__(self, file_path: str, module_name: str) -> None:
        self.file_path = file_path
        self.module_name = module_name
        self.nodes: list[dict] = []
        self.edges: list[dict] = []
        self._scope_stack: list[str] = [module_name]

    # ---- helpers ----------------------------------------------------------

    def _current_scope(self) -> str:
        return self._scope_stack[-1]

    def _add_node(self, label: str, name: str, qualified: str, **props) -> None:
        self.nodes.append(
            {
                "label": label,
                "name": name,
                "qualified_name": qualified,
                "file_path": self.file_path,
                **props,
            }
        )

    def _add_edge(self, src: str, rel: str, tgt: str) -> None:
        self.edges.append({"source": src, "relation": rel, "target": tgt})

    # ---- visitors ---------------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            self._add_edge(self._current_scope(), "IMPORTS", alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        module = node.module or ""
        self._add_edge(self._current_scope(), "IMPORTS", module)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        qualified = f"{self._current_scope()}.{node.name}"
        self._add_node(
            "Class",
            node.name,
            qualified,
            lineno=node.lineno,
        )
        self._add_edge(self._current_scope(), "CONTAINS", qualified)
        for base in node.bases:
            if isinstance(base, ast.Name):
                self._add_edge(qualified, "INHERITS", base.id)
            elif isinstance(base, ast.Attribute):
                self._add_edge(qualified, "INHERITS", f"{base.attr}")
        self._scope_stack.append(qualified)
        self.generic_visit(node)
        self._scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:  # noqa: N802
        qualified = f"{self._current_scope()}.{node.name}"
        self._add_node(
            "Function",
            node.name,
            qualified,
            lineno=node.lineno,
            is_async=isinstance(node, ast.AsyncFunctionDef),
        )
        self._add_edge(self._current_scope(), "CONTAINS", qualified)
        self._scope_stack.append(qualified)
        self.generic_visit(node)
        self._scope_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        # Capture simple name calls (e.g. foo()) and attribute calls (e.g. obj.bar())
        callee = None
        if isinstance(node.func, ast.Name):
            callee = node.func.id
        elif isinstance(node.func, ast.Attribute):
            callee = node.func.attr
        if callee:
            self._add_edge(self._current_scope(), "CALLS", callee)
        self.generic_visit(node)


def _extract_py_graph(file_path: str, repo_id: str) -> tuple[list[dict], list[dict]]:
    """Return (nodes, edges) for one Python file."""
    try:
        source = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source, filename=file_path)
    except (SyntaxError, OSError):
        return [], []

    # Build a dotted module name from the path tail
    rel = Path(file_path).stem.replace(os.sep, ".")
    extractor = _ASTExtractor(file_path, rel)
    extractor.visit(tree)
    return extractor.nodes, extractor.edges


def _extract_js_ts_graph(file_path: str) -> tuple[list[dict], list[dict]]:
    """Very light regex-based extractor for JS/TS files."""
    nodes: list[dict] = []
    edges: list[dict] = []
    try:
        source = Path(file_path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return [], []

    module = Path(file_path).stem

    # Function declarations / arrow functions assigned to const
    for m in re.finditer(
        r"(?:export\s+)?(?:async\s+)?function\s+(\w+)|const\s+(\w+)\s*=\s*(?:async\s+)?\(",
        source,
    ):
        name = m.group(1) or m.group(2)
        qn = f"{module}.{name}"
        nodes.append({"label": "Function", "name": name, "qualified_name": qn, "file_path": file_path})
        edges.append({"source": module, "relation": "CONTAINS", "target": qn})

    # Class declarations
    for m in re.finditer(r"(?:export\s+)?class\s+(\w+)", source):
        name = m.group(1)
        qn = f"{module}.{name}"
        nodes.append({"label": "Class", "name": name, "qualified_name": qn, "file_path": file_path})
        edges.append({"source": module, "relation": "CONTAINS", "target": qn})

    # Import statements
    for m in re.finditer(r"""(?:import|require)\s*\(?['"]([^'"]+)['"]\)?""", source):
        edges.append({"source": module, "relation": "IMPORTS", "target": m.group(1)})

    return nodes, edges


# ---------------------------------------------------------------------------
# GraphService
# ---------------------------------------------------------------------------

class GraphService:
    """
    Singleton that wraps a code knowledge graph.

    When Neo4j is available:  all data is stored/queried via Cypher.
    When unavailable:          NetworkX in-memory graph is used as fallback.
    """

    _instance: "GraphService | None" = None

    def __init__(self) -> None:
        self._nx: dict[str, nx.DiGraph] = {}  # repo_id → DiGraph
        self._neo4j_driver = None
        self._neo4j_ok = False
        self._try_neo4j()

    # ---- singleton --------------------------------------------------------

    @classmethod
    def get_instance(cls) -> "GraphService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """For tests: drop singleton and Neo4j driver."""
        if cls._instance and cls._instance._neo4j_driver:
            try:
                cls._instance._neo4j_driver.close()
            except Exception:
                pass
        cls._instance = None

    # ---- Neo4j probe ------------------------------------------------------

    def _try_neo4j(self) -> None:
        if not _NEO4J_AVAILABLE:
            logger.info("GraphService: neo4j package not installed — using NetworkX fallback")
            return
        uri = getattr(settings, "NEO4J_URI", None)
        user = getattr(settings, "NEO4J_USER", "neo4j")
        password = getattr(settings, "NEO4J_PASSWORD", "")
        use_memory = getattr(settings, "NEO4J_USE_MEMORY", True)
        if use_memory or not uri:
            logger.info("GraphService: NEO4J_USE_MEMORY=true — using NetworkX fallback")
            return
        try:
            driver = GraphDatabase.driver(uri, auth=(user, password))
            driver.verify_connectivity()
            self._neo4j_driver = driver
            self._neo4j_ok = True
            logger.info("GraphService: connected to Neo4j at %s", uri)
        except Exception as exc:
            logger.warning("GraphService: Neo4j unavailable (%s) — using NetworkX fallback", exc)

    # ---- public API -------------------------------------------------------

    @property
    def neo4j_connected(self) -> bool:
        return self._neo4j_ok

    def extract_code_graph(self, repo_id: str, workspace_dir: str) -> dict[str, Any]:
        """
        Walk *workspace_dir*, extract code entities, and populate the graph.
        Returns a summary dict: {nodes, edges, files_scanned}.
        """
        total_nodes: list[dict] = []
        total_edges: list[dict] = []
        files_scanned = 0

        # File node per source file
        for root, _dirs, files in os.walk(workspace_dir):
            # Skip hidden / build dirs
            _dirs[:] = [
                d for d in _dirs
                if not d.startswith(".") and d not in {"node_modules", "__pycache__", ".git", "dist", "build", ".next"}
            ]
            for fname in files:
                fpath = os.path.join(root, fname)
                ext = Path(fname).suffix.lower()
                rel_path = os.path.relpath(fpath, workspace_dir)
                file_qn = f"file:{rel_path}"

                total_nodes.append(
                    {
                        "label": "File",
                        "name": fname,
                        "qualified_name": file_qn,
                        "file_path": rel_path,
                    }
                )

                if ext == ".py":
                    n, e = _extract_py_graph(fpath, repo_id)
                    # Tie top-level module node to File node
                    if n:
                        total_edges.append({"source": file_qn, "relation": "CONTAINS", "target": n[0]["qualified_name"].split(".")[0]})
                    total_nodes.extend(n)
                    total_edges.extend(e)
                    files_scanned += 1
                elif ext in {".js", ".jsx", ".ts", ".tsx"}:
                    n, e = _extract_js_ts_graph(fpath)
                    if n:
                        total_edges.append({"source": file_qn, "relation": "CONTAINS", "target": n[0]["qualified_name"].split(".")[0]})
                    total_nodes.extend(n)
                    total_edges.extend(e)
                    files_scanned += 1

        # Store
        if self._neo4j_ok:
            self._store_neo4j(repo_id, total_nodes, total_edges)
        else:
            self._store_nx(repo_id, total_nodes, total_edges)

        return {
            "repo_id": repo_id,
            "nodes": len(total_nodes),
            "edges": len(total_edges),
            "files_scanned": files_scanned,
            "backend": "neo4j" if self._neo4j_ok else "networkx",
        }

    def get_graph_summary(self, repo_id: str) -> dict[str, Any]:
        """Return node/edge counts for a repository."""
        if self._neo4j_ok:
            return self._summary_neo4j(repo_id)
        g = self._get_nx(repo_id)
        if g is None:
            return {"repo_id": repo_id, "nodes": 0, "edges": 0, "available": False}
        label_counts: dict[str, int] = {}
        for _, data in g.nodes(data=True):
            lbl = data.get("label", "Unknown")
            label_counts[lbl] = label_counts.get(lbl, 0) + 1
        rel_counts: dict[str, int] = {}
        for _, _, data in g.edges(data=True):
            rel = data.get("relation", "UNKNOWN")
            rel_counts[rel] = rel_counts.get(rel, 0) + 1
        return {
            "repo_id": repo_id,
            "nodes": g.number_of_nodes(),
            "edges": g.number_of_edges(),
            "available": True,
            "backend": "networkx",
            "node_labels": label_counts,
            "edge_relations": rel_counts,
        }

    def query_subgraph(self, repo_id: str, symbol: str, depth: int = 2) -> dict[str, Any]:
        """
        Return a subgraph centred on *symbol* up to *depth* hops.
        Compatible with React Flow data shape: {nodes: [...], edges: [...]}.
        """
        if self._neo4j_ok:
            return self._subgraph_neo4j(repo_id, symbol, depth)
        return self._subgraph_nx(repo_id, symbol, depth)

    def query_context(self, repo_id: str, query: str, limit: int = 8) -> dict[str, Any]:
        """
        Return relevant graph context for RAG augmentation.
        Finds nodes whose name contains query terms.
        """
        if self._neo4j_ok:
            return self._context_neo4j(repo_id, query, limit)
        return self._context_nx(repo_id, query, limit)

    # ---- NetworkX backend -------------------------------------------------

    def _get_nx(self, repo_id: str) -> nx.DiGraph | None:
        if repo_id in self._nx:
            return self._nx[repo_id]
        cache_path = Path("./data/graphs") / f"{repo_id}.json"
        if cache_path.is_file():
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                g = nx.node_link_graph(data)
                self._nx[repo_id] = g
                return g
            except Exception as exc:
                logger.warning("Failed to load persisted graph %s: %s", cache_path, exc)
        return None

    def _store_nx(self, repo_id: str, nodes: list[dict], edges: list[dict]) -> None:
        g = nx.DiGraph()
        for n in nodes:
            qn = n["qualified_name"]
            g.add_node(qn, **n)
        for e in edges:
            g.add_edge(e["source"], e["target"], relation=e["relation"])
        self._nx[repo_id] = g
        try:
            cache_dir = Path("./data/graphs")
            cache_dir.mkdir(parents=True, exist_ok=True)
            with open(cache_dir / f"{repo_id}.json", "w", encoding="utf-8") as f:
                json.dump(nx.node_link_data(g), f)
        except Exception as exc:
            logger.warning("Failed to persist graph %s to disk: %s", repo_id, exc)

    def _subgraph_nx(self, repo_id: str, symbol: str, depth: int) -> dict[str, Any]:
        g = self._get_nx(repo_id)
        if g is None:
            return {"available": False, "nodes": [], "edges": []}
        # Find seed nodes that match symbol (case-insensitive substring)
        seeds = [n for n in g.nodes if symbol.lower() in n.lower()]
        if not seeds:
            return {"available": True, "nodes": [], "edges": []}
        # BFS up to depth hops
        visited: set[str] = set()
        frontier = set(seeds[:5])  # cap seeds
        for _ in range(depth):
            next_frontier: set[str] = set()
            for node in frontier:
                if node in g:
                    next_frontier.update(g.successors(node))
                    next_frontier.update(g.predecessors(node))
            visited.update(frontier)
            frontier = next_frontier - visited
        visited.update(frontier)
        sg = g.subgraph(visited)
        rf_nodes = [
            {
                "id": n,
                "data": {"label": d.get("name", n), "type": d.get("label", "?"), "file": d.get("file_path", "")},
                "position": {"x": 0, "y": 0},
            }
            for n, d in sg.nodes(data=True)
        ]
        rf_edges = [
            {"id": f"{u}-{v}", "source": u, "target": v, "label": d.get("relation", "")}
            for u, v, d in sg.edges(data=True)
        ]
        return {"available": True, "nodes": rf_nodes, "edges": rf_edges, "backend": "networkx"}

    def _context_nx(self, repo_id: str, query: str, limit: int) -> dict[str, Any]:
        g = self._get_nx(repo_id)
        if g is None:
            return {"available": False, "nodes": [], "edges": []}
        terms = query.lower().split()
        matches = []
        for n, data in g.nodes(data=True):
            name = data.get("name", "").lower()
            if any(t in name for t in terms):
                matches.append(data)
            if len(matches) >= limit:
                break
        return {"available": True, "nodes": matches, "edges": [], "backend": "networkx"}

    def _summary_neo4j(self, repo_id: str) -> dict[str, Any]:  # pragma: no cover
        with self._neo4j_driver.session() as s:
            nc = s.run("MATCH (n {repo_id: $r}) RETURN count(n) AS c", r=repo_id).single()["c"]
            ec = s.run("MATCH ()-[r {repo_id: $r}]->() RETURN count(r) AS c", r=repo_id).single()["c"]
        return {"repo_id": repo_id, "nodes": nc, "edges": ec, "available": True, "backend": "neo4j"}

    def _store_neo4j(self, repo_id: str, nodes: list[dict], edges: list[dict]) -> None:  # pragma: no cover
        with self._neo4j_driver.session() as s:
            s.run("MATCH (n {repo_id: $r}) DETACH DELETE n", r=repo_id)
            for n in nodes:
                s.run(
                    f"CREATE (:{n['label']} {{repo_id: $r, name: $name, qualified_name: $qn, file_path: $fp}})",
                    r=repo_id, name=n["name"], qn=n["qualified_name"], fp=n.get("file_path", ""),
                )
            for e in edges:
                s.run(
                    f"MATCH (a {{repo_id: $r, qualified_name: $src}}) "
                    f"MATCH (b {{repo_id: $r, qualified_name: $tgt}}) "
                    f"CREATE (a)-[:{e['relation']} {{repo_id: $r}}]->(b)",
                    r=repo_id, src=e["source"], tgt=e["target"],
                )

    def _subgraph_neo4j(self, repo_id: str, symbol: str, depth: int) -> dict[str, Any]:  # pragma: no cover
        with self._neo4j_driver.session() as s:
            result = s.run(
                f"MATCH p=(n {{repo_id: $r}})-[*0..{depth}]-(m) "
                "WHERE n.qualified_name CONTAINS $sym "
                "RETURN nodes(p) AS ns, relationships(p) AS rs",
                r=repo_id, sym=symbol,
            )
            nodes_out, edges_out = [], []
            seen_n, seen_e = set(), set()
            for rec in result:
                for nd in rec["ns"]:
                    if nd.id not in seen_n:
                        seen_n.add(nd.id)
                        nodes_out.append({"id": str(nd.id), "data": {"label": nd.get("name", ""), "type": list(nd.labels)[0]}})
                for rel in rec["rs"]:
                    eid = rel.id
                    if eid not in seen_e:
                        seen_e.add(eid)
                        edges_out.append({"id": str(eid), "source": str(rel.start_node.id), "target": str(rel.end_node.id), "label": rel.type})
        return {"available": True, "nodes": nodes_out, "edges": edges_out, "backend": "neo4j"}

    def _context_neo4j(self, repo_id: str, query: str, limit: int) -> dict[str, Any]:  # pragma: no cover
        with self._neo4j_driver.session() as s:
            result = s.run(
                "MATCH (n {repo_id: $r}) WHERE n.name CONTAINS $q RETURN n LIMIT $l",
                r=repo_id, q=query, l=limit,
            )
            nodes = [dict(rec["n"]) for rec in result]
        return {"available": True, "nodes": nodes, "edges": [], "backend": "neo4j"}
