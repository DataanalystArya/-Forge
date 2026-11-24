from typing import List, Optional, Any
from pydantic import BaseModel


class FileTreeNode(BaseModel):
    name: str
    path: str
    type: str  # "file" or "directory"
    size: Optional[int] = None
    language: Optional[str] = None
    children: Optional[List["FileTreeNode"]] = None


class FileContentResponse(BaseModel):
    path: str
    name: str
    language: str
    size: int
    lines: int
    content: str


class ArtifactItemResponse(BaseModel):
    id: str
    file_path: str
    language: Optional[str]
    entity_type: str
    entity_name: Optional[str]
    start_line: Optional[int]
    end_line: Optional[int]


class ArtifactListResponse(BaseModel):
    artifacts: List[ArtifactItemResponse]
    total: int
