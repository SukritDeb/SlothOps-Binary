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

_CREATE_DEVELOPER_CONFIGS = """
CREATE TABLE IF NOT EXISTS developer_configs (
    workspace_id TEXT PRIMARY KEY,
    config_json TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_CREATE_QA_REPORTS = """
CREATE TABLE IF NOT EXISTS qa_reports (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    pr_number INTEGER NOT NULL,
    pr_url TEXT,
    commit_sha TEXT,
    repo_name TEXT,
    static_analysis TEXT,
    functionality TEXT,
    stress_test TEXT,
    vapt TEXT,
    regression TEXT,
    performance TEXT,
    overall_status TEXT DEFAULT 'running',
    summary TEXT,
    email_sent_to TEXT,
    email_sent_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_CREATE_QA_CONFIGS = """
CREATE TABLE IF NOT EXISTS qa_configs (
    workspace_id TEXT PRIMARY KEY,
    config_json TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_CREATE_ROLLBACKS = """
CREATE TABLE IF NOT EXISTS rollbacks (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    failed_commit_sha TEXT NOT NULL,
    rolled_back_to_sha TEXT,
    backup_branch TEXT,
    pr_number INTEGER,
    pr_url TEXT,
    failure_reason TEXT,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_CREATE_RESOLUTIONS = """
CREATE TABLE IF NOT EXISTS resolutions (
    id TEXT PRIMARY KEY,
    rollback_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    backup_branch TEXT NOT NULL,
    resolution_pr_url TEXT,
    resolution_pr_number INTEGER,
    attempt_number INTEGER DEFAULT 1,
    build_error_log TEXT,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
        await db.execute(_CREATE_TABLE)
        await db.execute(_CREATE_WORKSPACES)
        await db.execute(_CREATE_USERS)
        await db.execute(_CREATE_WORKSPACE_USERS)
        await db.execute(_CREATE_INTEGRATIONS)
        await db.execute(_CREATE_DEVELOPER_CONFIGS)
        await db.execute(_CREATE_QA_REPORTS)
        await db.execute(_CREATE_QA_CONFIGS)
        await db.execute(_CREATE_ROLLBACKS)
        await db.execute(_CREATE_RESOLUTIONS)
        for idx_sql in _CREATE_INDEXES:
            await db.execute(idx_sql)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_qa_reports_workspace ON qa_reports(workspace_id);"
        )
        await db.commit()


async def create_issue(issue: IssueRecord, db_path: str = _DEFAULT_DB) -> None:
    """Insert a new issue record."""
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
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
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM issues WHERE id = ? AND workspace_id = ?", (issue_id, workspace_id)) as cursor:
            row = await cursor.fetchone()
            return _row_to_issue(row) if row else None


async def get_issue_by_fingerprint(fingerprint: str, workspace_id: str, db_path: str = _DEFAULT_DB) -> Optional[IssueRecord]:
    """Fetch the most recent issue with a given fingerprint for a workspace."""
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
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
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
        await db.execute(
            f"UPDATE issues SET {set_clause} WHERE id = ?",
            values,
        )
        await db.commit()


async def increment_occurrence(
    issue_id: str, workspace_id: str, db_path: str = _DEFAULT_DB
) -> None:
    """Bump occurrence_count by 1."""
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
        await db.execute(
            "UPDATE issues SET occurrence_count = occurrence_count + 1, updated_at = ? WHERE id = ? AND workspace_id = ?",
            (datetime.utcnow().isoformat(), issue_id, workspace_id),
        )
        await db.commit()


async def create_user(user, db_path: str = _DEFAULT_DB) -> None:
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
        await db.execute(
            "INSERT INTO users (id, email, hashed_password, created_at) VALUES (?, ?, ?, ?)",
            (user.id, user.email, user.hashed_password, user.created_at.isoformat())
        )
        await db.commit()

async def get_user_by_email(email: str, db_path: str = _DEFAULT_DB):
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
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
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
        await db.execute(
            "INSERT INTO workspaces (id, name, created_at) VALUES (?, ?, ?)",
            (workspace.id, workspace.name, workspace.created_at.isoformat())
        )
        await db.commit()

async def add_user_to_workspace(workspace_id: str, user_id: str, role: str = "admin", db_path: str = _DEFAULT_DB) -> None:
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
        await db.execute(
            "INSERT INTO workspace_users (workspace_id, user_id, role) VALUES (?, ?, ?)",
            (workspace_id, user_id, role)
        )
        await db.commit()

async def get_user_workspaces(user_id: str, db_path: str = _DEFAULT_DB):
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
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

async def get_workspace_by_installation_id(installation_id: str, db_path: str = _DEFAULT_DB) -> Optional[str]:
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
        async with db.execute(
            "SELECT workspace_id FROM integrations WHERE github_installation_id = ?",
            (str(installation_id),)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def list_workspaces(db_path: str = _DEFAULT_DB):
    """Return all workspaces (used for auto-linking GitHub installations)."""
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
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
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM integrations WHERE workspace_id = ?", (workspace_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                from models import Integration
                return Integration(**dict(row))
            return None

async def upsert_integration(integration, db_path: str = _DEFAULT_DB) -> None:
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
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
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM issues WHERE workspace_id = ? ORDER BY created_at DESC", (workspace_id,)) as cursor:
            rows = await cursor.fetchall()
            return [_row_to_issue(row) for row in rows]


async def upsert_developer_config(workspace_id: str, config_json: str, db_path: str = _DEFAULT_DB) -> None:
    """Save or update developer.json preferences for a workspace."""
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
        await db.execute(
            """INSERT INTO developer_configs (workspace_id, config_json, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(workspace_id) DO UPDATE SET
               config_json=excluded.config_json,
               updated_at=excluded.updated_at""",
            (workspace_id, config_json, datetime.utcnow().isoformat())
        )
        await db.commit()


async def get_developer_config(workspace_id: str, db_path: str = _DEFAULT_DB) -> dict | None:
    """Retrieve developer.json preferences for a workspace."""
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT config_json FROM developer_configs WHERE workspace_id = ?", (workspace_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return json.loads(row["config_json"])
            return None


# ── QA Agent CRUD ───────────────────────────────────────────────────────

async def create_qa_report(report, db_path: str = _DEFAULT_DB) -> None:
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
        await db.execute(
            """INSERT INTO qa_reports (
                id, workspace_id, pr_number, pr_url, commit_sha, repo_name,
                static_analysis, functionality, stress_test, vapt, regression,
                performance, overall_status, summary, email_sent_to, email_sent_at, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                report.id, report.workspace_id, report.pr_number, report.pr_url,
                report.commit_sha, report.repo_name,
                json.dumps(report.static_analysis) if report.static_analysis else None,
                json.dumps(report.functionality) if report.functionality else None,
                json.dumps(report.stress_test) if report.stress_test else None,
                json.dumps(report.vapt) if report.vapt else None,
                json.dumps(report.regression) if report.regression else None,
                json.dumps(report.performance) if report.performance else None,
                report.overall_status, report.summary, report.email_sent_to,
                report.email_sent_at.isoformat() if report.email_sent_at else None,
                report.created_at.isoformat()
            )
        )
        await db.commit()

async def update_qa_report(report_id: str, db_path: str = _DEFAULT_DB, **kwargs) -> None:
    if not kwargs:
        return
    sets = []
    values = []
    for k, v in kwargs.items():
        sets.append(f"{k} = ?")
        if isinstance(v, dict):
            values.append(json.dumps(v))
        elif isinstance(v, datetime):
            values.append(v.isoformat())
        else:
            values.append(v)
    
    values.append(report_id)
    query = f"UPDATE qa_reports SET {', '.join(sets)} WHERE id = ?"
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
        await db.execute(query, tuple(values))
        await db.commit()

async def get_qa_reports(workspace_id: str, db_path: str = _DEFAULT_DB) -> list:
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM qa_reports WHERE workspace_id = ? ORDER BY created_at DESC", (workspace_id,)) as cursor:
            rows = await cursor.fetchall()
            from models import QAReport
            res = []
            for r in rows:
                d = dict(r)
                for json_col in ('static_analysis', 'functionality', 'stress_test', 'vapt', 'regression', 'performance'):
                    if d.get(json_col):
                        d[json_col] = json.loads(d[json_col])
                res.append(QAReport(**d))
            return res

async def get_qa_report(report_id: str, db_path: str = _DEFAULT_DB):
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM qa_reports WHERE id = ?", (report_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                from models import QAReport
                d = dict(row)
                for json_col in ('static_analysis', 'functionality', 'stress_test', 'vapt', 'regression', 'performance'):
                    if d.get(json_col):
                        d[json_col] = json.loads(d[json_col])
                return QAReport(**d)
            return None

# ── Rollbacks CRUD ───────────────────────────────────────────────────────

async def create_rollback(record, db_path: str = _DEFAULT_DB) -> None:
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
        await db.execute(
            """INSERT INTO rollbacks (
                id, workspace_id, repo_name, failed_commit_sha, rolled_back_to_sha,
                backup_branch, pr_number, pr_url, failure_reason, status,
                created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.id, record.workspace_id, record.repo_name, record.failed_commit_sha,
                record.rolled_back_to_sha, record.backup_branch, record.pr_number, record.pr_url,
                record.failure_reason, record.status,
                record.created_at.isoformat(), record.updated_at.isoformat()
            )
        )
        await db.commit()

async def update_rollback(rollback_id: str, db_path: str = _DEFAULT_DB, **kwargs) -> None:
    if not kwargs:
        return
    kwargs["updated_at"] = datetime.utcnow().isoformat()
    sets = []
    values = []
    for k, v in kwargs.items():
        sets.append(f"{k} = ?")
        if isinstance(v, datetime):
            values.append(v.isoformat())
        else:
            values.append(v)
    
    values.append(rollback_id)
    query = f"UPDATE rollbacks SET {', '.join(sets)} WHERE id = ?"
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
        await db.execute(query, tuple(values))
        await db.commit()

async def get_rollbacks(workspace_id: str, db_path: str = _DEFAULT_DB) -> list:
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM rollbacks WHERE workspace_id = ? ORDER BY created_at DESC", (workspace_id,)) as cursor:
            rows = await cursor.fetchall()
            from models import RollbackRecord
            res = []
            for r in rows:
                d = dict(r)
                d["created_at"] = datetime.fromisoformat(d["created_at"]) if isinstance(d.get("created_at"), str) else d.get("created_at", datetime.utcnow())
                d["updated_at"] = datetime.fromisoformat(d["updated_at"]) if isinstance(d.get("updated_at"), str) else d.get("updated_at", datetime.utcnow())
                res.append(RollbackRecord(**d))
            return res

async def get_rollback(rollback_id: str, db_path: str = _DEFAULT_DB):
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM rollbacks WHERE id = ?", (rollback_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                from models import RollbackRecord
                d = dict(row)
                d["created_at"] = datetime.fromisoformat(d["created_at"]) if isinstance(d.get("created_at"), str) else d.get("created_at", datetime.utcnow())
                d["updated_at"] = datetime.fromisoformat(d["updated_at"]) if isinstance(d.get("updated_at"), str) else d.get("updated_at", datetime.utcnow())
                return RollbackRecord(**d)
            return None

async def get_rollback_by_backup_branch(backup_branch: str, db_path: str = _DEFAULT_DB):
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM rollbacks WHERE backup_branch = ?", (backup_branch,)) as cursor:
            row = await cursor.fetchone()
            if row:
                from models import RollbackRecord
                d = dict(row)
                d["created_at"] = datetime.fromisoformat(d["created_at"]) if isinstance(d.get("created_at"), str) else d.get("created_at", datetime.utcnow())
                d["updated_at"] = datetime.fromisoformat(d["updated_at"]) if isinstance(d.get("updated_at"), str) else d.get("updated_at", datetime.utcnow())
                return RollbackRecord(**d)
            return None


# ── Resolutions CRUD ───────────────────────────────────────────────────────

async def create_resolution(record, db_path: str = _DEFAULT_DB) -> None:
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
        await db.execute(
            """INSERT INTO resolutions (
                id, rollback_id, workspace_id, repo_name, backup_branch,
                resolution_pr_url, resolution_pr_number, attempt_number,
                build_error_log, status, created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.id, record.rollback_id, record.workspace_id, record.repo_name, record.backup_branch,
                record.resolution_pr_url, record.resolution_pr_number, record.attempt_number,
                record.build_error_log, record.status, record.created_at.isoformat(), record.updated_at.isoformat()
            )
        )
        await db.commit()

async def update_resolution(resolution_id: str, db_path: str = _DEFAULT_DB, **kwargs) -> None:
    if not kwargs:
        return
    kwargs["updated_at"] = datetime.utcnow().isoformat()
    sets = []
    values = []
    for k, v in kwargs.items():
        sets.append(f"{k} = ?")
        if isinstance(v, datetime):
            values.append(v.isoformat())
        else:
            values.append(v)
    
    values.append(resolution_id)
    query = f"UPDATE resolutions SET {', '.join(sets)} WHERE id = ?"
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
        await db.execute(query, tuple(values))
        await db.commit()

async def get_resolutions_for_rollback(rollback_id: str, db_path: str = _DEFAULT_DB) -> list:
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM resolutions WHERE rollback_id = ? ORDER BY attempt_number DESC", (rollback_id,)) as cursor:
            rows = await cursor.fetchall()
            from models import ResolutionRecord
            res = []
            for r in rows:
                d = dict(r)
                d["created_at"] = datetime.fromisoformat(d["created_at"]) if isinstance(d.get("created_at"), str) else d.get("created_at", datetime.utcnow())
                d["updated_at"] = datetime.fromisoformat(d["updated_at"]) if isinstance(d.get("updated_at"), str) else d.get("updated_at", datetime.utcnow())
                res.append(ResolutionRecord(**d))
            return res

async def get_resolution(resolution_id: str, db_path: str = _DEFAULT_DB):
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM resolutions WHERE id = ?", (resolution_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                from models import ResolutionRecord
                d = dict(row)
                d["created_at"] = datetime.fromisoformat(d["created_at"]) if isinstance(d.get("created_at"), str) else d.get("created_at", datetime.utcnow())
                d["updated_at"] = datetime.fromisoformat(d["updated_at"]) if isinstance(d.get("updated_at"), str) else d.get("updated_at", datetime.utcnow())
                return ResolutionRecord(**d)
            return None


