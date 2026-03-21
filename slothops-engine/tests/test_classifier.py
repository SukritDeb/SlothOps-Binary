"""Tests for classifier.py — code vs infra vs dependency vs unknown."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from classifier import classify


# ── Infra signals ────────────────────────────────────────────────────────

class TestInfraClassification:
    def test_econnrefused(self):
        assert classify(error_message="connect ECONNREFUSED 127.0.0.1:5432") == "infra"

    def test_etimedout(self):
        assert classify(error_message="connect ETIMEDOUT") == "infra"

    def test_econnreset(self):
        assert classify(error_message="read ECONNRESET") == "infra"

    def test_502_status(self):
        assert classify(error_message="Request failed with status code 502") == "infra"

    def test_503_status(self):
        assert classify(error_message="Service Unavailable 503") == "infra"

    def test_oomkilled(self):
        assert classify(error_message="Process exited with OOMKilled") == "infra"

    def test_heap_out_of_memory(self):
        assert classify(error_message="FATAL ERROR: heap out of memory") == "infra"

    def test_sigterm(self):
        assert classify(error_message="Process received SIGTERM") == "infra"

    def test_connection_refused(self):
        assert classify(error_message="connection refused to host") == "infra"

    def test_timeout_exceeded(self):
        assert classify(error_message="timeout exceeded waiting for response") == "infra"

    def test_dns_error(self):
        assert classify(error_message="getaddrinfo DNS resolution failed") == "infra"

    def test_certificate_error(self):
        assert classify(error_message="certificate has expired") == "infra"

    def test_database_connection_error(self):
        assert classify(error_message="database connection timeout") == "infra"

    def test_redis_connection_error(self):
        assert classify(error_message="redis connection refused") == "infra"

    def test_database_without_connection_keyword(self):
        """'database' alone is NOT infra — needs a pairing keyword."""
        result = classify(error_message="database query returned empty")
        assert result != "infra"


# ── Code signals ─────────────────────────────────────────────────────────

class TestCodeClassification:
    def test_type_error(self):
        assert classify(error_type="TypeError") == "code"

    def test_reference_error(self):
        assert classify(error_type="ReferenceError") == "code"

    def test_range_error(self):
        assert classify(error_type="RangeError") == "code"

    def test_syntax_error(self):
        assert classify(error_type="SyntaxError") == "code"

    def test_uri_error(self):
        assert classify(error_type="URIError") == "code"


# ── Dependency signals ───────────────────────────────────────────────────

class TestDependencyClassification:
    def test_node_modules_path(self):
        assert classify(
            error_type="TypeError",
            file_path="node_modules/express/lib/router.js",
        ) == "dependency"


# ── Unknown fallback ────────────────────────────────────────────────────

class TestUnknownClassification:
    def test_no_signals(self):
        assert classify(error_type="CustomError", error_message="something happened") == "unknown"

    def test_empty_inputs(self):
        assert classify() == "unknown"
