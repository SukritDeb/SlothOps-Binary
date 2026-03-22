"""Tests for sentry_parser.py — webhook payload parsing."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from pathlib import Path

from sentry_parser import parse_sentry_webhook


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture() -> dict:
    with open(FIXTURES_DIR / "sentry_webhook.json") as f:
        return json.load(f)


# ── Fixture parsing ──────────────────────────────────────────────────────

class TestSentryParserWithFixture:
    def setup_method(self):
        self.payload = _load_fixture()
        self.issue, self.call_frames = parse_sentry_webhook(self.payload)

    def test_error_type(self):
        assert self.issue.error_type == "TypeError"

    def test_error_message(self):
        assert "displayName" in self.issue.error_message

    def test_file_path_is_app_frame(self):
        """Should pick the top APPLICATION frame, not node_modules."""
        assert self.issue.file_path == "src/routes/users.ts"

    def test_function_name(self):
        assert self.issue.function_name == "getUserProfile"

    def test_line_number(self):
        assert self.issue.line_number == 42

    def test_status_is_received(self):
        assert self.issue.status == "received"

    def test_has_uuid_id(self):
        """id should be a valid UUID-4 string."""
        parts = self.issue.id.split("-")
        assert len(parts) == 5

    def test_stack_trace_built(self):
        assert "getUserProfile" in self.issue.stack_trace
        assert "src/routes/users.ts" in self.issue.stack_trace

    def test_raw_payload_stored(self):
        assert self.issue.raw_payload is not None
        restored = json.loads(self.issue.raw_payload)
        assert "data" in restored or "event" in restored or "exception" in restored


# ── Call chain extraction ────────────────────────────────────────────────

class TestCallChainExtraction:
    def setup_method(self):
        self.payload = _load_fixture()
        self.issue, self.call_frames = parse_sentry_webhook(self.payload)

    def test_call_frames_returned(self):
        """Should return call frames alongside the issue."""
        assert isinstance(self.call_frames, list)
        assert len(self.call_frames) > 0

    def test_call_frames_skip_node_modules(self):
        """Call frames should only include app-level frames."""
        for frame in self.call_frames:
            assert "node_modules" not in frame.file_path

    def test_call_frames_match_issue_call_chain(self):
        """Call frames should be identical to issue.call_chain."""
        assert len(self.call_frames) == len(self.issue.call_chain)

    def test_call_frame_has_crash_site(self):
        """Last call frame should be the crash site."""
        last = self.call_frames[-1]
        assert last.file_path == "src/routes/users.ts"
        assert last.function_name == "getUserProfile"
        assert last.line_number == 42

    def test_call_frame_path_normalisation(self):
        """Paths should be repo-relative .ts paths."""
        for frame in self.call_frames:
            assert not frame.file_path.endswith(".js")
            assert "/var/task/" not in frame.file_path


# ── Node_modules filtering ──────────────────────────────────────────────

class TestNodeModulesFiltering:
    def test_only_node_modules_frames(self):
        """If ALL frames are node_modules, file_path should be None."""
        payload = {
            "event": {
                "exception": {
                    "values": [
                        {
                            "type": "Error",
                            "value": "oops",
                            "stacktrace": {
                                "frames": [
                                    {
                                        "filename": "node_modules/pkg/index.js",
                                        "function": "run",
                                        "lineno": 10,
                                        "in_app": False,
                                    }
                                ]
                            },
                        }
                    ]
                }
            }
        }
        issue, call_frames = parse_sentry_webhook(payload)
        assert issue.file_path is None
        assert call_frames == []


# ── Edge cases ───────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_payload(self):
        """Should not crash on a minimal/empty payload."""
        issue, call_frames = parse_sentry_webhook({})
        assert issue.id is not None
        assert issue.status == "received"
        assert call_frames == []

    def test_missing_exception_key(self):
        payload = {"event": {"message": "Something went wrong"}}
        issue, call_frames = parse_sentry_webhook(payload)
        assert issue.error_message == "Something went wrong"
        assert issue.file_path is None
        assert call_frames == []
