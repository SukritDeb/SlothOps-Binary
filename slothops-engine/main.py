"""
SlothOps Engine — FastAPI Application
Entry point for the server.  Defines all HTTP endpoints and starts
the pipeline asynchronously on incoming Sentry webhooks.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

import database as db
from models import IssueRecord
from pipeline import run_pipeline
from sentry_parser import parse_sentry_webhook
from sse_manager import broadcast, subscribe
# ── Load env early (before config.py import to avoid crash in dev) ───
from dotenv import load_dotenv
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GITHUB_APP_ID = os.getenv("GITHUB_APP_ID", None)

# Support both inline PEM and file path
_pem_raw = os.getenv("GITHUB_APP_PRIVATE_KEY", "")
if _pem_raw and os.path.isfile(_pem_raw):
    with open(_pem_raw, "r") as f:
        GITHUB_APP_PRIVATE_KEY = f.read()
elif _pem_raw:
    GITHUB_APP_PRIVATE_KEY = _pem_raw.replace("\\n", "\n")
else:
    GITHUB_APP_PRIVATE_KEY = None
DATABASE_PATH = os.getenv("DATABASE_PATH", "./slothops.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ── Logging ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s  %(name)-28s  %(levelname)-5s  %(message)s",
)
logger = logging.getLogger("slothops.main")


class SSELogHandler(logging.Handler):
    """Forward Python logs to connected dashboard clients over SSE."""

    def __init__(self) -> None:
        super().__init__()
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def emit(self, record: logging.LogRecord) -> None:
        loop = self._loop
        if not loop or loop.is_closed():
            return

        # Prevent accidental recursion if SSE internals log.
        if record.name.startswith("slothops.sse"):
            return

        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        def _dispatch() -> None:
            asyncio.create_task(broadcast("log", payload))

        loop.call_soon_threadsafe(_dispatch)


sse_log_handler = SSELogHandler()


# ── Lifespan (runs on startup / shutdown) ────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    root_logger = logging.getLogger()
    if not any(isinstance(h, SSELogHandler) for h in root_logger.handlers):
        sse_log_handler.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
        root_logger.addHandler(sse_log_handler)
    sse_log_handler.set_loop(asyncio.get_running_loop())

    logger.info("Initialising database at %s", DATABASE_PATH)
    await db.init_db(DATABASE_PATH)
    logger.info("SlothOps engine ready 🦥")
    yield
    logger.info("Shutting down")


# ── FastAPI App ──────────────────────────────────────────────────────────
app = FastAPI(
    title="SlothOps Engine",
    description="Production-aware automated bug remediation pipeline",
    version="0.1.0",
    lifespan=lifespan,
)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ── Auth & Security ──────────────────────────────────────────────────────
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
import auth
import uuid
from models import User, Workspace

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

async def get_current_workspace(token: str = Depends(oauth2_scheme)):
    token_data = auth.decode_access_token(token)
    if not token_data.workspace_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return token_data.workspace_id

class SignupRequest(BaseModel):
    email: str
    password: str
    workspace_name: str

@app.post("/api/signup")
async def signup(req: SignupRequest):
    try:
        existing = await db.get_user_by_email(req.email)
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        user_id = str(uuid.uuid4())
        hashed = auth.get_password_hash(req.password)
        user = User(id=user_id, email=req.email, hashed_password=hashed)
        await db.create_user(user)
        
        workspace_id = str(uuid.uuid4())
        workspace = Workspace(id=workspace_id, name=req.workspace_name)
        await db.create_workspace(workspace)
        await db.add_user_to_workspace(workspace_id, user_id, role="admin")
        
        access_token = auth.create_access_token(
            data={"sub": user.email, "workspace_id": workspace_id}
        )
        return {"access_token": access_token, "token_type": "bearer"}
    except Exception as e:
        import traceback
        logger.error("Signup 500: %s %s", str(e), traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Engine Error: {str(e)}")

@app.post("/api/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    try:
        user = await db.get_user_by_email(form_data.username)
        if not user or not auth.verify_password(form_data.password, user.hashed_password):
            raise HTTPException(status_code=400, detail="Incorrect email or password")
        
        workspaces = await db.get_user_workspaces(user.id)
        workspace_id = workspaces[0].id if workspaces else "default_workspace"
        
        access_token = auth.create_access_token(
            data={"sub": user.email, "workspace_id": workspace_id}
        )
        return {"access_token": access_token, "token_type": "bearer"}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error("Login 500: %s %s", str(e), traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Engine Error: {str(e)}")


# ── Routes ───────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "slothops-engine"}


@app.get("/")
async def serve_dashboard():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse({"message": "Dashboard not built yet. See Phase 3."})

@app.get("/style.css")
async def serve_css():
    css_path = os.path.join(STATIC_DIR, "style.css")
    if os.path.exists(css_path):
        return FileResponse(css_path)
    return JSONResponse({"error": "Not found"}, status_code=404)


@app.post("/webhook/sentry/{workspace_id}")
async def receive_sentry_webhook(workspace_id: str, request: Request):
    """
    Receive a Sentry webhook, parse it, bind to workspace, and kick off the pipeline async.
    Returns 200 immediately so Sentry doesn't retry.
    """
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    # Parse payload into an IssueRecord
    try:
        issue, call_frames = parse_sentry_webhook(payload)
        issue.workspace_id = workspace_id
        # Store call frames in structured raw_payload for deep scan on recurrence
        issue.raw_payload = json.dumps({
            "frames": [f.model_dump() for f in call_frames],
            "original": payload,
        })
    except Exception as exc:
        logger.error("Failed to parse Sentry payload: %s", exc)
        return JSONResponse({"error": "Parse failed"}, status_code=400)

    logger.info(
        "Webhook received: %s — %s in %s",
        issue.error_type,
        issue.error_message,
        issue.file_path,
    )

    # Kick off pipeline in background
    asyncio.create_task(
        run_pipeline(
            issue=issue,
            db_path=DATABASE_PATH,
            gemini_api_key=GEMINI_API_KEY,
            github_app_id=GITHUB_APP_ID,
            github_app_private_key=GITHUB_APP_PRIVATE_KEY,
        )
    )

    return JSONResponse({"status": "accepted", "issue_id": issue.id})

from pydantic import BaseModel

class GithubLinkRequest(BaseModel):
    installation_id: str

@app.post("/api/github/link")
async def link_github_installation(req: GithubLinkRequest, workspace_id: str = Depends(get_current_workspace)):
    """
    Called securely by the Frontend Dashboard immediately after the user installs 
    the GitHub App and is redirected back to the Setup URL.
    Pairs the App Installation mathematically to their verified JWT workspace_id.
    """
    from models import Integration
    # Upsert the integration row
    integration = Integration(
        workspace_id=workspace_id,
        github_installation_id=req.installation_id
    )
    await db.upsert_integration(integration, DATABASE_PATH)
    logger.info("Successfully bound GitHub Installation %s to Workspace %s via Dashboard OAuth redirect!", req.installation_id, workspace_id)
    return {"status": "linked", "workspace": workspace_id}

@app.post("/webhook/github")
async def receive_github_webhook(request: Request):
    """
    Receives GitHub App installation events.
    On 'installation' created: store the installation_id.
    On 'installation' deleted: remove the integration record.
    """
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    action = payload.get("action")
    installation = payload.get("installation", {})
    installation_id = str(installation.get("id", ""))

    github_event = request.headers.get("x-github-event")

    if github_event == "pull_request" and action in ["opened", "synchronize"]:
        if installation_id:
            workspace_id = await db.get_workspace_by_installation_id(installation_id, DATABASE_PATH)
            if workspace_id:
                from github_automation import handle_human_pr_review
                from qa_pipeline import run_qa_pipeline
                logger.info("Received Human PR event %s for workspace %s, queuing review + QA...", action, workspace_id)
                asyncio.create_task(handle_human_pr_review(
                    payload=payload,
                    workspace_id=workspace_id,
                    gemini_api_key=GEMINI_API_KEY,
                    github_app_id=GITHUB_APP_ID,
                    github_app_private_key=GITHUB_APP_PRIVATE_KEY,
                    db_path=DATABASE_PATH
                ))
                asyncio.create_task(run_qa_pipeline(
                    payload=payload,
                    workspace_id=workspace_id,
                    gemini_api_key=GEMINI_API_KEY,
                    github_app_id=GITHUB_APP_ID,
                    github_app_private_key=GITHUB_APP_PRIVATE_KEY,
                    db_path=DATABASE_PATH
                ))
                return {"status": "review_and_qa_queued"}

    if github_event == "deployment_status":
        deployment_status = payload.get("deployment_status", {})
        state = deployment_status.get("state")
        if state in ["error", "failure"] and installation_id:
            workspace_id = await db.get_workspace_by_installation_id(installation_id, DATABASE_PATH)
            if workspace_id:
                sha = payload.get("deployment", {}).get("sha")
                ref = payload.get("deployment", {}).get("ref", "")
                repo_name = payload.get("repository", {}).get("full_name")
                if sha and repo_name:
                    if str(ref).startswith("slothops/backup-"):
                        rollback_record = await db.get_rollback_by_backup_branch(str(ref), DATABASE_PATH)
                        if rollback_record:
                            from resolution import attempt_resolution
                            logger.info("Received re-cycle deployment failure for resolution PR %s", ref)
                            
                            SMTP_HOST = os.getenv("SMTP_HOST", "")
                            SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
                            SMTP_USER = os.getenv("SMTP_USER", "")
                            SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
                            QA_EMAIL_RECIPIENT = os.getenv("QA_EMAIL_RECIPIENT", "")
                            
                            asyncio.create_task(attempt_resolution(
                                rollback_id=rollback_record.id,
                                workspace_id=workspace_id,
                                repo_name=repo_name,
                                backup_branch=str(ref),
                                build_error_log=f"Deployment status reported {state}",
                                failed_sha=sha,
                                github_app_id=GITHUB_APP_ID,
                                github_app_private_key=GITHUB_APP_PRIVATE_KEY,
                                gemini_api_key=str(os.getenv("GEMINI_API_KEY", "")),
                                db_path=DATABASE_PATH,
                                smtp_config={
                                    "SMTP_HOST": SMTP_HOST,
                                    "SMTP_PORT": SMTP_PORT,
                                    "SMTP_USER": SMTP_USER,
                                    "SMTP_PASSWORD": SMTP_PASSWORD,
                                    "QA_EMAIL_RECIPIENT": QA_EMAIL_RECIPIENT
                                }
                            ))
                            return {"status": "resolution_queued"}
                    
                    from rollback import perform_rollback
                    logger.info("Received deployment failure for %s, queuing rollback...", sha[:8])
                    asyncio.create_task(perform_rollback(
                        workspace_id=workspace_id,
                        repo_name=repo_name,
                        failed_sha=sha,
                        github_app_id=GITHUB_APP_ID,
                        github_app_private_key=GITHUB_APP_PRIVATE_KEY,
                        db_path=DATABASE_PATH,
                        failure_reason=f"Deployment status reported {state}"
                    ))
                    return {"status": "rollback_queued"}

    if payload.get("installation") and action == "created" and installation_id:
        # Auto-link: Find the workspace that doesn't have a GitHub integration yet
        # and link this installation to it. For multi-tenant, the frontend /api/github/link
        # endpoint is the primary pairing mechanism, but this serves as a backup.
        workspaces = await db.list_workspaces(DATABASE_PATH)
        for ws in workspaces:
            existing_integration = await db.get_integration(ws.id, DATABASE_PATH)
            if not existing_integration or not existing_integration.github_installation_id:
                from models import Integration
                integration = Integration(
                    workspace_id=ws.id,
                    github_installation_id=installation_id
                )
                await db.upsert_integration(integration, DATABASE_PATH)
                logger.info("Auto-linked GitHub Installation %s to Workspace %s", installation_id, ws.id)
                return {"status": "linked", "workspace": ws.id}
        
        logger.info("GitHub Installation %s received but no unlinked workspace available. User should link via dashboard.", installation_id)
    
    elif payload.get("installation") and action == "deleted" and installation_id:
        # Remove the integration when the app is uninstalled
        workspaces = await db.list_workspaces(DATABASE_PATH)
        for ws in workspaces:
            integration = await db.get_integration(ws.id, DATABASE_PATH)
            if integration and integration.github_installation_id == installation_id:
                from models import Integration
                cleared = Integration(workspace_id=ws.id, github_installation_id="")
                await db.upsert_integration(cleared, DATABASE_PATH)
                logger.info("Unlinked GitHub Installation %s from Workspace %s (app uninstalled)", installation_id, ws.id)
                break

    return {"status": "ok"}


# ── Developer Config ─────────────────────────────────────────────────────

@app.post("/api/developer-config")
async def upload_developer_config(request: Request, workspace_id: str = Depends(get_current_workspace)):
    """Upload or update developer.json style preferences for this workspace."""
    try:
        config = await request.json()
        import json as _json
        await db.upsert_developer_config(workspace_id, _json.dumps(config), DATABASE_PATH)
        logger.info("Developer config saved for workspace %s", workspace_id)
        return {"status": "saved", "workspace": workspace_id}
    except Exception as e:
        logger.error("Failed to save developer config: %s", e)
        raise HTTPException(status_code=400, detail=f"Invalid config: {str(e)}")

@app.get("/api/qa-reports")
async def list_qa_reports(workspace_id: str = Depends(get_current_workspace)):
    reports = await db.get_qa_reports(workspace_id, DATABASE_PATH)
    return [r.model_dump() for r in reports]

@app.get("/api/qa-reports/{report_id}")
async def get_qa_report(report_id: str, workspace_id: str = Depends(get_current_workspace)):
    report = await db.get_qa_report(report_id, DATABASE_PATH)
    if not report or report.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Not found")
    return report.model_dump()

@app.get("/api/rollbacks")
async def list_rollbacks(workspace_id: str = Depends(get_current_workspace)):
    rollbacks = await db.get_rollbacks(workspace_id, DATABASE_PATH)
    res = []
    for r in rollbacks:
        r_dict = r.model_dump()
        resolutions = await db.get_resolutions_for_rollback(r.id, DATABASE_PATH)
        r_dict["resolutions"] = [res_rec.model_dump() for res_rec in resolutions]
        res.append(r_dict)
    return res

@app.get("/api/rollbacks/{rollback_id}")
async def get_rollback_record(rollback_id: str, workspace_id: str = Depends(get_current_workspace)):
    r = await db.get_rollback(rollback_id, DATABASE_PATH)
    if not r or r.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Not found")
    r_dict = r.model_dump()
    resolutions = await db.get_resolutions_for_rollback(r.id, DATABASE_PATH)
    r_dict["resolutions"] = [res_rec.model_dump() for res_rec in resolutions]
    return r_dict



class QABypassRequest(BaseModel):
    reason: str

@app.post("/api/qa-bypass/{report_id}")
async def bypass_qa(report_id: str, req: QABypassRequest, workspace_id: str = Depends(get_current_workspace)):
    report = await db.get_qa_report(report_id, DATABASE_PATH)
    if not report or report.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Not found")
    
    logger.info("QA bypassed for PR #%s by user in workspace %s. Reason: %s", report.pr_number, workspace_id, req.reason)
    from models import QAStatus
    await db.update_qa_report(report_id, DATABASE_PATH, overall_status=QAStatus.BYPASSED.value, summary=f"Bypassed by operator. Reason: {req.reason}")
    asyncio.create_task(broadcast("qa_update", {"id": report_id, "status": QAStatus.BYPASSED.value}))
    
    # Set GitHub commit status to success so the merge button unblocks
    try:
        integration = await db.get_integration(workspace_id, DATABASE_PATH)
        if integration and integration.github_installation_id:
            from github import GithubIntegration, Github
            from qa_pipeline import _set_commit_status
            gi = GithubIntegration(GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY)
            token = gi.get_access_token(int(integration.github_installation_id)).token
            gh = Github(token)
            repo = gh.get_repo(report.repo_name)
            _set_commit_status(repo, report.commit_sha, "success", f"QA bypassed: {req.reason[:100]}", report.pr_url)
            logger.info("✅ Commit status set to success after bypass for SHA %s", report.commit_sha[:8])
    except Exception as e:
        logger.error("Failed to set commit status on bypass: %s", e)
    
    return {"status": "bypassed"}


@app.get("/api/developer-config")
async def get_developer_config(workspace_id: str = Depends(get_current_workspace)):
    """Retrieve current developer.json preferences for this workspace."""
    config = await db.get_developer_config(workspace_id, DATABASE_PATH)
    if config is None:
        return {"config": None, "message": "No developer config set. Upload one to enable style reviews."}
    return {"config": config}


# ── Issue Routes ─────────────────────────────────────────────────────────

@app.get("/issues")
async def list_issues(workspace_id: str = Depends(get_current_workspace)):
    issues = await db.list_issues(workspace_id, DATABASE_PATH)
    return [issue.model_dump(mode="json") for issue in issues]

@app.get("/issues/{issue_id}")
async def get_issue(issue_id: str, workspace_id: str = Depends(get_current_workspace)):
    issue = await db.get_issue(issue_id, workspace_id, DATABASE_PATH)
    if not issue:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return issue.model_dump(mode="json")

@app.get("/stream")
async def sse_stream(token: str):
    """Server-Sent Events endpoint for real-time dashboard updates. 
    Uses ?token query param since EventSource does not natively support Authorization headers.
    """
    token_data = auth.decode_access_token(token)
    if not token_data.workspace_id:
        raise HTTPException(status_code=401, detail="Invalid token")
        
    async def event_generator():
        async for msg in subscribe():
            yield {
                "event": msg.get("event", "message"),
                "data": json.dumps(msg.get("data", {})),
            }

    return EventSourceResponse(event_generator())
