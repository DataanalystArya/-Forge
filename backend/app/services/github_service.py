import logging
from typing import Optional, List, Dict, Any
import httpx
from app.core.config import settings

logger = logging.getLogger("forge.github_service")

GITHUB_API_BASE = "https://api.github.com"
GITHUB_OAUTH_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_OAUTH_ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"


class GitHubService:
    @staticmethod
    def get_oauth_authorize_url(state: str, redirect_uri: Optional[str] = None) -> str:
        """Construct the GitHub OAuth authorization URL with least-privilege scopes."""
        params = [
            f"client_id={settings.GITHUB_CLIENT_ID}",
            f"scope=read:user,repo",
            f"state={state}",
        ]
        if redirect_uri:
            params.append(f"redirect_uri={redirect_uri}")
        return f"{GITHUB_OAUTH_AUTHORIZE_URL}?{'&'.join(params)}"

    @staticmethod
    def exchange_code_for_token(code: str, redirect_uri: Optional[str] = None) -> Optional[str]:
        """Exchange temporary OAuth code for GitHub user access token."""
        payload = {
            "client_id": settings.GITHUB_CLIENT_ID,
            "client_secret": settings.GITHUB_CLIENT_SECRET,
            "code": code,
        }
        if redirect_uri:
            payload["redirect_uri"] = redirect_uri

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(
                    GITHUB_OAUTH_ACCESS_TOKEN_URL,
                    json=payload,
                    headers={"Accept": "application/json"}
                )
                if res.status_code == 200:
                    data = res.json()
                    return data.get("access_token")
                logger.error(f"GitHub token exchange failed: {res.status_code} {res.text}")
                return None
        except Exception as e:
            logger.error(f"Exception during GitHub token exchange: {e}")
            return None

    @staticmethod
    def get_user_profile(token: str) -> Optional[Dict[str, Any]]:
        """Retrieve the authenticated GitHub user profile."""
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "FORGE-Autonomous-Platform"
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(f"{GITHUB_API_BASE}/user", headers=headers)
                if res.status_code == 200:
                    return res.json()
                logger.warning(f"Failed to fetch GitHub user: {res.status_code}")
                return None
        except Exception as e:
            logger.error(f"Error fetching GitHub profile: {e}")
            return None

    @staticmethod
    def list_repositories(token: str, page: int = 1, per_page: int = 50) -> List[Dict[str, Any]]:
        """List repositories accessible to the user (sorted by updated)."""
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "FORGE-Autonomous-Platform"
        }
        params = {
            "sort": "updated",
            "direction": "desc",
            "page": page,
            "per_page": per_page,
            "affiliation": "owner,collaborator,organization_member"
        }
        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.get(f"{GITHUB_API_BASE}/user/repos", headers=headers, params=params)
                if res.status_code == 200:
                    return res.json()
                logger.warning(f"Failed to fetch GitHub repos: {res.status_code} {res.text}")
                return []
        except Exception as e:
            logger.error(f"Error listing GitHub repositories: {e}")
            return []

    @staticmethod
    def get_repository_info(token: str, full_name: str) -> Optional[Dict[str, Any]]:
        """Fetch metadata for a specific repository."""
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "FORGE-Autonomous-Platform"
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(f"{GITHUB_API_BASE}/repos/{full_name}", headers=headers)
                if res.status_code == 200:
                    return res.json()
                return None
        except Exception as e:
            logger.error(f"Error fetching repo '{full_name}': {e}")
            return None
