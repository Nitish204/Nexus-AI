"""
NEXUS — Data model.

Design note: agents don't call each other directly. They read and write
to this shared "blackboard" (Project -> Task -> AgentMessage / GeneratedFile).
This keeps the multi-agent system decoupled, inspectable, and replayable —
every decision an agent made is a row in a table, not a lost function call.
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, JSON, DateTime


def now() -> datetime:
    # IMPORTANT: datetime.utcnow() (the previous implementation here)
    # returns UTC time but strips the timezone marker entirely — the
    # resulting value is indistinguishable from local time once
    # serialized to JSON. Browsers then parse it as if it WERE already
    # local time, silently shifting every displayed timestamp by
    # exactly the user's UTC offset (e.g. +5:30 for India) — this was
    # the root cause of timestamps looking hours off in the sidebar.
    # now(timezone.utc) is timezone-AWARE and serializes with an
    # explicit UTC marker, which JS correctly converts to local time.
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


def utc_datetime_field(**kwargs):
    """Shared Field() for created_at/updated_at columns. Explicitly
    configures the underlying SQL column as TIMESTAMPTZ (timezone-aware)
    rather than SQLAlchemy's default TIMESTAMP WITHOUT TIME ZONE — the
    latter silently strips timezone info on every save/read, which
    would reintroduce the same bug now() alone was fixed for, just one
    layer deeper (at the database column level instead of the Python
    function level)."""
    return Field(default_factory=now, sa_column=Column(DateTime(timezone=True)), **kwargs)


class AgentRole(str, enum.Enum):
    PRODUCT_MANAGER = "product_manager"
    BACKEND_ENGINEER = "backend_engineer"
    FRONTEND_ENGINEER = "frontend_engineer"
    QA_ENGINEER = "qa_engineer"
    DEVOPS_ENGINEER = "devops_engineer"


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    IN_REVIEW = "in_review"
    DONE = "done"
    FAILED = "failed"


class AuthProvider(str, enum.Enum):
    LOCAL = "local"
    GOOGLE = "google"
    GITHUB = "github"


class User(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    email: str = Field(index=True, unique=True)
    name: str = ""
    password_hash: str | None = None  # null for OAuth-only users
    provider: AuthProvider = AuthProvider.LOCAL
    avatar_url: str = ""
    created_at: datetime = utc_datetime_field()


class Project(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    name: str
    # True until the user explicitly renames the project (see the
    # rename endpoint in api/projects.py) or the orchestrator
    # auto-renames it from the first command. Lets the orchestrator
    # safely auto-name a fresh project from its first request without
    # ever silently overwriting a name the user already chose.
    name_is_default: bool = True
    description: str = ""
    owner_id: str = Field(index=True)
    created_at: datetime = utc_datetime_field()
    updated_at: datetime = utc_datetime_field()

    tasks: list["Task"] = Relationship(back_populates="project")
    files: list["GeneratedFile"] = Relationship(back_populates="project")


class Task(SQLModel, table=True):
    """A unit of work assigned to one agent. The PM agent creates these;
    engineer agents consume and complete them."""
    id: str = Field(default_factory=new_id, primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    title: str
    description: str
    assigned_role: AgentRole
    status: TaskStatus = TaskStatus.PENDING
    depends_on: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    result_summary: str = ""
    created_at: datetime = utc_datetime_field()
    updated_at: datetime = utc_datetime_field()

    project: Project = Relationship(back_populates="tasks")
    messages: list["AgentMessage"] = Relationship(back_populates="task")


class AgentMessage(SQLModel, table=True):
    """Every thought/action an agent takes gets logged here. This is what
    powers the live activity feed and lets us replay a project's history."""
    id: str = Field(default_factory=new_id, primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    role: AgentRole
    content: str
    message_type: str = "reasoning"  # reasoning | code | tool_call | error | status
    created_at: datetime = utc_datetime_field()

    task: Task = Relationship(back_populates="messages")


class GeneratedFile(SQLModel, table=True):
    """Virtual file tree for a project. Content lives here, not on disk,
    so the live editor and the knowledge graph both read from one source
    of truth."""
    id: str = Field(default_factory=new_id, primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    path: str  # e.g. "backend/auth/views.py"
    content: str
    language: str = "python"
    written_by: AgentRole
    version: int = 1
    created_at: datetime = utc_datetime_field()
    updated_at: datetime = utc_datetime_field()

    project: Project = Relationship(back_populates="files")


class GraphEdge(SQLModel, table=True):
    """Knowledge graph edges: file -> imports -> file, file -> defines -> api,
    api -> reads/writes -> table, etc. Kept relational (not a separate graph
    DB) so Phase-0/1 stays deployable as a single Postgres instance; can be
    mirrored into Neo4j later without changing the write path."""
    id: str = Field(default_factory=new_id, primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    source: str
    target: str
    relation: str  # imports | defines_api | reads_table | writes_table | calls
    created_at: datetime = utc_datetime_field()


class AnalysisResult(SQLModel, table=True):
    """Output of static analysis (radon/bandit/ruff) per file, for the
    live quality/security dashboard."""
    id: str = Field(default_factory=new_id, primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    file_path: str
    complexity_score: float = 0.0
    security_issues: int = 0
    lint_issues: int = 0
    raw_report: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = utc_datetime_field()


class Deployment(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    provider: str
    status: str = "pending"  # pending | building | live | failed
    url: str = ""
    log: str = ""
    created_at: datetime = utc_datetime_field()
