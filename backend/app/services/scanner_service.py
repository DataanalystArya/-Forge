import ast
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from sqlalchemy.orm import Session
from app.models.repository import Repository, IndexingJob, CodeArtifact

logger = logging.getLogger("forge.scanner")

IGNORED_DIRECTORIES = {
    ".git",
    "node_modules",
    "venv",
    ".venv",
    "__pycache__",
    "dist",
    "build",
    ".next",
    ".pytest_cache",
    ".vscode",
    ".idea",
    "storage",
    "workspaces",
    ".gemini",
}

IGNORED_EXTENSIONS = {
    ".pyc", ".pyo", ".pyd",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
    ".pdf", ".zip", ".tar", ".gz", ".7z",
    ".exe", ".dll", ".so", ".dylib", ".bin",
    ".woff", ".woff2", ".ttf", ".eot",
    ".mp4", ".mp3", ".wav", ".avi",
    ".db", ".sqlite", ".sqlite3",
}

LANGUAGE_MAP = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript (React)",
    ".ts": "TypeScript",
    ".tsx": "TypeScript (React)",
    ".rs": "Rust",
    ".go": "Go",
    ".java": "Java",
    ".cpp": "C++",
    ".c": "C",
    ".h": "C/C++ Header",
    ".hpp": "C++ Header",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".md": "Markdown",
    ".sql": "SQL",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".toml": "TOML",
    ".xml": "XML",
}

# Try loading tree-sitter python parser
TS_PYTHON_PARSER = None
try:
    from tree_sitter import Language, Parser
    import tree_sitter_python
    PY_LANGUAGE = Language(tree_sitter_python.language())
    TS_PYTHON_PARSER = Parser(PY_LANGUAGE)
    logger.info("Tree-sitter Python parser loaded successfully.")
except Exception as e:
    logger.info(f"Tree-sitter native parser init notice ({e}); will use Python AST parser.")


def is_binary_file(filepath: Path) -> bool:
    """Detect binary files by sampling the first 1024 bytes for null bytes."""
    try:
        with open(filepath, "rb") as f:
            chunk = f.read(1024)
            if b"\x00" in chunk:
                return True
        return False
    except Exception:
        return True


def extract_python_symbols_ast(content: str, rel_path: str) -> List[Dict[str, Any]]:
    """Extract classes, functions, and methods using Python's AST."""
    symbols = []
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                symbols.append({
                    "entity_type": "CLASS",
                    "entity_name": node.name,
                    "start_line": node.lineno,
                    "end_line": getattr(node, "end_lineno", node.lineno),
                })
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append({
                    "entity_type": "FUNCTION",
                    "entity_name": node.name,
                    "start_line": node.lineno,
                    "end_line": getattr(node, "end_lineno", node.lineno),
                })
    except Exception:
        pass
    return symbols


def extract_python_symbols_treesitter(content_bytes: bytes) -> List[Dict[str, Any]]:
    """Extract functions and classes using Tree-sitter AST parser."""
    symbols = []
    if not TS_PYTHON_PARSER:
        return symbols

    try:
        tree = TS_PYTHON_PARSER.parse(content_bytes)
        root = tree.root_node

        def traverse(node):
            if node.type == "class_definition":
                name_node = node.child_by_field_name("name")
                name = name_node.text.decode("utf-8") if name_node else "UnknownClass"
                symbols.append({
                    "entity_type": "CLASS",
                    "entity_name": name,
                    "start_line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                })
            elif node.type == "function_definition":
                name_node = node.child_by_field_name("name")
                name = name_node.text.decode("utf-8") if name_node else "anonymous"
                symbols.append({
                    "entity_type": "FUNCTION",
                    "entity_name": name,
                    "start_line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                })
            for child in node.children:
                traverse(child)

        traverse(root)
    except Exception as e:
        logger.debug(f"Tree-sitter parse error: {e}")
    return symbols


def extract_ts_js_symbols_simple(content: str) -> List[Dict[str, Any]]:
    """Extract functions, classes, and exported constants from JS/TS files."""
    import re
    symbols = []
    lines = content.splitlines()

    class_regex = re.compile(r"^\s*(export\s+)?(default\s+)?class\s+([A-Za-z0-9_]+)")
    func_regex = re.compile(r"^\s*(export\s+)?(async\s+)?function\s+([A-Za-z0-9_]+)")
    arrow_regex = re.compile(r"^\s*(export\s+)?const\s+([A-Za-z0-9_]+)\s*=\s*(async\s*)?\(")

    for idx, line in enumerate(lines, start=1):
        c_match = class_regex.match(line)
        if c_match:
            symbols.append({
                "entity_type": "CLASS",
                "entity_name": c_match.group(3),
                "start_line": idx,
                "end_line": idx,
            })
            continue

        f_match = func_regex.match(line)
        if f_match:
            symbols.append({
                "entity_type": "FUNCTION",
                "entity_name": f_match.group(3),
                "start_line": idx,
                "end_line": idx,
            })
            continue

        a_match = arrow_regex.match(line)
        if a_match:
            symbols.append({
                "entity_type": "FUNCTION",
                "entity_name": a_match.group(2),
                "start_line": idx,
                "end_line": idx,
            })

    return symbols


class RepositoryScanner:
    @staticmethod
    def scan_repository(repo: Repository, workspace_dir: Path, db: Session) -> Repository:
        """Scan directory structure, extract symbols, and populate repository metadata."""
        logger.info(f"Starting repository structural scan for {repo.full_name} ({workspace_dir})")

        job = db.query(IndexingJob).filter(IndexingJob.repository_id == repo.id).first()
        if not job:
            job = IndexingJob(repository_id=repo.id, status="PARSING")
            db.add(job)
        else:
            job.status = "PARSING"
        db.commit()

        total_files = 0
        total_lines = 0
        lang_counts: Dict[str, int] = {}
        artifacts_to_insert: List[CodeArtifact] = []

        # Clear old artifacts if re-scanning
        db.query(CodeArtifact).filter(CodeArtifact.repository_id == repo.id).delete()
        db.commit()

        for root, dirs, files in os.walk(workspace_dir):
            # Prune ignored directories in-place
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRECTORIES]

            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in IGNORED_EXTENSIONS:
                    continue

                file_path = Path(root) / file
                # Skip files larger than 2MB
                try:
                    if file_path.stat().st_size > 2 * 1024 * 1024:
                        continue
                except Exception:
                    continue

                if is_binary_file(file_path):
                    continue

                rel_path = str(file_path.relative_to(workspace_dir))
                language = LANGUAGE_MAP.get(ext, "Other")
                lang_counts[language] = lang_counts.get(language, 0) + 1
                total_files += 1

                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                except Exception:
                    continue

                file_lines = len(content.splitlines())
                total_lines += file_lines

                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

                # Add file-level artifact
                artifacts_to_insert.append(
                    CodeArtifact(
                        repository_id=repo.id,
                        file_path=rel_path,
                        language=language,
                        entity_type="FILE",
                        entity_name=file,
                        start_line=1,
                        end_line=file_lines,
                        content_hash=content_hash,
                    )
                )

                # Symbol extraction
                symbols = []
                if language == "Python":
                    if TS_PYTHON_PARSER:
                        symbols = extract_python_symbols_treesitter(content.encode("utf-8"))
                    if not symbols:
                        symbols = extract_python_symbols_ast(content, rel_path)
                elif language in ("JavaScript", "TypeScript", "JavaScript (React)", "TypeScript (React)"):
                    symbols = extract_ts_js_symbols_simple(content)

                for sym in symbols:
                    artifacts_to_insert.append(
                        CodeArtifact(
                            repository_id=repo.id,
                            file_path=rel_path,
                            language=language,
                            entity_type=sym["entity_type"],
                            entity_name=sym["entity_name"],
                            start_line=sym["start_line"],
                            end_line=sym["end_line"],
                            content_hash=content_hash,
                        )
                    )

        # Batch insert artifacts
        if artifacts_to_insert:
            db.bulk_save_objects(artifacts_to_insert)

        # Calculate language distribution percentages
        lang_percentages = {}
        if total_files > 0:
            for l_name, count in lang_counts.items():
                lang_percentages[l_name] = round((count / total_files) * 100, 1)

        # Update repository record
        repo.status = "READY"
        repo.total_files = total_files
        repo.total_lines = total_lines
        repo.languages_json = json.dumps(lang_percentages)
        repo.indexed_at = datetime.now(timezone.utc)

        # Update job
        job.status = "COMPLETED"
        job.indexed_files = total_files
        job.total_files = total_files
        job.completed_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(repo)

        logger.info(
            f"Repository {repo.full_name} scanned: {total_files} files, {total_lines} lines, "
            f"{len(artifacts_to_insert)} code artifacts indexed."
        )
        return repo
