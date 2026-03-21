"""Tests for fingerprint.py — hashing and dedup logic."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timedelta

from fingerprint import compute_fingerprint, check_dedup
from models import DedupeAction, IssueStatus


# ── Fingerprint hashing ─────────────────────────────────────────────────

class TestComputeFingerprint:
    def test_same_inputs_same_hash(self):
        fp1 = compute_fingerprint("TypeError", "src/routes/users.ts", "getUserProfile")
        fp2 = compute_fingerprint("TypeError", "src/routes/users.ts", "getUserProfile")
        assert fp1 == fp2

    def test_different_error_type(self):
        fp1 = compute_fingerprint("TypeError", "src/routes/users.ts", "getUserProfile")
        fp2 = compute_fingerprint("ReferenceError", "src/routes/users.ts", "getUserProfile")
        assert fp1 != fp2

    def test_different_file_path(self):
        fp1 = compute_fingerprint("TypeError", "src/routes/users.ts", "getUserProfile")
        fp2 = compute_fingerprint("TypeError", "src/routes/orders.ts", "getUserProfile")
        assert fp1 != fp2

    def test_different_function_name(self):
        fp1 = compute_fingerprint("TypeError", "src/routes/users.ts", "getUserProfile")
        fp2 = compute_fingerprint("TypeError", "src/routes/users.ts", "getUser")
        assert fp1 != fp2

    def test_hash_is_hex_sha256(self):
        fp = compute_fingerprint("TypeError", "file.ts", "func")
        assert len(fp) == 64  # SHA-256 hex digest
        assert all(c in "0123456789abcdef" for c in fp)

    def test_none_inputs(self):
        """None values should not crash — treated as empty strings."""
        fp = compute_fingerprint(None, None, None)
        assert isinstance(fp, str)
        assert len(fp) == 64


# ── Dedup logic ──────────────────────────────────────────────────────────

class TestCheckDedup:
    def test_no_existing_record(self):
        assert check_dedup(None) == DedupeAction.CREATE

    def test_pr_created_skip(self):
        assert check_dedup(IssueStatus.PR_CREATED.value) == DedupeAction.SKIP

    def test_ignored_skip(self):
        assert check_dedup(IssueStatus.IGNORED.value) == DedupeAction.SKIP

    def test_pr_merged_retrigger(self):
        """Merged but error recurs → re-trigger."""
        old_time = datetime.utcnow() - timedelta(minutes=20)
        assert check_dedup(IssueStatus.PR_MERGED.value, old_time) == DedupeAction.RETRIGGER

    def test_pr_merged_cooldown_skip(self):
        """Merged recently (within 10 min) → skip to avoid spam."""
        recent_time = datetime.utcnow() - timedelta(minutes=2)
        assert check_dedup(IssueStatus.PR_MERGED.value, recent_time) == DedupeAction.SKIP

    def test_received_status_skip(self):
        """Pipeline already working on it → skip."""
        assert check_dedup(IssueStatus.RECEIVED.value) == DedupeAction.SKIP

    def test_fixing_status_skip(self):
        assert check_dedup(IssueStatus.FIXING.value) == DedupeAction.SKIP
