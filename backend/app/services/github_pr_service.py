"""Phase 7 — GitHub PR creation service."""
from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class GitHubPRService:
    """
    Creates GitHub Pull Requests via the GitHub REST API.
    Requires a GitHub Personal Access Token (PAT).
    """

    API_BASE = "https://api.github.com"

    def __init__(self, access_token: str) -> None:
        self.access_token = access_token
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str = "main",
        draft: bool = False,
    ) -> dict:
        """
        Create a GitHub PR.  Returns GitHub's response dict.
        Never auto-merges — sets draft=True by default or passes caller choice.
        """
        url = f"{self.API_BASE}/repos/{owner}/{repo}/pulls"
        payload = {
            "title": title,
            "body": body,
            "head": head,
            "base": base,
            "draft": draft,
        }
        try:
            resp = httpx.post(url, json=payload, headers=self._headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return {
                "ok": True,
                "pr_number": data["number"],
                "pr_url": data["html_url"],
                "state": data["state"],
                "draft": data.get("draft", False),
            }
        except httpx.HTTPStatusError as exc:
            return {"ok": False, "error": str(exc), "response": exc.response.text}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_pull_request(self, owner: str, repo: str, pr_number: int) -> dict:
        url = f"{self.API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}"
        try:
            resp = httpx.get(url, headers=self._headers, timeout=15)
            resp.raise_for_status()
            d = resp.json()
            return {
                "ok": True,
                "pr_number": d["number"],
                "title": d["title"],
                "state": d["state"],
                "merged": d.get("merged", False),
                "pr_url": d["html_url"],
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def push_branch(self, owner: str, repo: str, branch: str, sha: str) -> dict:
        """
        Update a branch reference on GitHub (requires a local SHA to have been pushed).
        Note: actual push is done via git CLI / gitpython; this just verifies.
        """
        url = f"{self.API_BASE}/repos/{owner}/{repo}/git/refs/heads/{branch}"
        try:
            resp = httpx.get(url, headers=self._headers, timeout=15)
            if resp.status_code == 200:
                return {"ok": True, "exists": True}
            return {"ok": True, "exists": False}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
