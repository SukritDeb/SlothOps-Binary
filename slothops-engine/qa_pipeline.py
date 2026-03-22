import asyncio
import logging
import os
import tempfile
import subprocess
from datetime import datetime

import database as db
from models import QAReport, QAStatus
from stack_detector import detect_stack

from qa_agents.static_analysis import run_static_analysis
from qa_agents.functionality import run_functionality_tests
from qa_agents.vapt import run_vapt_scan
from qa_agents.stress_test import run_stress_test
from qa_agents.regression import run_regression_tests
from qa_agents.performance import run_performance_check
from email_sender import send_qa_report_email
from github_automation import post_qa_report_comment
from google import genai
import json

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
QA_EMAIL_RECIPIENT = os.getenv("QA_EMAIL_RECIPIENT", "")

logger = logging.getLogger("slothops.qa_pipeline")

COMMIT_STATUS_CONTEXT = "SlothOps QA"

def _set_commit_status(repo, sha: str, state: str, description: str, target_url: str = ""):
    """Set GitHub Commit Status on a specific SHA. state: pending|success|failure|error"""
    try:
        commit = repo.get_commit(sha)
        commit.create_status(
            state=state,
            description=description[:140],  # GitHub caps at 140 chars
            context=COMMIT_STATUS_CONTEXT,
            target_url=target_url or ""
        )
    except Exception as e:
        logger.error("Failed to set commit status (%s) on %s: %s", state, sha[:8], e)

async def run_qa_pipeline(
    payload: dict,
    workspace_id: str,
    gemini_api_key: str,
    github_app_id: int,
    github_app_private_key: str,
    db_path: str
):
    """
    Main QA orchestrator. Triggers upon PR close/merge.
    Downloads the merged state, runs the sub-agents sequentially (Phase 1),
    and stores/posts the results.
    """
    from github import Github, GithubIntegration
    
    installation_id = payload.get("installation", {}).get("id")
    if not installation_id:
        return
        
    pr_number = payload["pull_request"]["number"]
    pr_url = payload["pull_request"]["html_url"]
    repo_name = payload["repository"]["full_name"]
    # Use the PR HEAD SHA (not merge_commit_sha) for pre-merge status checks
    commit_sha = payload["pull_request"]["head"]["sha"]
    
    logger.info("🚀 Starting QA Pipeline for PR #%s in %s (SHA: %s)...", pr_number, repo_name, commit_sha[:8])
    
    try:
        integration = GithubIntegration(github_app_id, github_app_private_key)
        access_token = integration.get_access_token(installation_id).token
        gh = Github(access_token)
        repo = gh.get_repo(repo_name)
    except Exception as e:
        logger.error("Failed to auth GitHub App for QA: %s", e)
        return
    
    # Set commit status to PENDING immediately
    _set_commit_status(repo, commit_sha, "pending", "SlothOps QA is running...", pr_url)
        
    # 1. Create a running QA Record in DB
    report_id = f"qa-{pr_number}-{commit_sha[:8]}"
    report = QAReport(
        id=report_id,
        workspace_id=workspace_id,
        pr_number=pr_number,
        pr_url=pr_url,
        commit_sha=commit_sha,
        repo_name=repo_name,
        overall_status=QAStatus.RUNNING.value,
        summary="QA tests are currently running..."
    )
    await db.create_qa_report(report, db_path)
    
    # 2. Clone repo locally in a sandbox
    # Using the standard mechanism tested in `test_runner.py`
    clone_url = repo.clone_url.replace("https://", f"https://x-access-token:{access_token}@")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        logger.info("🧪 QA Sandbox: Cloning %s @ %s...", repo_name, commit_sha)
        try:
            # We clone the specific PR branch/merge commit 
            subprocess.run(
                ["git", "clone", clone_url, tmpdir],
                check=True, capture_output=True, text=True, timeout=120
            )
            subprocess.run(
                ["git", "checkout", commit_sha],
                cwd=tmpdir, check=True, capture_output=True, text=True, timeout=30
            )
        except subprocess.TimeoutExpired:
            logger.error("QA Sandbox Failed: Git operations timed out.")
            await db.update_qa_report(report_id, db_path, overall_status=QAStatus.FAILED.value, summary="Failed to setup QA sandbox. Git operations timed out.")
            return
        except subprocess.CalledProcessError as e:
            logger.error("QA Sandbox Failed to clone: %s", e.stderr)
            await db.update_qa_report(report_id, db_path, overall_status=QAStatus.FAILED.value, summary=f"Failed to setup QA sandbox. Clone error.")
            return

        # Detect tech stack
        stack_config = detect_stack(tmpdir)
        logger.info("🔍 Detected stack: %s/%s", stack_config.get('language'), stack_config.get('framework'))
        
        # Install dependencies using detected command
        install_cmd = stack_config.get("install_command")
        if install_cmd:
            logger.info("🧪 QA Sandbox: Running '%s'...", install_cmd)
            try:
                subprocess.run(install_cmd.split(), cwd=tmpdir, capture_output=True, text=True, timeout=120)
            except subprocess.TimeoutExpired:
                logger.warning("Install command timed out.")
            except Exception:
                pass
                
        # Additionally, we need to know what files were changed in the PR 
        # to generate specifically targeted functionality tests.
        pr = repo.get_pull(pr_number)
        gh_files = pr.get_files()
        changed_files = []
        changed_paths = []
        for f in gh_files:
            if f.status == "removed":
                continue
            changed_paths.append(f.filename)
            try:
                content_file = repo.get_contents(f.filename, ref=commit_sha)
                if not isinstance(content_file, list):
                    changed_files.append({
                        "path": f.filename,
                        "content": content_file.decoded_content.decode("utf-8", errors="replace")
                    })
            except Exception:
                pass
                
        # --- LANGCHAIN ORCHESTRATION ---
        logger.info("🛠️ Initializing LangChain Orchestrator...")
        
        # Tools definitions
        async def tool_static_analysis() -> dict:
            """Run static analysis (linters, type checkers) on the repository."""
            logger.info("Agent invoked StaticAnalysis")
            res = await run_static_analysis(tmpdir, changed_paths, stack_config)
            report.static_analysis = res
            return res

        async def tool_functionality() -> dict:
            """Generate and run unit tests for changed files to verify functionality."""
            logger.info("Agent invoked FunctionalityTesting")
            res = await run_functionality_tests(tmpdir, changed_files, gemini_api_key, stack_config)
            report.functionality = res
            return res

        async def tool_vapt() -> dict:
            """Run Vulnerability Assessment and Penetration Testing."""
            logger.info("Agent invoked VAPTScan")
            res = await run_vapt_scan(tmpdir, stack_config)
            report.vapt = res
            return res

        async def tool_stress_test() -> dict:
            """Run high-load stress testing against a locally spawned instance."""
            logger.info("Agent invoked StressTesting")
            res = await run_stress_test(tmpdir, stack_config)
            report.stress_test = res
            return res
            
        async def tool_regression() -> dict:
            """Run the existing unit/integration test suites defined in the repository."""
            logger.info("Agent invoked RegressionTesting")
            res = await run_regression_tests(tmpdir, stack_config)
            report.regression = res
            return res
            
        async def tool_performance() -> dict:
            """Measure baseline performance and endpoint response times."""
            logger.info("Agent invoked PerformanceCheck")
            res = await run_performance_check(tmpdir, stack_config)
            report.performance = res
            return res

        logger.info("🛠️ Initializing Native GenAI Orchestrator...")
        try:
            client = genai.Client(api_key=gemini_api_key)
            system_msg = (
                "You are the QA Orchestrator for SlothOps. Decide which QA tools to run.\n"
                "Must run: StaticAnalysis, VAPTScan.\n"
                "If code files changed: FunctionalityTesting, RegressionTesting, PerformanceCheck.\n"
                "If web endpoints/infra involved: StressTesting.\n"
                "Output ONLY a raw JSON array of strings representing the exact tool names to run.\n"
                "Valid tools: [\"StaticAnalysis\", \"FunctionalityTesting\", \"VAPTScan\", \"StressTesting\", \"RegressionTesting\", \"PerformanceCheck\"]\n"
                "Do not output markdown blocks or any other text."
            )
            user_msg = f"Changed {len(changed_paths)} files:\\n{changed_paths}\\nStack: {stack_config.get('language')}/{stack_config.get('framework')}\\nHas start_command: {bool(stack_config.get('start_command'))}\\nHas test_command: {bool(stack_config.get('test_command'))}"
            
            logger.info("🛠️ Asking LLM for QA Agent list...")
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=user_msg,
                config=genai.types.GenerateContentConfig(
                    system_instruction=system_msg,
                    temperature=0.0
                )
            )
            raw_text = response.text.replace("```json", "").replace("```", "").strip()
            tool_names = json.loads(raw_text)
            logger.info(f"🧠 LLM chose tools: {tool_names}")
            
            langchain_summary = "QA Orchestration completed. Tools run: " + ", ".join(tool_names)
            
            for t in tool_names:
                if t == "StaticAnalysis": await tool_static_analysis()
                elif t == "FunctionalityTesting": await tool_functionality()
                elif t == "VAPTScan": await tool_vapt()
                elif t == "StressTesting": await tool_stress_test()
                elif t == "RegressionTesting": await tool_regression()
                elif t == "PerformanceCheck": await tool_performance()
                else: logger.warning(f"Unknown tool requested by LLM: {t}")
                
        except Exception as e:
            logger.error("Native Orchestrator failed: %s", e)
            langchain_summary = f"Orchestrator encountered an error while running tools: {e}"

        # Aggregate status across all sub-agents (some might not have run and remain None)
        final_status = QAStatus.PASSED.value
        all_res = [report.static_analysis, report.functionality, report.vapt, report.stress_test, report.regression, report.performance]
        
        # Filter None and check statuses
        ran_res = [r for r in all_res if r is not None]
        if not ran_res:
             final_status = QAStatus.WARNING.value
             summary_text = "No tools ran."
        else:
            if any(r.get("status") == "failed" for r in ran_res):
                final_status = QAStatus.FAILED.value
            elif any(r.get("status") == "warning" for r in ran_res):
                final_status = QAStatus.WARNING.value
            
            summary_parts = []
            if report.static_analysis: summary_parts.append(f"**Static Analysis:** {report.static_analysis.get('summary', 'Done')}")
            if report.functionality: summary_parts.append(f"**Functionality:** {report.functionality.get('summary', 'Done')}")
            if report.vapt: summary_parts.append(f"**VAPT Scan:** {report.vapt.get('summary', 'Done')}")
            if report.stress_test: summary_parts.append(f"**Stress Test:** {report.stress_test.get('summary', 'Done')}")
            if report.regression: summary_parts.append(f"**Regression:** {report.regression.get('summary', 'Done')}")
            if report.performance: summary_parts.append(f"**Performance:** {report.performance.get('summary', 'Done')}")
            
            summary_text = "\n".join(summary_parts) + f"\n\n**Orchestrator Note:** {langchain_summary}"
            
            # --- LLM Fix Suggestion ---
            if final_status in [QAStatus.FAILED.value, QAStatus.WARNING.value]:
                logger.info("QA failed. Asking LLM for a fix recommendation...")
                try:
                    error_context = ""
                    if report.static_analysis and report.static_analysis.get("issues"):
                        error_context += f"Static Analysis Issues: {report.static_analysis['issues']}\n"
                    if report.functionality and report.functionality.get("failures"):
                        error_context += f"Functionality Test Failures: {report.functionality['failures']}\n"
                    if report.vapt and report.vapt.get("status") != "passed":
                        error_context += f"VAPT Logs: {report.vapt.get('logs', report.vapt.get('summary'))}\n"
                    if report.stress_test and report.stress_test.get("status") != "passed":
                        error_context += f"Stress Test Logs: {report.stress_test.get('logs', report.stress_test.get('summary'))}\n"
                    if report.regression and report.regression.get("status") != "passed":
                        error_context += f"Regression Logs: {report.regression.get('logs', report.regression.get('summary'))}\n"
                    if report.performance and report.performance.get("status") != "passed":
                        error_context += f"Performance Logs: {report.performance.get('logs', report.performance.get('summary'))}\n"

                    fix_prompt = (
                        "The QA pipeline failed for the following reasons. "
                        "Please analyze the provided error logs and write a concise technical explanation of what went wrong. "
                        "Then, provide code snippets or concrete recommendations to fix the issues.\n\n"
                        f"Error Logs:\n{error_context}"
                    )
                    fix_resp = client.models.generate_content(
                        model='gemini-2.5-pro',
                        contents=fix_prompt,
                    )
                    summary_text += f"\n\n### 🤖 AI Auto-Fix Recommendation\n\n{fix_resp.text}\n"
                except Exception as e:
                    logger.error("Failed to generate fix recommendation: %s", e)
            # --------------------------

        report.overall_status = final_status
        report.summary = summary_text
        
        # 9. Database update
        await db.update_qa_report(
            report_id, 
            db_path, 
            overall_status=final_status,
            summary=report.summary,
            static_analysis=report.static_analysis,
            functionality=report.functionality,
            vapt=report.vapt,
            stress_test=report.stress_test,
            regression=report.regression,
            performance=report.performance
        )
        
        # 6. Post PR Comment
        post_qa_report_comment(pr_url, report.model_dump(), repo, repo_name)
        
        # 10. Send Email
        if QA_EMAIL_RECIPIENT and SMTP_HOST:
            logger.info("📧 Sending QA Report Email...")
            report_dict = {
                "pr_number": report.pr_number,
                "pr_url": report.pr_url,
                "repo_name": report.repo_name,
                "overall_status": final_status,
                "summary": report.summary,
            }
            send_qa_report_email(
                report_dict, 
                QA_EMAIL_RECIPIENT, 
                SMTP_HOST, 
                SMTP_PORT, 
                SMTP_USER, 
                SMTP_PASSWORD
            )
            
        logger.info("✅ QA Pipeline completed for PR #%s -> Status: %s", pr_number, final_status)
        
        # 11. Set final commit status on GitHub
        if final_status == QAStatus.PASSED.value:
            _set_commit_status(repo, commit_sha, "success", "All QA checks passed ✅", pr_url)
        elif final_status == QAStatus.WARNING.value:
            _set_commit_status(repo, commit_sha, "success", "QA passed with warnings ⚠️", pr_url)
        else:
            _set_commit_status(repo, commit_sha, "failure", "QA checks failed ❌ — fix issues before merging", pr_url)
