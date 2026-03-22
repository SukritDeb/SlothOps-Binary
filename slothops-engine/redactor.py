"""
SlothOps Engine — PII & Secret Redactor
Strips sensitive data from text BEFORE it reaches the LLM or gets logged.
Each match is replaced with [REDACTED_{PATTERN_NAME}].
"""

from __future__ import annotations

import re
from typing import List, Tuple

# ── Ordered list of (pattern_name, compiled_regex) ───────────────────────
# Order matters: JWT before UUID (JWTs contain UUID-like segments).

_PATTERNS: List[Tuple[str, re.Pattern]] = [
    (
        "JWT",
        re.compile(r"eyJ[A-Za-z0-9\-_]+\.eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+"),
    ),
    (
        "BEARER",
        re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*"),
    ),
    (
        "API_KEY",
        re.compile(
            r"(?:api[_\-]?key|apikey|secret|token|password|auth)\s*[=:]\s*[\"']?[A-Za-z0-9\-._~+/]{16,}",
            re.IGNORECASE,
        ),
    ),
    (
        "CREDIT_CARD",
        re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
    ),
    (
        "EMAIL",
        re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"),
    ),
    (
        "IP_ADDRESS",
        re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    ),
    (
        "UUID",
        re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE),
    ),
    (
        "PHONE",
        re.compile(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"),
    ),
]


def redact(text: str) -> str:
    """
    Strip all PII and secrets from ``text``.

    Returns a copy of ``text`` with every sensitive match replaced by
    ``[REDACTED_{PATTERN_NAME}]``.
    """
    if not text:
        return text

    for name, pattern in _PATTERNS:
        text = pattern.sub(f"[REDACTED_{name}]", text)

    return text
