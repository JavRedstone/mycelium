from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
import uuid


class DeveloperNode(BaseModel):
    gitlab_id: Optional[int] = None
    username: str
    name: str
    active: bool = True
    external: bool = False  # True for upstream/fork authors not in current project members
    expertise: dict[str, float] = Field(default_factory=dict)  # module_path -> score 0-1
    first_seen: Optional[datetime] = None   # exact date of first observed commit
    last_seen: Optional[datetime] = None    # exact date of most recent observed commit
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    demo: bool = False  # True for seeded simulation entries — safe to bulk-delete


class ModuleNode(BaseModel):
    """Observational state for a module — measurements only.

    Per PROJECT_IDEA, there is no scalar risk model. Severity and concern
    are qualitative and live in Finding records produced by the analyst,
    not as numbers stored on the module.
    """
    path: str                                    # e.g. "src/auth"
    language: Optional[str] = None
    owners: list[str] = Field(default_factory=list)   # declared GitLab usernames
    bus_factor: int = 0                          # measurement: contributors covering 80% of commits
    last_commit_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    demo: bool = False  # True for seeded simulation entries — safe to bulk-delete


class Finding(BaseModel):
    """Qualitative continuity finding produced by the analyst agent.

    Findings replace risk scores. Each finding describes a structural pattern
    in the knowledge graph and what the agent thinks should be done about it.
    No severity buckets — the narrative carries the meaning.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_id: Optional[str] = None
    subject: str                                 # module path, "members/<name>", or "upstream sync"
    concern_type: str                            # descriptive: "knowledge_concentration",
                                                 # "fragile_documentation", "fading_contributor",
                                                 # "upstream_dominance", "stalled_work",
                                                 # "undeclared_ownership", "ci_instability", etc.
    narrative: str                               # qualitative reasoning, not a label
    evidence: list[str] = Field(default_factory=list)         # references to investigator findings / signals
    recommended_actions: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


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
    demo: bool = False  # True for seeded simulation entries — safe to bulk-delete


class ContributionHistory(BaseModel):
    """Monthly commit count per (developer, module) — the timeline backbone."""
    developer_username: str
    module_path: str
    year_month: str          # "YYYY-MM"
    commit_count: int = 0
    external: bool = False
    demo: bool = False


class ActionRecord(BaseModel):
    """A single action taken by the act agent during a pipeline run."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str
    executed_at: datetime = Field(default_factory=datetime.utcnow)
    tool: str               # MCP tool name, e.g. "create_issue", "add_comment"
    detail: str             # human-readable description, e.g. "#42 Knowledge transfer..."
    success: bool = True
    run_summary: Optional[str] = None  # agent's overall text for this run
