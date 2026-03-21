"""
SlothOps Engine — Database Layer
Async SQLite via aiosqlite.  Provides CRUD operations for the issues table.
Call `init_db()` once at startup to create the table and indexes.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

import aiosqlite

from models import IssueRecord

# Default path – overridden at runtime via config.DATABASE_PATH
_DEFAULT_DB = "./slothops.db"

# ── SQL Statements ───────────────────────────────────────────────────────

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS issues (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL DEFAULT 'default_workspace',
    fingerprint TEXT NOT NULL,
    error_type TEXT,
    error_message TEXT,
    file_path TEXT,
    function_name TEXT,
    line_number INTEGER,
    stack_trace TEXT,
    raw_payload TEXT,
    occurrence_count INTEGER DEFAULT 1,
    classification TEXT DEFAULT 'unknown',
    confidence TEXT,
    status TEXT DEFAULT 'received',
    fix_pr_url TEXT,
    fix_pr_branch TEXT,
    root_cause TEXT,
    recommendation TEXT,
    previous_fix_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_CREATE_WORKSPACES = """
CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_CREATE_WORKSPACE_USERS = """
CREATE TABLE IF NOT EXISTS workspace_users (
    workspace_id TEXT,
    user_id TEXT,
    role TEXT DEFAULT 'admin',
    PRIMARY KEY (workspace_id, user_id)
);
"""

_CREATE_INTEGRATIONS = """
CREATE TABLE IF NOT EXISTS integrations (
    workspace_id TEXT PRIMARY KEY,
    github_installation_id TEXT,
    sentry_webhook_secret TEXT
);
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_fingerprint ON issues(fingerprint);",
    "CREATE INDEX IF NOT EXISTS idx_status ON issues(status);",
]


# ── Helpers ──────────────────────────────────────────────────────────────

def _row_to_issue(row: aiosqlite.Row) -> IssueRecord:
    """Convert a sqlite3.Row to an IssueRecord."""
    d = dict(row)
    # Parse datetime strings back
    for dt_field in ("created_at", "updated_at"):
        val = d.get(dt_field)
        if isinstance(val, str):
            try:
                d[dt_field] = datetime.fromisoformat(val)
            except (ValueError, TypeError):
                d[dt_field] = datetime.utcnow()
    return IssueRecord(**d)


# ── Public API ───────────────────────────────────────────────────────────

async def init_db(db_path: str = _DEFAULT_DB) -> None:
    """Create the issues table and indexes if they don't exist."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(_CREATE_TABLE)
        await db.execute(_CREATE_WORKSPACES)
        await db.execute(_CREATE_USERS)
        await db.execute(_CREATE_WORKSPACE_USERS)
        await db.execute(_CREATE_INTEGRATIONS)
        for idx_sql in _CREATE_INDEXES:
            await db.execute(idx_sql)
        await db.commit()


async def create_issue(issue: IssueRecord, db_path: str = _DEFAULT_DB) -> None:
    """Insert a new issue record."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO issues (
                id, workspace_id, fingerprint, error_type, error_message, file_path,
                function_name, line_number, stack_trace, raw_payload,
                occurrence_count, classification, confidence, status,
                fix_pr_url, fix_pr_branch, root_cause, recommendation,
                previous_fix_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                issue.id,
                issue.workspace_id,
                issue.fingerprint,
                issue.error_type,
                issue.error_message,
                issue.file_path,
                issue.function_name,
                issue.line_number,
                issue.stack_trace,
                issue.raw_payload,
                issue.occurrence_count,
                issue.classification,
                issue.confidence,
                issue.status,
                issue.fix_pr_url,
                issue.fix_pr_branch,
                issue.root_cause,
                issue.recommendation,
                issue.previous_fix_id,
                issue.created_at.isoformat(),
                issue.updated_at.isoformat(),
            ),
        )
        await db.commit()


async def get_issue(issue_id: str, workspace_id: str, db_path: str = _DEFAULT_DB) -> Optional[IssueRecord]:
    """Fetch a single issue by its ID, scoped to a workspace."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM issues WHERE id = ? AND workspace_id = ?", (issue_id, workspace_id)) as cursor:
            row = await cursor.fetchone()
            return _row_to_issue(row) if row else None


async def get_issue_by_fingerprint(fingerprint: str, workspace_id: str, db_path: str = _DEFAULT_DB) -> Optional[IssueRecord]:
    """Fetch the most recent issue with a given fingerprint for a workspace."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM issues WHERE fingerprint = ? AND workspace_id = ? ORDER BY created_at DESC LIMIT 1",
            (fingerprint, workspace_id),
        ) as cursor:
            row = await cursor.fetchone()
            return _row_to_issue(row) if row else None


async def update_issue_status(
    issue_id: str,
    db_path: str = _DEFAULT_DB,
    **kwargs: str | int | None,
) -> None:
    """Update one or more columns on an issue record."""
    if not kwargs:
        return
    kwargs["updated_at"] = datetime.utcnow().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [issue_id]
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            f"UPDATE issues SET {set_clause} WHERE id = ?",
            values,
        )
        await db.commit()


async def increment_occurrence(
    issue_id: str, workspace_id: str, db_path: str = _DEFAULT_DB
) -> None:
    """Bump occurrence_count by 1."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE issues SET occurrence_count = occurrence_count + 1, updated_at = ? WHERE id = ? AND workspace_id = ?",
            (datetime.utcnow().isoformat(), issue_id, workspace_id),
        )
        await db.commit()


async def create_user(user, db_path: str = _DEFAULT_DB) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO users (id, email, hashed_password, created_at) VALUES (?, ?, ?, ?)",
            (user.id, user.email, user.hashed_password, user.created_at.isoformat())
        )
        await db.commit()

async def get_user_by_email(email: str, db_path: str = _DEFAULT_DB):
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE email = ?", (email,)) as cursor:
            row = await cursor.fetchone()
            if row:
                from models import User
                d = dict(row)
                d["created_at"] = datetime.fromisoformat(d["created_at"]) if isinstance(d.get("created_at"), str) else d.get("created_at", datetime.utcnow())
                return User(**d)
            return None

async def create_workspace(workspace, db_path: str = _DEFAULT_DB) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO workspaces (id, name, created_at) VALUES (?, ?, ?)",
            (workspace.id, workspace.name, workspace.created_at.isoformat())
        )
        await db.commit()

async def add_user_to_workspace(workspace_id: str, user_id: str, role: str = "admin", db_path: str = _DEFAULT_DB) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO workspace_users (workspace_id, user_id, role) VALUES (?, ?, ?)",
            (workspace_id, user_id, role)
        )
        await db.commit()

async def get_user_workspaces(user_id: str, db_path: str = _DEFAULT_DB):
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT w.* FROM workspaces w JOIN workspace_users wu ON w.id = wu.workspace_id WHERE wu.user_id = ?",
            (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            res = []
            from models import Workspace
            for row in rows:
                d = dict(row)
                d["created_at"] = datetime.fromisoformat(d["created_at"]) if isinstance(d.get("created_at"), str) else d.get("created_at", datetime.utcnow())
                res.append(Workspace(**d))
            return res

async def list_workspaces(db_path: str = _DEFAULT_DB):
    """Return all workspaces (used for auto-linking GitHub installations)."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM workspaces") as cursor:
            rows = await cursor.fetchall()
            res = []
            from models import Workspace
            for row in rows:
                d = dict(row)
                d["created_at"] = datetime.fromisoformat(d["created_at"]) if isinstance(d.get("created_at"), str) else d.get("created_at", datetime.utcnow())
                res.append(Workspace(**d))
            return res

async def get_integration(workspace_id: str, db_path: str = _DEFAULT_DB):
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM integrations WHERE workspace_id = ?", (workspace_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                from models import Integration
                return Integration(**dict(row))
            return None

async def upsert_integration(integration, db_path: str = _DEFAULT_DB) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO integrations (workspace_id, github_installation_id, sentry_webhook_secret) 
               VALUES (?, ?, ?) 
               ON CONFLICT(workspace_id) DO UPDATE SET 
               github_installation_id=excluded.github_installation_id,
               sentry_webhook_secret=excluded.sentry_webhook_secret""",
            (integration.workspace_id, integration.github_installation_id, integration.sentry_webhook_secret)
        )
        await db.commit()


async def list_issues(workspace_id: str, db_path: str = _DEFAULT_DB) -> list[IssueRecord]:
    """Return all issues for a specific workspace ordered by most recent first."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM issues WHERE workspace_id = ? ORDER BY created_at DESC", (workspace_id,)) as cursor:
            rows = await cursor.fetchall()
            return [_row_to_issue(row) for row in rows]
