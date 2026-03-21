"""
SlothOps Engine — Pydantic Models & Enums
Defines the internal data contract used by every module in the pipeline.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────────

class Classification(str, enum.Enum):
    CODE = "code"
    INFRA = "infra"
    DEPENDENCY = "dependency"
    UNKNOWN = "unknown"


class Confidence(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class IssueStatus(str, enum.Enum):
    RECEIVED = "received"
    TRIAGING = "triaging"
    CLASSIFIED = "classified"
    FIXING = "fixing"
    PR_CREATED = "pr_created"
    PR_MERGED = "pr_merged"
    FIX_INEFFECTIVE = "fix_ineffective"
    IGNORED = "ignored"
    RECOMMENDATION_ONLY = "recommendation_only"
    FIXING_FAILED = "fixing_failed"
    PR_CREATION_FAILED = "pr_creation_failed"


class DedupeAction(str, enum.Enum):
    CREATE = "CREATE"
    SKIP = "SKIP"
    RETRIGGER = "RETRIGGER"


# ── Core Issue Record ────────────────────────────────────────────────────

class IssueRecord(BaseModel):
    """The single data object that flows through the entire pipeline."""

    id: str
    workspace_id: str = "default_workspace"
    fingerprint: str = ""
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    file_path: Optional[str] = None
    function_name: Optional[str] = None
    line_number: Optional[int] = None
    stack_trace: Optional[str] = None
    raw_payload: Optional[str] = None
    occurrence_count: int = 1
    classification: str = Classification.UNKNOWN.value
    confidence: Optional[str] = None
    status: str = IssueStatus.RECEIVED.value
    fix_pr_url: Optional[str] = None
    fix_pr_branch: Optional[str] = None
    root_cause: Optional[str] = None
    recommendation: Optional[str] = None
    previous_fix_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ── SaaS Multi-Tenant Models ──────────────────────────────────────────────────

class User(BaseModel):
    id: str
    email: str
    hashed_password: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Workspace(BaseModel):
    id: str
    name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class WorkspaceUser(BaseModel):
    workspace_id: str
    user_id: str
    role: str = "admin"

class Integration(BaseModel):
    workspace_id: str
    github_installation_id: Optional[str] = None
    sentry_webhook_secret: Optional[str] = None


# ── LLM Response Models ─────────────────────────────────────────────────

class FileChange(BaseModel):
    """One file changed by the LLM fix."""

    path: str
    original_content: str
    fixed_content: str
    explanation: str


class LLMFixResponse(BaseModel):
    """Parsed JSON response from Gemini 2.5 Pro."""

    root_cause: str
    confidence: str  # high | medium | low
    files_changed: list[FileChange]
    pr_title: str
    pr_body: str
