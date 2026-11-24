import re
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator


REPO_NAME_REGEX = re.compile(r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$")


class RepositoryBase(BaseModel):
    full_name: str = Field(..., json_schema_extra={"example": "facebook/react"})
    description: Optional[str] = None
    default_branch: str = "main"
    is_private: bool = False
    clone_url: Optional[str] = None

    @field_validator("full_name")
    @classmethod
    def validate_repo_name(cls, v: str) -> str:
        v = v.strip()
        if not REPO_NAME_REGEX.match(v) or ".." in v:
            raise ValueError(
                "Invalid repository name format. Must be in 'owner/repo' format without path traversal or invalid characters."
            )
        return v


class RepositoryCreate(RepositoryBase):
    pass


class RepositoryResponse(RepositoryBase):
    id: str
    user_id: str
    github_repo_id: Optional[str] = None
    status: str
    total_files: int = 0
    total_lines: int = 0
    languages_json: Optional[str] = None
    indexed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class RepositoryListResponse(BaseModel):
    items: List[RepositoryResponse]
    total: int


class IndexingJobResponse(BaseModel):
    id: str
    repository_id: str
    status: str
    indexed_files: int
    total_files: int
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
