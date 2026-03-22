"""
SlothOps Engine — Context-Aware Code Reviewer
Evaluates proposed PR code changes against the overall structure
and function of the codebase, providing a functional description and suggestions.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from google import genai
from google.genai import types

logger = logging.getLogger("slothops.code_reviewer")

CODE_REVIEW_PROMPT = """You are a senior software architect running an automated code review for a Pull Request.

CODEBASE CONTEXT:
The following is an overview of the repository's structure and function (if available):
{codebase_context}

PROPOSED CODE CHANGES:
{files_changed}

YOUR TASK:
1. Provide a "simplified Description" of what these code changes actually do to the codebase.
2. Provide specific "suggestive changes" or improvements based on architectural best practices, potential bugs, or logical flaws in the diff.
3. Be friendly and highly technical.
4. If the code is perfect, say so, but still provide the functional description.

Format your entire response as a single markdown string containing:
### 🧠 Architecture & Logic Review
**What changed**: <your simplified description>
**Suggestions**: <your suggestive changes>
"""

async def review_pr_code(
    changed_files: list[dict],
    codebase_context: str,
    gemini_api_key: str,
) -> str:
    """
    Send the file changes + codebase context to Gemini and get back an architecture/logic review.
    changed_files: [{"path": str, "content": str}]
    Returns a markdown formatted string.
    """
    if not changed_files:
        return ""

    files_block = ""
    for fc in changed_files:
        files_block += f"\n--- {fc.get('path')} ---\n{fc.get('content')}\n"

    prompt = CODE_REVIEW_PROMPT.format(
        codebase_context=codebase_context or "(No codebase context available)",
        files_changed=files_block,
    )

    client = genai.Client(api_key=gemini_api_key)

    try:
        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt,
        )
        return response.text or ""
    except Exception as e:
        logger.error("Code review failed: %s", e)
        return ""
