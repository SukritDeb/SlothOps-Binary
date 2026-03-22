"""
SlothOps Engine — Production Rollback
Handles automatic revert of bad commits on main based on CI/CD deployment failures.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import subprocess
import uuid
from datetime import datetime

import database as db
from models import RollbackRecord, RollbackStatus
from sse_manager import broadcast
from email_sender import send_rollback_notification_email

logger = logging.getLogger("slothops.rollback")

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
QA_EMAIL_RECIPIENT = os.getenv("QA_EMAIL_RECIPIENT", "")


async def perform_rollback(
    workspace_id: str,
    repo_name: str,
    failed_sha: str,
    github_app_id: int,
    github_app_private_key: str,
    db_path: str,
    failure_reason: str = "Production deployment failed"
):
    """
    Execute a production rollback using a local sandbox to securely revert the bad commit.
    """
    logger.info("Initiating rollback for %s on %s", failed_sha[:8], repo_name)
    from github import Github, GithubIntegration

    # Load integrations
    integration_record = await db.get_integration(workspace_id, db_path)
    if not integration_record or not integration_record.github_installation_id:
        logger.error("No GitHub App linked for workspace %s. Cannot rollback.", workspace_id)
        return

    installation_id = int(integration_record.github_installation_id)

    try:
        integration = GithubIntegration(github_app_id, github_app_private_key)
        access_token = integration.get_access_token(installation_id).token
        gh = Github(access_token)
        repo = gh.get_repo(repo_name)
    except Exception as e:
        logger.error("Failed to auth GitHub App for Rollback: %s", e)
        return

    # Check if a rollback for this SHA already happened to avoid loops
    existing_rollbacks = await db.get_rollbacks(workspace_id, db_path)
    if any(r.failed_commit_sha == failed_sha for r in existing_rollbacks):
        logger.warning("Rollback for %s has already been triggered. Skipping.", failed_sha[:8])
        return

    # Look up the PR
    pr_number = None
    pr_url = None
    try:
        commit_obj = repo.get_commit(failed_sha)
        is_merge = len(commit_obj.parents) > 1
        
        if commit_obj.commit.message.startswith("Revert"):
            logger.warning("Commit %s appears to be a Revert commit. Aborting rollback to prevent infinite loops.", failed_sha[:8])
            return
        
        prs = commit_obj.get_pulls()
        for p in prs:
            pr_number = p.number
            pr_url = p.html_url
            break
    except Exception as e:
        logger.warning("Could not find commit or PR info for %s: %s", failed_sha[:8], e)
        is_merge = False

    backup_branch = f"slothops/backup-{failed_sha[:8]}"
    
    # Run sandbox operations
    clone_url = repo.clone_url.replace("https://", f"https://x-access-token:{access_token}@")
    
    rollback_id = str(uuid.uuid4())
    record = RollbackRecord(
        id=rollback_id,
        workspace_id=workspace_id,
        repo_name=repo_name,
        failed_commit_sha=failed_sha,
        backup_branch=backup_branch,
        pr_number=pr_number,
        pr_url=pr_url,
        failure_reason=failure_reason,
        status=RollbackStatus.PENDING.value
    )
    await db.create_rollback(record, db_path)
    await broadcast("rollback_event", record.model_dump())

    revert_commit_sha = None
    
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            # Clone and setup branch
            subprocess.run(["git", "clone", clone_url, tmpdir], check=True, capture_output=True, timeout=60)
            subprocess.run(["git", "checkout", "main"], cwd=tmpdir, check=True, capture_output=True)
            
            # Create backup
            subprocess.run(["git", "branch", backup_branch, failed_sha], cwd=tmpdir, check=True, capture_output=True)
            subprocess.run(["git", "push", "origin", backup_branch], cwd=tmpdir, check=True, capture_output=True)
            logger.info("Backup branch created: %s", backup_branch)
            
            # Revert
            subprocess.run(["git", "config", "user.email", "bot@slothops.com"], cwd=tmpdir)
            subprocess.run(["git", "config", "user.name", "SlothOps Bot"], cwd=tmpdir)
            
            revert_cmd = ["git", "revert", "--no-edit"]
            if is_merge:
                revert_cmd.extend(["-m", "1"])
            revert_cmd.append(failed_sha)
            
            res = subprocess.run(revert_cmd, cwd=tmpdir, capture_output=True, text=True)
            if res.returncode != 0:
                raise Exception(f"Git revert failed: {res.stderr}")
                
            subprocess.run(["git", "push", "origin", "main"], cwd=tmpdir, check=True, capture_output=True)
            logger.info("Reverted bad commit %s on main", failed_sha[:8])
            
            # Get the new sha
            rev_parse = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmpdir, capture_output=True, text=True)
            revert_commit_sha = rev_parse.stdout.strip()
            
        except Exception as e:
            logger.error("Sandbox rollback logic failed: %s", e)
            await db.update_rollback(rollback_id, db_path, status=RollbackStatus.FAILED.value, failure_reason=f"{failure_reason} (Revert script failed: {e})")
            
            # Broadcast the updated failure
            record.status = RollbackStatus.FAILED.value
            await broadcast("rollback_event", record.model_dump())
            return

    # Update success in DB
    await db.update_rollback(
        rollback_id, 
        db_path, 
        status=RollbackStatus.COMPLETED.value, 
        rolled_back_to_sha=revert_commit_sha
    )
    
    record.status = RollbackStatus.COMPLETED.value
    record.rolled_back_to_sha = revert_commit_sha
    await broadcast("rollback_event", record.model_dump())

    # Comment on PR
    if pr_number:
        try:
            pr = repo.get_pull(pr_number)
            pr.create_issue_comment(
                f"🚨 **Production Deployment Failed**\n\n"
                f"SlothOps intercepted a deployment failure linked to this PR (`{failed_sha[:8]}`).\n"
                f"As a safety measure, this commit was **automatically reverted** on `main`.\n\n"
                f"A backup branch preserving these changes has been created: `{backup_branch}`.\n"
                f"Please fix the build issues on the backup branch and open a new PR."
            )
            logger.info("Commented rollback notification on PR #%d", pr_number)
        except Exception as e:
            logger.warning("Could not comment on PR for rollback: %s", e)

    # Email
    if QA_EMAIL_RECIPIENT and SMTP_HOST:
        send_rollback_notification_email({
            "repo_name": repo_name,
            "failed_sha": failed_sha[:8],
            "backup_branch": backup_branch,
            "pr_url": pr_url,
            "failure_reason": failure_reason
        }, QA_EMAIL_RECIPIENT, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD)

    # Trigger Resolution Auto-Fix
    from resolution import attempt_resolution
    logger.info("Triggering Auto-Resolution for rollback %s...", rollback_id)
    asyncio.create_task(attempt_resolution(
        rollback_id=rollback_id,
        workspace_id=workspace_id,
        repo_name=repo_name,
        backup_branch=backup_branch,
        build_error_log=failure_reason,  # Pass whatever reason we gathered
        failed_sha=failed_sha,
        github_app_id=github_app_id,
        github_app_private_key=github_app_private_key,
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        db_path=db_path,
        smtp_config={
            "SMTP_HOST": SMTP_HOST,
            "SMTP_PORT": SMTP_PORT,
            "SMTP_USER": SMTP_USER,
            "SMTP_PASSWORD": SMTP_PASSWORD,
            "QA_EMAIL_RECIPIENT": QA_EMAIL_RECIPIENT
        }
    ))


