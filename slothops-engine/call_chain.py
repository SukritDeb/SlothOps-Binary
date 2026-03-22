"""
SlothOps Engine — Call Chain Tracer
Parses Sentry stack trace frames into a structured call chain
for deep-call-chain tracing on issue recurrence.
"""

from __future__ import annotations

from models import CallFrame

_MAX_CALL_CHAIN_FILES = 5


def normalize_path(path: str) -> str:
    """
    Normalize a Sentry frame path to a repo-relative path.

    - Strips Vercel/λ prefixes like /var/task/
    - Converts .js → .ts
    """
    if not path:
        return ""
    if "/var/task/" in path:
        path = path.split("/var/task/", 1)[-1]
    if path.endswith(".js"):
        path = path[:-3] + ".ts"
    return path


def parse_call_chain(frames: list[dict]) -> list[CallFrame]:
    """
    Convert raw Sentry frame dicts into a structured CallFrame list.

    Filters to application frames only (skips node_modules).
    Frames are ordered top-of-stack first (caller 1 at index 0,
    crashing function at the last index).

    Returns up to _MAX_CALL_CHAIN_FILES frames.
    """
    app_frames: list[CallFrame] = []

    for f in frames:
        filename = f.get("filename", "") or f.get("abs_path", "") or ""
        if "node_modules" in filename or f.get("in_app") is False:
            continue

        normalized = normalize_path(filename)
        if not normalized:
            continue

        app_frames.append(CallFrame(
            file_path=normalized,
            function_name=f.get("function") or "?",
            line_number=f.get("lineno") or 0,
            context_line=(f.get("context_line") or "").strip(),
        ))

        if len(app_frames) >= _MAX_CALL_CHAIN_FILES:
            break

    return app_frames
