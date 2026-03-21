"""
SlothOps Engine — Error Classifier
Heuristic classifier that categorises errors as:
  code | infra | dependency | unknown

Only "code" errors proceed to fix generation.
"""

from __future__ import annotations

from models import Classification

# ── Signal lists ─────────────────────────────────────────────────────────

INFRA_SIGNALS: list[str] = [
    "ECONNREFUSED",
    "ETIMEDOUT",
    "ECONNRESET",
    "502",
    "503",
    "504",
    "OOMKilled",
    "heap out of memory",
    "SIGKILL",
    "SIGTERM",
    "connection refused",
    "connection dropped",
    "timeout exceeded",
    "certificate",
    "DNS",
]

# Infra signals that only count when paired with connection/timeout words
INFRA_CONTEXTUAL: list[str] = [
    "database",
    "redis",
]

CODE_ERROR_TYPES: list[str] = [
    "TypeError",
    "ReferenceError",
    "RangeError",
    "SyntaxError",
    "URIError",
]


def classify(
    error_type: str | None = None,
    error_message: str | None = None,
    stack_trace: str | None = None,
    file_path: str | None = None,
) -> str:
    """
    Return one of: ``code``, ``infra``, ``dependency``, ``unknown``.

    The combined text of *error_type*, *error_message*, and *stack_trace*
    is checked against signal lists.  *file_path* is checked for
    ``node_modules`` to detect dependency errors.
    """
    combined = " ".join(
        part for part in (error_type, error_message, stack_trace) if part
    ).lower()

    # 1) Dependency check (node_modules in file path)
    if file_path and "node_modules" in file_path:
        return Classification.DEPENDENCY.value

    # 2) Infra signals (direct match)
    for signal in INFRA_SIGNALS:
        if signal.lower() in combined:
            return Classification.INFRA.value

    # 3) Infra contextual signals (need a pairing keyword)
    connection_keywords = ["connection", "timeout", "refused", "reset"]
    for signal in INFRA_CONTEXTUAL:
        if signal.lower() in combined:
            if any(kw in combined for kw in connection_keywords):
                return Classification.INFRA.value

    # 4) Code signals (error_type matches known JS/TS error types)
    if error_type and error_type in CODE_ERROR_TYPES:
        return Classification.CODE.value

    # 5) Default
    return Classification.UNKNOWN.value
