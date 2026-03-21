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

from models import IssueRecord, LLMFixResponse
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
    not just the diff or snippet."""


def _build_user_prompt(
    issue: IssueRecord,
    code_context: dict[str, str],
    previous_pr_url: Optional[str] = None,
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
) -> LLMFixResponse:
    """
    Call Gemini 2.5 Pro to generate a fix for the given issue.

    Raises:
        RuntimeError: If the LLM returns invalid JSON twice.
    """
    client = genai.Client(api_key=gemini_api_key)
    user_prompt = _build_user_prompt(issue, code_context, previous_pr_url)

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
            return _parse_response(raw_content)
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
