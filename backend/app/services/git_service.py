"""Phase 7 — Git/GitHub service: branch creation, patch application, diff generation."""
from __future__ import annotations

import logging
import os
import textwrap
import difflib
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import git  # gitpython
    _GIT_AVAILABLE = True
except ImportError:
    _GIT_AVAILABLE = False


class GitService:
    """Wraps gitpython operations for local workspace repositories."""

    def __init__(self, local_path: str) -> None:
        self.local_path = local_path
        self._repo = None
        if _GIT_AVAILABLE and os.path.isdir(os.path.join(local_path, ".git")):
            try:
                self._repo = git.Repo(local_path)
            except Exception as exc:
                logger.warning("GitService: cannot open repo at %s: %s", local_path, exc)

    @property
    def available(self) -> bool:
        return self._repo is not None

    # ---- branch -----------------------------------------------------------

    def create_branch(self, branch_name: str) -> dict:
        """Create and checkout a new branch from HEAD."""
        if not self._repo:
            return {"ok": False, "error": "Git repo not available"}
        try:
            new_branch = self._repo.create_head(branch_name)
            new_branch.checkout()
            return {"ok": True, "branch": branch_name}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def checkout_branch(self, branch_name: str) -> dict:
        """Checkout an existing branch."""
        if not self._repo:
            return {"ok": False, "error": "Git repo not available"}
        try:
            self._repo.git.checkout(branch_name)
            return {"ok": True, "branch": branch_name}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def current_branch(self) -> str:
        if self._repo:
            try:
                return self._repo.active_branch.name
            except Exception:
                return "HEAD"
        return "unknown"

    # ---- diff & patch -----------------------------------------------------

    def generate_diff(self, file_path: str, original: str, modified: str) -> str:
        """Return a unified diff string for a single file change."""
        rel = os.path.relpath(file_path, self.local_path)
        diff_lines = list(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                modified.splitlines(keepends=True),
                fromfile=f"a/{rel}",
                tofile=f"b/{rel}",
            )
        )
        return "".join(diff_lines)

    def apply_diff_patch(self, diff_content: str) -> dict:
        """
        Apply a unified diff to the workspace using git apply.
        Returns {"ok": bool, "error": str|None}.
        """
        if not self._repo:
            return {"ok": False, "error": "Git repo not available"}
        patch_path = os.path.join(self.local_path, ".forge_patch.diff")
        try:
            with open(patch_path, "w", encoding="utf-8") as f:
                f.write(diff_content if diff_content.endswith("\n") else diff_content + "\n")
            self._repo.git.apply(patch_path)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        finally:
            if os.path.exists(patch_path):
                os.unlink(patch_path)

    # ---- commit -----------------------------------------------------------

    def commit_all(self, message: str) -> dict:
        """Stage all changes and create a commit."""
        if not self._repo:
            return {"ok": False, "error": "Git repo not available"}
        try:
            self._repo.git.add(A=True)
            commit = self._repo.index.commit(message)
            return {"ok": True, "sha": commit.hexsha}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_last_commit_sha(self) -> Optional[str]:
        if self._repo:
            try:
                return self._repo.head.commit.hexsha
            except Exception:
                return None
        return None

    def push_branch(self, branch_name: str, github_token: str = "") -> dict:
        """Push branch to origin using temporary authenticated URL without persisting credentials."""
        if not self._repo:
            return {"ok": False, "error": "Git repo not available"}
        try:
            origin = self._repo.remote("origin")
        except Exception:
            return {"ok": False, "error": "No 'origin' remote configured for this repository"}

        orig_url = origin.url
        try:
            if github_token and orig_url.startswith("https://") and "@" not in orig_url:
                auth_url = orig_url.replace("https://", f"https://x-access-token:{github_token}@", 1)
                self._repo.git.push(auth_url, f"{branch_name}:{branch_name}")
            else:
                self._repo.git.push("origin", branch_name)
            return {"ok": True, "branch": branch_name}
        except Exception as exc:
            err = str(exc)
            if github_token:
                err = err.replace(github_token, "***")
            return {"ok": False, "error": err}

    def rollback_changes(self, target_branch: str = "") -> dict:
        """Revert uncommitted workspace changes or switch back to the base branch."""
        if not self._repo:
            return {"ok": False, "error": "Git repo not available"}
        try:
            self._repo.git.reset("--hard", "HEAD")
            self._repo.git.clean("-fd")
            current = self.current_branch()
            if current.startswith("forge/fix-"):
                candidates = [target_branch] if target_branch else ["main", "master"]
                for b in candidates:
                    if b and b in [h.name for h in self._repo.heads]:
                        self._repo.git.checkout(b)
                        try:
                            self._repo.delete_head(current, force=True)
                        except Exception:
                            pass
                        return {"ok": True, "reverted_from": current, "active_branch": b}
            return {"ok": True, "reverted_from": current, "active_branch": self.current_branch()}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ---- working tree utils -----------------------------------------------

    def read_file(self, rel_path: str) -> Optional[str]:
        full = os.path.join(self.local_path, rel_path)
        try:
            return Path(full).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return None

    def write_file(self, rel_path: str, content: str) -> None:
        full = os.path.join(self.local_path, rel_path)
        Path(full).write_text(content, encoding="utf-8")
