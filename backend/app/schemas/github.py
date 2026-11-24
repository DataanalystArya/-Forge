from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


class GitHubConnectionStatus(BaseModel):
    is_connected: bool
    username: Optional[str] = None
    avatar_url: Optional[str] = None
    github_user_id: Optional[str] = None
    connected_at: Optional[datetime] = None


class GitHubConnectPATRequest(BaseModel):
    token: str = Field(..., min_length=10, max_length=255, description="GitHub Personal Access Token (classic or fine-grained)")


class GitHubRepoItem(BaseModel):
    id: int
    name: str
    full_name: str
    description: Optional[str] = None
    private: bool
    html_url: str
    clone_url: str
    default_branch: str
    stargazers_count: int = 0
    language: Optional[str] = None
    updated_at: Optional[str] = None


class GitHubRepoListResponse(BaseModel):
    repositories: List[GitHubRepoItem]
    total: int
