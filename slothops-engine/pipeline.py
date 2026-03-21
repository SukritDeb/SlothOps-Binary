"""
SlothOps Engine — Pipeline Orchestrator
Runs the full remediation pipeline for a single issue:
  parse → redact → fingerprint → classify → fetch → fix → PR

Each stage updates the DB status and broadcasts an SSE event.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import database as db
from classifier import classify
from code_fetcher import fetch_code_context
import asyncio
from fingerprint import check_dedup, compute_fingerprint
from github_automation import create_fix_pr
from llm_fixer import generate_fix, generate_infra_recommendation
from models import DedupeAction, IssueRecord, IssueStatus
from redactor import redact
from sse_manager import broadcast

logger = logging.getLogger("slothops.pipeline")


async def _update(
    issue: IssueRecord,
    db_path: str,
    status: str,
    event: str = "status_update",
    **extra_fields,
) -> None:
    """Helper: update DB status + broadcast SSE event."""
    await db.update_issue_status(issue.id, db_path, status=status, **extra_fields)
    await broadcast(event, {"id": issue.id, "status": status, **extra_fields})


async def run_pipeline(
    issue: IssueRecord,
    db_path: str,
    gemini_api_key: str,
    github_app_id: str | None = None,
    github_app_private_key: str | None = None,
) -> None:
    """
    Execute the full bug remediation pipeline for one issue.

    This function is meant to be spawned as an ``asyncio.create_task()``
    from the webhook handler so the HTTP response returns immediately.
    """
    logger.info("Pipeline started for issue %s (%s)", issue.id[:8], issue.error_type)

    try:
        # ── 1. Redact ────────────────────────────────────────────────
        await _update(issue, db_path, IssueStatus.TRIAGING.value)
        issue.stack_trace = redact(issue.stack_trace or "")
        issue.error_message = redact(issue.error_message or "")
        logger.info("[%s] Redaction complete", issue.id[:8])

        # ── 2. Fingerprint + Dedup ───────────────────────────────────
        fp = compute_fingerprint(issue.error_type, issue.file_path, issue.function_name, issue.error_message)
        issue.fingerprint = fp

        existing = await db.get_issue_by_fingerprint(fp, issue.workspace_id, db_path)

        if existing:
            action = check_dedup(existing.status, existing.updated_at)
            if action == DedupeAction.SKIP:
                await db.increment_occurrence(existing.id, issue.workspace_id, db_path)
                await broadcast("status_update", {
                    "id": existing.id,
                    "status": existing.status,
                    "message": "Duplicate — skipped",
                })
                logger.info("[%s] Duplicate fingerprint, skipping", issue.id[:8])
                return
            elif action == DedupeAction.RETRIGGER:
                # Mark old fix as ineffective
                await db.update_issue_status(
                    existing.id, db_path, status=IssueStatus.FIX_INEFFECTIVE.value
                )
                issue.previous_fix_id = existing.id
                logger.info("[%s] Re-triggering: previous fix ineffective", issue.id[:8])

        # Persist the new issue
        issue.fingerprint = fp
        await db.create_issue(issue, db_path)

        # ── 3. Classify ──────────────────────────────────────────────
        classification = classify(
            error_type=issue.error_type,
            error_message=issue.error_message,
            stack_trace=issue.stack_trace,
            file_path=issue.file_path,
        )
        issue.classification = classification
        await _update(issue, db_path, IssueStatus.CLASSIFIED.value, classification=classification)
        logger.info("[%s] Classified as: %s", issue.id[:8], classification)

        if classification != "code":
            if classification == "infra":
                logger.info("[%s] Fetching Infra Recommendation from Gemini", issue.id[:8])
                await _update(issue, db_path, IssueStatus.FIXING.value)
                try:
                    recommendation = await asyncio.to_thread(generate_infra_recommendation, issue)
                except Exception as e:
                    recommendation = f"Failed to generate recommendation: {e}"
                    
                await _update(
                    issue, db_path,
                    IssueStatus.RECOMMENDATION_ONLY.value,
                    root_cause="Infrastructure failure detected",
                    recommendation=recommendation
                )
                return
                
            await _update(issue, db_path, IssueStatus.IGNORED.value)
            logger.info("[%s] Not a code error — ignored", issue.id[:8])
            return

        # ── 4. Build GitHub Client & Fetch context ───────────────────
        await _update(issue, db_path, IssueStatus.FIXING.value)

        try:
            from github import Github, GithubIntegration, Auth
            
            if not github_app_id or not github_app_private_key:
                logger.error("[%s] GitHub App not configured (GITHUB_APP_ID or GITHUB_APP_PRIVATE_KEY missing from .env)", issue.id[:8])
                await _update(issue, db_path, "fixing_failed", root_cause="GitHub App not configured. Set GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY in .env")
                return

            # Load private key — support both inline and file path
            private_key = github_app_private_key
            if private_key and os.path.isfile(private_key):
                with open(private_key, "r") as f:
                    private_key = f.read()
            
            # Get the installation_id from the workspace's integrations table
            integration = await db.get_integration(issue.workspace_id, db_path)
            
            if not integration or not integration.github_installation_id:
                logger.error("[%s] No GitHub App installation linked for workspace %s. "
                             "User must install the GitHub App on their repository first.",
                             issue.id[:8], issue.workspace_id)
                await _update(issue, db_path, "fixing_failed", 
                              root_cause="GitHub App not installed. Go to Settings in your SlothOps dashboard and install the GitHub App on your repository.")
                return

            installation_id = int(integration.github_installation_id)
            auth = Auth.AppAuth(github_app_id, private_key)
            gi = GithubIntegration(auth=auth)
            installation_auth = auth.get_installation_auth(installation_id)
            g = Github(auth=installation_auth)
            
            # Dynamically discover which repo the user installed us on
            installed_repos = list(gi.get_installations()[0].get_repos()) if gi.get_installations() else []
            if not installed_repos:
                # Fallback: try listing repos via the installation-authed client
                installed_repos = list(g.get_user().get_repos())
            if not installed_repos:
                raise Exception("GitHub App has no repository access. User must install on at least one repo.")
            
            repo = g.get_repo(installed_repos[0].full_name)
            logger.info("[%s] ✅ Authenticated via GitHub App (Installation %s) → Repo: %s", 
                        issue.id[:8], installation_id, repo.full_name)

        except Exception as exc:
            logger.error("[%s] GitHub client init failed: %s", issue.id[:8], exc)
            await _update(issue, db_path, "fixing_failed", root_cause=str(exc))
            return

        code_context = fetch_code_context(
            file_path=issue.file_path,
            repo=repo,
        )
        logger.info("[%s] Fetched %d file(s) from GitHub", issue.id[:8], len(code_context))

        if not code_context:
            logger.warning("[%s] No code context found — cannot generate fix", issue.id[:8])
            await _update(issue, db_path, "fixing_failed",
                          root_cause="Could not fetch source files from GitHub")
            return

        # ── 5. LLM fix generation ────────────────────────────────────
        previous_pr_url: Optional[str] = None
        if issue.previous_fix_id:
            prev = await db.get_issue(issue.previous_fix_id, db_path)
            previous_pr_url = prev.fix_pr_url if prev else None

        try:
            fix = generate_fix(
                issue=issue,
                code_context=code_context,
                gemini_api_key=gemini_api_key,
                previous_pr_url=issue.previous_fix_id,
            )
        except RuntimeError as exc:
            logger.error("[%s] LLM fix failed: %s", issue.id[:8], exc)
            await _update(issue, db_path, "fixing_failed", root_cause=str(exc))
            return

        issue.confidence = fix.confidence
        issue.root_cause = fix.root_cause
        logger.info("[%s] Fix generated (confidence: %s)", issue.id[:8], fix.confidence)

        # ── 6. Confidence gating ─────────────────────────────────────
        if fix.confidence == "low":
            await _update(
                issue, db_path,
                IssueStatus.RECOMMENDATION_ONLY.value,
                confidence=fix.confidence,
                root_cause=fix.root_cause,
                recommendation=fix.pr_body,
            )
            logger.info("[%s] Low confidence — stored recommendation only", issue.id[:8])
            return

        # ── 7. Create GitHub PR ──────────────────────────────────────
        try:
            pr_url = create_fix_pr(
                issue=issue,
                fix=fix,
                repo=repo,
            )
        except RuntimeError as exc:
            logger.error("[%s] PR creation failed: %s", issue.id[:8], exc)
            await _update(issue, db_path, "pr_creation_failed", root_cause=str(exc))
            return

        await _update(
            issue, db_path,
            IssueStatus.PR_CREATED.value,
            confidence=fix.confidence,
            root_cause=fix.root_cause,
            fix_pr_url=pr_url,
            fix_pr_branch=f"slothops/fix-{issue.id[:8]}",
        )
        logger.info("[%s] ✅ Draft PR created: %s", issue.id[:8], pr_url)

    except Exception as exc:
        logger.exception("[%s] Unhandled pipeline error: %s", issue.id[:8], exc)
        try:
            await _update(issue, db_path, "fixing_failed", root_cause=f"Unhandled: {exc}")
        except Exception:
            pass
