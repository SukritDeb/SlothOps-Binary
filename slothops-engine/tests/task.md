# tests/ — Engine Test Suite

This folder contains unit tests for the SlothOps engine's core modules.

---

## Responsibilities

- Test each pipeline module in isolation (no live API calls)
- Use saved fixture payloads for Sentry webhook format
- Run with: `pytest tests/ -v`

---

## File Checklist

### `fixtures/sentry_webhook.json`
- [ ] Save a real Sentry webhook payload here (capture from ngrok logs on first run)
- [ ] This file is the team's shared test contract — do NOT commit sensitive data
- [ ] Used by `test_sentry_parser.py` AND as the curl trigger: `curl -d @tests/fixtures/sentry_webhook.json`

### `test_classifier.py`
- [ ] `test_classifies_typeerror_as_code()` — TypeError → "code"
- [ ] `test_classifies_connection_refused_as_infra()` — ECONNREFUSED → "infra"
- [ ] `test_classifies_node_modules_as_dependency()` — file_path has node_modules → "dependency"
- [ ] `test_classifies_unknown_as_unknown()` — unrecognized error → "unknown"

### `test_redactor.py`
- [ ] `test_redacts_email()` — removes email addresses
- [ ] `test_redacts_bearer_token()` — removes Bearer tokens
- [ ] `test_redacts_ip()` — removes IP addresses
- [ ] `test_redacts_jwt()` — removes JWT tokens
- [ ] `test_leaves_safe_text_unchanged()` — normal log lines not modified

### `test_fingerprint.py`
- [ ] `test_same_inputs_produce_same_hash()` — deterministic
- [ ] `test_different_inputs_produce_different_hash()` — collision avoidance
- [ ] `test_dedup_skip_when_pr_created()` — returns SKIP
- [ ] `test_dedup_retrigger_when_pr_merged()` — returns RETRIGGER

### `test_sentry_parser.py`
- [ ] `test_extracts_error_type()` — correct TypeError extracted
- [ ] `test_extracts_file_path()` — correct src/ file, skips node_modules frames
- [ ] `test_extracts_line_number()` — integer line number
- [ ] `test_handles_missing_stack_trace()` — does not crash on malformed payload

---

## Running Tests

```bash
# From slothops-engine/
source venv/bin/activate
pytest tests/ -v

# With coverage
pytest tests/ -v --cov=. --cov-report=term-missing
```
