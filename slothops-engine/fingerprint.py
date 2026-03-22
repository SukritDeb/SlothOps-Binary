"""
SlothOps Engine — Fingerprinting & Deduplication
Computes a SHA-256 fingerprint for each error and decides whether
the pipeline should create a new record, skip, or re-trigger.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Optional

from models import DedupeAction, IssueStatus


# 10-minute cooldown between re-triggers for the same fingerprint
COOLDOWN = timedelta(minutes=10)


def compute_fingerprint(
    error_type: str | None,
    file_path: str | None,
    function_name: str | None,
    error_message: str | None = None,
) -> str:
    """
    Return a hex SHA-256 hash of the concatenated inputs.

    ``fingerprint = sha256(error_type + file_path + function_name + error_message)``
    """
    raw = "".join(part or "" for part in (error_type, file_path, function_name, error_message))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def check_dedup(
    existing_status: str | None,
    existing_updated_at: datetime | None = None,
) -> DedupeAction:
    """
    Given the status (and update timestamp) of an *existing* issue with the
    same fingerprint, decide what to do.

    Returns:
        ``DedupeAction.CREATE``    – no existing record (status is None)
        ``DedupeAction.SKIP``      – PR is open or issue is ignored
        ``DedupeAction.RETRIGGER`` – merged fix failed; re-run pipeline

    A cooldown of 10 minutes prevents rapid re-triggers.
    """
    if existing_status is None:
        return DedupeAction.CREATE

    # PR is still open → do nothing
    if existing_status == IssueStatus.PR_CREATED.value:
        return DedupeAction.SKIP

    # Issue was already ignored → do nothing
    if existing_status == IssueStatus.IGNORED.value:
        return DedupeAction.SKIP

    # Previously merged fix → re-trigger (with cooldown)
    if existing_status == IssueStatus.PR_MERGED.value:
        if existing_updated_at:
            elapsed = datetime.utcnow() - existing_updated_at
            if elapsed < COOLDOWN:
                return DedupeAction.SKIP
        return DedupeAction.RETRIGGER

    # Any other status (received, triaging, classified, fixing, etc.)
    # means the pipeline is already working on it → skip
    return DedupeAction.SKIP
