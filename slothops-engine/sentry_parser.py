"""
SlothOps Engine — Sentry Webhook Parser
Extracts error metadata and the top application-level stack frame
from a Sentry webhook payload.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, Optional

from models import IssueRecord, IssueStatus


def _extract_frames(payload: dict) -> list[dict]:
    """
    Walk the Sentry payload to find stack-trace frames.

    Sentry nests frames under:
      event.exception.values[*].stacktrace.frames
    """
    event = payload.get("data", {}).get("event", None)
    if event is None:
        event = payload.get("event", payload)

    exception_info = event.get("exception", {})
    values = exception_info.get("values", [])

    frames: list[dict] = []
    for exc_val in values:
        stacktrace = exc_val.get("stacktrace", {})
        frames.extend(stacktrace.get("frames", []))

    return frames


def _is_app_frame(frame: dict) -> bool:
    """Return True if the frame is NOT from node_modules / external libs."""
    filename = frame.get("filename", "") or frame.get("abs_path", "")
    if "node_modules" in filename:
        return False
    # Sentry sometimes marks app frames explicitly
    if frame.get("in_app") is False:
        return False
    return True


def _build_stack_trace_string(frames: list[dict]) -> str:
    """Build a human-readable stack trace from frame dicts."""
    lines = []
    for f in frames:
        filename = f.get("filename", "?")
        lineno = f.get("lineno", "?")
        func = f.get("function", "?")
        context = f.get("context_line", "")
        lines.append(f"  at {func} ({filename}:{lineno})")
        if context:
            lines.append(f"    > {context.strip()}")
    return "\n".join(lines)


def parse_sentry_webhook(payload: dict) -> IssueRecord:
    """
    Parse a Sentry webhook JSON payload into an ``IssueRecord``.

    Strategy:
      1. Extract error type + message from ``exception.values``
      2. Gather all stack frames and filter to application frames
      3. Use the **last** (top of stack) application frame for
         ``file_path``, ``function_name``, ``line_number``
      4. Build a combined stack-trace string
      5. Return a new ``IssueRecord`` with status ``received``
    """
    event = payload.get("data", {}).get("event", None)
    if event is None:
        event = payload.get("event", payload)

    # ── Error type & message ─────────────────────────────────────────
    error_type: Optional[str] = None
    error_message: Optional[str] = None

    exception_info = event.get("exception", {})
    exc_values = exception_info.get("values", [])
    if exc_values:
        top_exc = exc_values[-1]  # last is the outermost
        error_type = top_exc.get("type")
        error_message = top_exc.get("value")

    # Fallback: use event-level message
    if not error_message:
        error_message = event.get("message", event.get("title"))
    if not error_type:
        error_type = event.get("type")

    # ── Stack frames ─────────────────────────────────────────────────
    all_frames = _extract_frames(payload)
    app_frames = [f for f in all_frames if _is_app_frame(f)]

    file_path: Optional[str] = None
    function_name: Optional[str] = None
    line_number: Optional[int] = None

    if app_frames:
        top_frame = app_frames[-1]  # last frame = top of call stack
        file_path = top_frame.get("filename") or top_frame.get("abs_path")
        
        if file_path:
            if "/var/task/" in file_path:
                file_path = file_path.split("/var/task/")[-1]
            if file_path.endswith(".js"):
                file_path = file_path[:-3] + ".ts"
                
        function_name = top_frame.get("function")
        line_number = top_frame.get("lineno")

    stack_trace_str = _build_stack_trace_string(all_frames)

    # ── Build record ─────────────────────────────────────────────────
    return IssueRecord(
        id=str(uuid.uuid4()),
        error_type=error_type,
        error_message=error_message,
        file_path=file_path,
        function_name=function_name,
        line_number=line_number,
        stack_trace=stack_trace_str,
        raw_payload=json.dumps(payload),
        status=IssueStatus.RECEIVED.value,
    )
