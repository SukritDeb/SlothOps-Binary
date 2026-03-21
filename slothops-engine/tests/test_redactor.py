"""Tests for redactor.py — PII and secret stripping."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from redactor import redact


class TestEmailRedaction:
    def test_simple_email(self):
        assert "[REDACTED_EMAIL]" in redact("Contact user@example.com for help")

    def test_email_with_plus(self):
        assert "[REDACTED_EMAIL]" in redact("send to user+tag@company.co.uk")


class TestBearerRedaction:
    def test_bearer_token(self):
        result = redact("Authorization: Bearer eyABCDEF1234567890")
        assert "eyABCDEF1234567890" not in result
        assert "[REDACTED_BEARER]" in result


class TestApiKeyRedaction:
    def test_api_key_equals(self):
        result = redact("api_key=sk_live_abcdef1234567890")
        assert "sk_live_abcdef1234567890" not in result
        assert "[REDACTED_API_KEY]" in result

    def test_token_colon(self):
        result = redact('token: "ghp_ABCDefgh1234567890abcd"')
        assert "ghp_ABCDefgh1234567890abcd" not in result

    def test_password_redaction(self):
        result = redact("password=SuperSecret12345678")
        assert "SuperSecret12345678" not in result


class TestIpRedaction:
    def test_ipv4(self):
        result = redact("Connected to 192.168.1.100 on port 5432")
        assert "192.168.1.100" not in result
        assert "[REDACTED_IP_ADDRESS]" in result


class TestJwtRedaction:
    def test_jwt_token(self):
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc123def456"
        result = redact(f"Token: {jwt}")
        assert jwt not in result
        assert "[REDACTED_JWT]" in result


class TestUuidRedaction:
    def test_uuid(self):
        result = redact("Issue id: a1b2c3d4-e5f6-7890-abcd-ef1234567890")
        assert "a1b2c3d4-e5f6-7890-abcd-ef1234567890" not in result
        assert "[REDACTED_UUID]" in result


class TestPhoneRedaction:
    def test_us_phone(self):
        result = redact("Call me at (555) 123-4567")
        assert "(555) 123-4567" not in result
        assert "[REDACTED_PHONE]" in result

    def test_phone_with_country(self):
        result = redact("Reach me at +1-555-123-4567")
        assert "[REDACTED_PHONE]" in result


class TestCreditCardRedaction:
    def test_credit_card_dashes(self):
        result = redact("Card: 4111-1111-1111-1111")
        assert "4111-1111-1111-1111" not in result
        assert "[REDACTED_CREDIT_CARD]" in result

    def test_credit_card_spaces(self):
        result = redact("Card: 4111 1111 1111 1111")
        assert "4111 1111 1111 1111" not in result


class TestNoFalsePositives:
    def test_clean_text_unchanged(self):
        text = "TypeError at line 42 in getUserProfile"
        assert redact(text) == text

    def test_empty_string(self):
        assert redact("") == ""

    def test_none_passthrough(self):
        """redact(None) should return None (no crash)."""
        assert redact(None) is None
