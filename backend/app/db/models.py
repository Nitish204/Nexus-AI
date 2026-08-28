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
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


def utc_datetime_field(**kwargs):
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
    password_hash: str | None = None
    provider: AuthProvider = AuthProvider.LOCAL
    avatar_url: str = ""
    created_at: datetime = utc_datetime_field()
    security_question: str | None = None
    security_answer_hash: str | None = None


class Project(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    name: str
    name_is_default: bool = True
    description: str = ""
    owner_id: str = Field(index=True)
    created_at: datetime = utc_datetime_field()
    updated_at: datetime = utc_datetime_field()

    tasks: list["Task"] = Relationship(back_populates="project")
    files: list["GeneratedFile"] = Relationship(back_populates="project")


class Task(SQLModel, table=True):
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
    id: str = Field(default_factory=new_id, primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    role: AgentRole
    content: str
    message_type: str = "reasoning"
    created_at: datetime = utc_datetime_field()

    task: Task = Relationship(back_populates="messages")


class GeneratedFile(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    path: str
    content: str
    language: str = "python"
    written_by: AgentRole
    version: int = 1
    created_at: datetime = utc_datetime_field()
    updated_at: datetime = utc_datetime_field()

    project: Project = Relationship(back_populates="files")


class GraphEdge(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    source: str
    target: str
    relation: str
    created_at: datetime = utc_datetime_field()


class AnalysisResult(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    file_path: str
    complexity_score: float = 0.0
    security_issues: int = 0
    lint_issues: int = 0
    raw_report: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = utc_datetime_field()


class Plugin(SQLModel, table=True):
    """Marketplace catalog entry — a packaged extension (extra agent,
    prompt template, integration) that a project owner can enable."""
    id: str = Field(default_factory=new_id, primary_key=True)
    slug: str = Field(index=True, unique=True)
    name: str
    description: str = ""
    author: str = ""
    category: str = "integration"  # integration | agent | template | theme
    version: str = "0.1.0"
    config: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = utc_datetime_field()


class ProjectPlugin(SQLModel, table=True):
    """Join table: which plugins a given project has enabled."""
    id: str = Field(default_factory=new_id, primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    plugin_id: str = Field(foreign_key="plugin.id", index=True)
    enabled_at: datetime = utc_datetime_field()


class Deployment(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    provider: str
    status: str = "pending"
    url: str = ""
    log: str = ""
    created_at: datetime = utc_datetime_field()
