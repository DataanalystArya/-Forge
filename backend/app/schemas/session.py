from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class DebuggingSessionCreate(BaseModel):
    repository_id: str
    title: str = Field(..., min_length=3, max_length=255)
    description: str = Field(..., min_length=5)
    error_logs: Optional[str] = None


class PatchResponse(BaseModel):
    id: str
    session_id: str
    iteration: int
    diff_content: str
    affected_files_json: Optional[str] = None
    rationale: Optional[str] = None
    is_applied: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TestExecutionResponse(BaseModel):
    id: str
    session_id: str
    patch_id: Optional[str] = None
    exit_code: int
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    passed_count: int
    failed_count: int
    duration_ms: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SecurityFindingResponse(BaseModel):
    id: str
    repository_id: str
    session_id: Optional[str] = None
    rule_id: str
    severity: str
    file_path: str
    line_number: Optional[int] = None
    message: str
    recommendation: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PullRequestResponse(BaseModel):
    id: str
    session_id: str
    repository_id: str
    branch_name: str
    pr_number: Optional[int] = None
    pr_url: Optional[str] = None
    title: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DebuggingSessionResponse(BaseModel):
    id: str
    repository_id: str
    user_id: str
    title: str
    description: str
    error_logs: Optional[str] = None
    status: str
    current_phase: str
    retry_count: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    patches: List[PatchResponse] = []
    test_executions: List[TestExecutionResponse] = []
    security_findings: List[SecurityFindingResponse] = []

    model_config = ConfigDict(from_attributes=True)
