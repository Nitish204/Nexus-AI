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
from typing import List, Optional  # not list[...]/X | None — SQLModel/Pydantic must actually
                          # evaluate field annotations to build the schema
                          # (unlike a decorative function return type),
                          # and list[...] (PEP 585, 3.9+) / X | None (PEP 604,
                          # 3.10+) genuinely don't exist on Python 3.8 at all —
                          # typing.List/typing.Optional work identically from
                          # Python 3.5 through 3.13+.

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
    password_hash: Optional[str] = None  # null for OAuth-only users
    provider: AuthProvider = AuthProvider.LOCAL
    avatar_url: str = ""
    created_at: datetime = utc_datetime_field()
    security_question: Optional[str] = None
    security_answer_hash: Optional[str] = None
    is_admin: bool = False
    # Two-factor auth (TOTP). totp_secret is set as soon as setup begins
    # but totp_enabled stays False until the user proves they actually
    # configured their authenticator app correctly (see POST
    # /api/auth/2fa/enable) — this avoids a user getting locked out of
    # their own account from a setup flow they never finished.
    # totp_backup_codes stores HASHES only (bcrypt_sha256, same as
    # passwords), one-time-use, JSON-encoded list — never the raw codes,
    # which are shown to the user exactly once at generation time.
    totp_secret: Optional[str] = None
    totp_enabled: bool = False
    totp_backup_codes: Optional[str] = None  # JSON list of hashes

    # Account lockout (see app/api/auth.py's /login handler). Missing
    # from this model despite the login route depending on both fields
    # unconditionally was a real bug — every login attempt crashed with
    # AttributeError before a migration/model fix ever shipped this.
    # failed_login_count resets to 0 on any successful login or once a
    # lockout expires; locked_until is None until the threshold is hit.
    failed_login_count: int = 0
    locked_until: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class Project(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    name: str
    name_is_default: bool = True
    description: str = ""
    owner_id: str = Field(index=True)
    created_at: datetime = utc_datetime_field()
    updated_at: datetime = utc_datetime_field()

    tasks: List["Task"] = Relationship(back_populates="project")
    files: List["GeneratedFile"] = Relationship(back_populates="project")


class Task(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    title: str
    description: str
    assigned_role: AgentRole
    status: TaskStatus = TaskStatus.PENDING
    depends_on: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    result_summary: str = ""
    created_at: datetime = utc_datetime_field()
    updated_at: datetime = utc_datetime_field()

    project: Project = Relationship(back_populates="tasks")
    messages: List["AgentMessage"] = Relationship(back_populates="task")


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
    id: str = Field(default_factory=new_id, primary_key=True)
    slug: str = Field(index=True, unique=True)
    name: str
    description: str = ""
    author: str = ""
    category: str = "integration"
    version: str = "0.1.0"
    config: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = utc_datetime_field()
    status: str = "approved"  # pending | approved | rejected
    submitted_by: Optional[str] = Field(default=None, foreign_key="user.id")
    reviewed_by: Optional[str] = Field(default=None, foreign_key="user.id")
    review_note: str = ""


class ApiKey(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    owner_id: str = Field(foreign_key="user.id", index=True)
    name: str = "API Key"
    key_hash: str = Field(index=True, unique=True)
    key_prefix: str
    created_at: datetime = utc_datetime_field()
    last_used_at: Optional[datetime] = None
    revoked: bool = False


class ProjectPlugin(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    plugin_id: str = Field(foreign_key="plugin.id", index=True)
    enabled_at: datetime = utc_datetime_field()


class PushSubscription(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    endpoint: str = Field(unique=True)
    p256dh: str
    auth: str
    created_at: datetime = utc_datetime_field()


class TokenUsage(SQLModel, table=True):
    """
    One row per completed (or failed-after-streaming) LLM call made by
    an agent. This is the raw ledger the cost dashboard
    (GET /api/projects/{id}/analytics/cost) aggregates — kept at this
    granularity, rather than a running counter on Project, so spend can
    be broken down by role/model/task after the fact and so a bug in
    the aggregation query never has to be "fixed" by re-deriving lost
    data.
    """
    # protected_namespaces=() silences pydantic's warning that
    # "model_name" collides with its reserved "model_" prefix (used for
    # pydantic's own model_ methods) — it's a real field, not a
    # BaseModel method, so the collision is harmless here.
    model_config = {"protected_namespaces": ()}

    id: str = Field(default_factory=new_id, primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    role: AgentRole
    model_name: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    # True when cost_usd was computed against the fallback pricing rate
    # because `model_name` wasn't in the configured pricing table (see
    # app/core/llm_pricing.py) — surfaced so the UI can show "~$x.xx"
    # instead of implying penny-accurate billing data.
    is_estimated: bool = False
    created_at: datetime = utc_datetime_field()


class Deployment(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    provider: str
    status: str = "pending"
    url: str = ""
    log: str = ""
    created_at: datetime = utc_datetime_field()
