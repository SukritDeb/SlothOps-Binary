"""
SlothOps Engine — Style Reviewer
Reads a workspace's developer.json preferences, sends the LLM fix + rules
to Gemini, and returns style suggestions as a list of PR review comments.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from google import genai
from google.genai import types



logger = logging.getLogger("slothops.style_reviewer")

STYLE_REVIEW_PROMPT = """You are a code style reviewer for the SlothOps automated bug remediation system.

A developer has defined their code style preferences in a `developer.json` configuration.
Code changes have been proposed in a Pull Request. Your job is to review the files
against the developer's style preferences and suggest improvements.

IMPORTANT RULES:
1. Only comment on style violations, NOT on the correctness of the fix.
2. Be specific: reference the file path and the exact code that violates the style.
3. Keep comments concise and actionable (1-2 sentences each).
4. If the fix already conforms to all style rules, return an empty array.
5. Return valid JSON: an array of objects with {{file, line_hint, comment}}.

DEVELOPER STYLE PREFERENCES:
{developer_config}

PROPOSED FILE CHANGES:
{files_changed}

Return a JSON array of style review comments. Example:
[
  {{"file": "src/routes/config.ts", "line_hint": "line 15", "comment": "Use `const` instead of `let` per project conventions."}},
  {{"file": "src/services/userService.ts", "line_hint": "line 42", "comment": "Replace console.log with winston logger per backend rules."}}
]

If no style violations found, return: []
"""


async def review_against_preferences(
    changed_files: list[dict],
    developer_config: dict,
    gemini_api_key: str,
) -> list[dict]:
    """
    Send the file changes + developer preferences to Gemini and get back style comments.
    changed_files: [{"path": str, "content": str}]
    Returns a list of {file, line_hint, comment} dicts.
    """
    if not developer_config:
        return []

    files_block = ""
    for fc in changed_files:
        files_block += f"\n--- {fc.get('path')} ---\n{fc.get('content')}\n"

    prompt = STYLE_REVIEW_PROMPT.format(
        developer_config=json.dumps(developer_config, indent=2),
        files_changed=files_block,
    )

    client = genai.Client(api_key=gemini_api_key)

    try:
        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )
        raw = response.text or "[]"
        comments = json.loads(raw)
        if isinstance(comments, list):
            logger.info("Style reviewer returned %d comment(s)", len(comments))
            return comments
        return []
    except Exception as e:
        logger.error("Style review failed: %s", e)
        return []
