"""
SlothOps Engine — LLM Fixer (Gemini Version)
Constructs prompts, calls Google Gemini 2.5 Pro, and parses the JSON response
into a validated LLMFixResponse.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from google import genai
from google.genai import types

from models import CallFrame, IssueRecord, LLMFixResponse
from redactor import redact

logger = logging.getLogger("slothops.llm_fixer")

# ── System prompt (exact copy from AI_CONTEXT.md) ───────────────────────

SYSTEM_PROMPT = """You are SlothOps, an automated production bug remediation system.

RULES:
 1. You MUST fix the root cause, not hide the symptom.
 2. You MUST NOT wrap code in empty try/catch blocks.
 3. You MUST NOT suppress or swallow errors silently.
 4. You MUST NOT remove existing error logging or monitoring.
 5. You MUST NOT comment out failing code.
 6. You MUST NOT add generic fallbacks without clear reasoning.
 7. You MUST preserve the original code style and conventions.
 8. You MUST explain your root cause hypothesis clearly.
 9. If the fix requires changes to multiple files, specify each file separately.
 10. If you are not confident about the fix, set confidence to "low"
     and explain why.
 11. You MUST return valid JSON matching the specified format.
 12. You MUST return the COMPLETE file content for each changed file,
     not just the diff or snippet.
 13. You MUST generate at least one test file that validates your fix.
     Place tests at the conventional path (e.g. tests/routes/users.test.ts).
     Return test files in the "generated_tests" array using the same
     FileChange format as files_changed.
     Tests should cover: the original crash case, the fixed behavior,
     and at least one edge case.

DEEP SCAN (for recurrence / repeated errors):
If you are analyzing a recurrence of a previously-fixed bug, you MUST
set deep_scan_needed: true and list specific file paths in deep_scan_files
if the root cause appears to originate from a file not included in the
provided context. The call chain below shows the full execution path."""

TEST_FAILURE_PROMPT = """The fix and tests you generated previously have FAILED validation in the local test environment.

TEST OUTPUT (stdout/stderr):
{test_output}

PREVIOUS FIX FILES:
{previous_files}

PREVIOUS GENERATED TESTS:
{previous_tests}

Please analyze the test failure output above. Identify why the tests or the fix failed.
Generate a NEW fix and/or NEW tests that resolve the failure.
Return the updated files in the exact same JSON format."""


def _build_user_prompt(
    issue: IssueRecord,
    code_context: dict[str, str],
    previous_pr_url: Optional[str] = None,
    call_chain: list[CallFrame] | None = None,
) -> str:
    """Build the user prompt from the template in AI_CONTEXT.md."""
    # Redact the stack trace before including it
    redacted_trace = redact(issue.stack_trace or "")

    # Main file content
    main_file_path = issue.file_path or "unknown"
    main_content = code_context.get(main_file_path, "File content not available")

    # Related files (everything except main and test)
    related_parts: list[str] = []
    test_path: Optional[str] = None
    test_content: str = "No test file found"

    for path, content in code_context.items():
        if path == main_file_path:
            continue
        if ".test." in path or "test_" in path:
            test_path = path
            test_content = content
        else:
            related_parts.append(f"--- {path} ---\n{content}")

    related_block = "\n\n".join(related_parts) if related_parts else "No related files found"
    test_label = test_path or "unknown"

    prompt = f"""PRODUCTION ERROR:
  Type: {issue.error_type}
  Message: {issue.error_message}
  File: {issue.file_path}
  Function: {issue.function_name}
  Line: {issue.line_number}
  Occurrences: {issue.occurrence_count}

STACK TRACE:
{redacted_trace}

SOURCE FILE ({main_file_path}):
{main_content}

RELATED FILES:
{related_block}

TEST FILE ({test_label}):
{test_content}"""

    # Call chain context for recurrence
    if call_chain:
        chain_lines = []
        for i, frame in enumerate(call_chain):
            chain_lines.append(f"  [{i+1}] {frame.function_name} @ {frame.file_path}:{frame.line_number}")
            if hasattr(frame, "context_line") and frame.context_line:
                chain_lines.append(f"      > {frame.context_line}")
        prompt += f"""

FULL CALL CHAIN:
{" | ".join(["CRASH"] + [f"CALLER {i}" for i in range(len(call_chain)-1, 0, -1)])}
{chr(10).join(chain_lines)}
"""

    # Recurrence context
    if previous_pr_url:
        prompt += f"""

IMPORTANT: A previous fix was attempted (PR: {previous_pr_url}) but the same error has reoccurred.
The previous fix was insufficient. Please analyze why and propose a deeper fix."""

    prompt += "\n\nGenerate the fix following the rules and strict JSON response format specified."
    return prompt


def _parse_response(raw: str) -> LLMFixResponse:
    """Parse the raw JSON string from Gemini into a validated model."""
    data = json.loads(raw)
    return LLMFixResponse(**data)


def generate_fix(
    issue: IssueRecord,
    code_context: dict[str, str],
    gemini_api_key: str,
    previous_pr_url: Optional[str] = None,
    call_chain: list[CallFrame] | None = None,
    repo=None,
) -> LLMFixResponse:
    """
    Call Gemini 2.5 Pro to generate a fix for the given issue.

    Raises:
        RuntimeError: If the LLM returns invalid JSON twice.
    """
    client = genai.Client(api_key=gemini_api_key)
    user_prompt = _build_user_prompt(issue, code_context, previous_pr_url, call_chain)

    # Convert Pydantic scheme to type for Gemini structured output
    config_dict = {
        "temperature": 0.2,
        "response_mime_type": "application/json",
        "system_instruction": SYSTEM_PROMPT,
        # Pydantic native schema translation
        "response_schema": LLMFixResponse.model_json_schema(),
    }

    config = types.GenerateContentConfig(**config_dict)

    for attempt in range(2):
        logger.info("Calling Gemini 2.5 Pro (attempt %d)...", attempt + 1)
        
        # We send only the user prompt because system_instruction is in the config
        messages = [{"role": "user", "parts": [{"text": user_prompt}]}]
        if attempt > 0:
            # We add a retry context if json parsing failed manually, 
            # though structured output usually prevents this.
            messages.append({"role": "user", "parts": [{"text": "Your previous response was not valid JSON. Please retry."}]})

        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=messages,
            config=config,
        )

        raw_content = response.text or ""

        try:
            fix = _parse_response(raw_content)
            # Second-pass: if LLM requested more files, fetch them and retry
            if hasattr(fix, "deep_scan_needed") and fix.deep_scan_needed and hasattr(fix, "deep_scan_files") and fix.deep_scan_files:
                from code_fetcher import fetch_requested_files
                additional = fetch_requested_files(fix.deep_scan_files, repo)
                if additional:
                    code_context = {**code_context, **additional}
                    user_prompt = _build_user_prompt(issue, code_context, previous_pr_url, call_chain)
                    messages = [{"role": "user", "parts": [{"text": user_prompt}]}]
                    response = client.models.generate_content(
                        model="gemini-2.5-pro",
                        contents=messages,
                        config=config,
                    )
                    fix = _parse_response(response.text or "")
            return fix
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("JSON parse failed (attempt %d): %s", attempt + 1, exc)

    raise RuntimeError(
        f"LLM returned invalid JSON after 2 attempts for issue {issue.id}"
    )

def generate_infra_recommendation(issue: IssueRecord) -> str:
    """Uses Gemini 1.5 Flash to generate a DevOps recommendation for infra errors."""
    prompt = f"""
You are SlothOps, a Senior DevOps AI. 
A critical infrastructure error has occurred in production. 

ERROR SIGNATURE:
Type: {issue.error_type}
Message: {issue.error_message}
Occurrences: {issue.occurrence_count}

STACK TRACE:
{issue.stack_trace or "No stack trace available."}

Provide a concise, 1-paragraph actionable recommendation for the DevOps team.
Do NOT output JSON. Just output plain text markdown. 
"""
    # Assuming gemini_api_key is available or we pass it? Wait, where do we get the API key?
    # Actually, pipeline.py passes issue to generate_infra_recommendation, but not the API key!
    # I need to get the API key. Let's import config or use load_dotenv.
    import os
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt,
        )
        return response.text or "Check infrastructure dependencies and network connectivity."
    except Exception as e:
        logger.error("[%s] Infra recommendation failed: %s", issue.id[:8], e)
        return "Automatic recommendation failed due to API limits."


async def retry_fix_with_test_failure(
    issue: IssueRecord,
    code_context: dict[str, str],
    previous_fix: LLMFixResponse,
    test_output: str,
    gemini_api_key: str,
    previous_pr_url: Optional[str] = None,
    call_chain: list[CallFrame] | None = None,
) -> LLMFixResponse:
    """
    Call Gemini again to fix the fix based on local test failure output.
    """
    client = genai.Client(api_key=gemini_api_key)
    base_prompt = _build_user_prompt(issue, code_context, previous_pr_url, call_chain)
    
    prev_files = "\n".join([f"--- {f.path} ---\n{f.fixed_content}" for f in previous_fix.files_changed])
    prev_tests = "\n".join([f"--- {t.path} ---\n{t.fixed_content}" for t in previous_fix.generated_tests])
    
    retry_prompt = TEST_FAILURE_PROMPT.format(
        test_output=test_output,
        previous_files=prev_files,
        previous_tests=prev_tests
    )
    
    full_prompt = base_prompt + "\n\n" + retry_prompt

    config_dict = {
        "temperature": 0.2,
        "response_mime_type": "application/json",
        "system_instruction": SYSTEM_PROMPT,
        "response_schema": LLMFixResponse.model_json_schema(),
    }
    config = types.GenerateContentConfig(**config_dict)

    logger.info("Calling Gemini 2.5 Pro (Refix Attempt)...")
    messages = [{"role": "user", "parts": [{"text": full_prompt}]}]
    
    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=messages,
        config=config,
    )
    
    raw_content = response.text or ""
    try:
        return _parse_response(raw_content)
    except Exception as e:
        logger.warning(f"Refix JSON parse failed: {e}. Falling back to original fix.")
        return previous_fix
