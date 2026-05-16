from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class DeveloperNode(BaseModel):
    gitlab_id: Optional[int] = None
    username: str
    name: str
    active: bool = True
    external: bool = False  # True for upstream/fork authors not in current project members
    expertise: dict[str, float] = Field(default_factory=dict)  # module_path -> score 0-1
    last_seen: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ModuleNode(BaseModel):
    path: str                           # e.g. "src/auth"
    language: Optional[str] = None
    owners: list[str] = Field(default_factory=list)   # gitlab usernames
    bus_factor: int = 0                 # number of meaningful contributors
    doc_coverage: float = 0.0          # 0-1
    last_commit_at: Optional[datetime] = None
    continuity_risk_score: float = 0.0  # 0-1, higher = more at risk
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class TaskNode(BaseModel):
    gitlab_iid: int                    # issue or MR internal id
    gitlab_id: int
    kind: str                          # "issue" | "merge_request"
    title: str
    assignee: Optional[str] = None    # gitlab username
    module_paths: list[str] = Field(default_factory=list)
    status: str = "open"
    created_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ContributionEdge(BaseModel):
    developer_username: str
    module_path: str
    commit_count: int = 0
    lines_changed: int = 0
    expertise_score: float = 0.0
    last_contribution_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    # Optional metadata for contributions originating outside project members
    external: bool = False
    developer_identity: Optional[str] = None  # freeform name/email for external contributors
