# SlothOps Engine — Knowledge Transfer (KT)

A quick reference for every file in `slothops-engine/`.
Read this to understand **what each file does** and **how they connect**.

---

## Project Setup Files

### `requirements.txt`
All Python dependencies pinned to specific versions. Install with:
```bash
pip install -r requirements.txt
```

### `.env.example`
Template for environment variables. Copy to `.env` and fill in your real keys before running the server. Three are **required** (`OPENAI_API_KEY`, `GITHUB_TOKEN`, `GITHUB_REPO`); the rest have sensible defaults.

### `config.py`
Loads `.env` via `python-dotenv` and exports typed constants. If a required key is missing, it raises a `RuntimeError` at import time — you'll know immediately rather than hitting a `None` somewhere deep in the pipeline.

---

## Data Layer

### `models.py`
The **single source of truth** for data shapes. Contains:
- **`IssueRecord`** — the central Pydantic model. Every pipeline module reads and writes this object. Fields map 1:1 to the SQLite `issues` table.
- **`LLMFixResponse`** / **`FileChange`** — models for parsing the GPT-4o JSON response.
- **Enums** — `Classification` (code/infra/dependency/unknown), `Confidence` (high/medium/low), `IssueStatus` (received → pr_created → pr_merged → ...), `DedupeAction` (create/skip/retrigger).

### `database.py`
Async SQLite wrapper using `aiosqlite`. Provides:
- `init_db()` — creates the `issues` table and indexes (safe to call repeatedly).
- `create_issue()` — inserts a new record.
- `get_issue()` / `get_issue_by_fingerprint()` — lookups.
- `update_issue_status()` — partial update (any columns via kwargs).
- `increment_occurrence()` — bumps the count for duplicate events.
- `list_issues()` — returns all issues (newest first).

Every function takes a `db_path` parameter so tests can point to a temp database.

---

## Pure Logic Modules (no external APIs)

### `redactor.py`
Regex-based PII stripper. Scans text for 8 patterns (email, bearer token, API key, IP, JWT, UUID, phone, credit card) and replaces them with `[REDACTED_EMAIL]`, `[REDACTED_JWT]`, etc.

**Important:** Patterns are applied in priority order — JWT is checked before UUID because JWT strings contain segments that look like UUIDs.

### `classifier.py`
Heuristic error classifier. Examines `error_type`, `error_message`, `stack_trace`, and `file_path` against three signal lists:
1. **Infra signals** (ECONNREFUSED, ETIMEDOUT, 502/503/504, OOMKilled, etc.) — some like "database" only trigger when paired with connection/timeout keywords.
2. **Code signals** — error_type is one of TypeError, ReferenceError, RangeError, SyntaxError, URIError.
3. **Dependency signals** — `node_modules` appears in the file path.
4. **Default** — "unknown" (no fix generated).

### `fingerprint.py`
Two functions:
- **`compute_fingerprint()`** — SHA-256 hash of `error_type + file_path + function_name`. Same bug = same hash.
- **`check_dedup()`** — Given an existing issue's status, decides:  CREATE (new), SKIP (already handled), or RETRIGGER (merged fix didn't work). Enforces a 10-minute cooldown to prevent spam.

### `sentry_parser.py`
Parses Sentry's webhook JSON into an `IssueRecord`. Key logic:
- Walks `event.exception.values[*].stacktrace.frames`
- Filters out `node_modules` frames
- Picks the **last** application frame (top of the call stack)
- Extracts `error_type`, `error_message`, `file_path`, `function_name`, `line_number`
- Builds a readable stack trace string
- Assigns a new UUID as the issue `id`

---

## Tests

### `tests/fixtures/sentry_webhook.json`
A realistic Sentry webhook payload matching the Bug 1 scenario (null user profile crash). Contains both `node_modules` and application frames.

### `tests/test_classifier.py`
Tests all classification paths: infra signals (14 cases), code signals (5 error types), dependency (node_modules path), and unknown fallback.

### `tests/test_redactor.py`
Tests each of the 8 redaction patterns plus edge cases (clean text, empty string, `None` input).

### `tests/test_fingerprint.py`
Tests hash determinism, uniqueness, SHA-256 format, `None` handling, and the full dedup decision matrix including the 10-minute cooldown.

### `tests/test_sentry_parser.py`
Tests fixture parsing (all fields extracted correctly), `node_modules` frame filtering, and edge cases (empty payload, missing exception key).

---

## External API Modules (Phase 2)

### `code_fetcher.py`
Downloads source files from the target GitHub repo using PyGithub. For a crashing file like `src/routes/users.ts`, it fetches:
1. The main file itself
2. The associated test file (convention: `src/` → `tests/`, `.ts` → `.test.ts`)
3. Up to 3 local imports parsed from the source (e.g. `import ... from './services/userService'`)

Handles GitHub 404s gracefully. Max 5 files total.

### `llm_fixer.py`
Constructs the prompt and calls GPT-4o. Contains:
- The **exact** system prompt from AI_CONTEXT.md (12 strict rules)
- A user prompt builder that slots in error details, redacted stack trace, and all fetched source files
- JSON response parsing into `LLMFixResponse`
- One-retry logic: if GPT-4o returns bad JSON, it sends a follow-up message. If it fails again, the pipeline marks the issue `fixing_failed`.

### `github_automation.py`
Creates branches, commits fixes, and opens Draft PRs. Steps:
1. Create branch `slothops/fix-{slugified-path}-{short-id}` from `main`
2. For each changed file: fetch current SHA → update file on branch
3. Open a **Draft** PR with rich Markdown body (root cause, confidence badge, error table, per-file explanations, auto-generated warning footer)
4. Add `needs-careful-review` label if confidence is medium

### `sse_manager.py`
Manages Server-Sent Events for the dashboard. Uses a fan-out pattern: one `asyncio.Queue` per connected browser client. `broadcast()` pushes events to all clients. `subscribe()` yields messages for a single connection.

---

## Server & Orchestration (Phase 2)

### `pipeline.py`
The conductor. Runs the full pipeline for a single issue in order:
1. Redact → 2. Fingerprint + Dedup → 3. Classify → 4. Fetch code → 5. LLM fix → 6. Confidence gate → 7. Create PR

Updates the database status and broadcasts SSE events at every stage. Uses **granular error handling**: LLM fails → `fixing_failed`, GitHub fails → `pr_creation_failed` (never catch-all).

### `main.py`
The FastAPI web server. Endpoints:
- `POST /webhook/sentry` — receives webhook, returns 200 immediately, spawns `asyncio.create_task(run_pipeline(...))` in background
- `GET /issues` — list all tracked issues
- `GET /issues/{id}` — single issue detail
- `GET /stream` — SSE endpoint for dashboard
- `GET /health` — health check
- `GET /` — serves `static/index.html`

Runs `init_db()` on startup via FastAPI's lifespan context.

---

## How Everything Connects

```
 HTTP POST from Sentry
       │
       ▼
   main.py          →  receives webhook, spawns async task
       │
       ▼
  sentry_parser.py  →  IssueRecord (models.py)
       │
       ▼
   redactor.py      →  strips PII from stack_trace
       │
       ▼
  fingerprint.py    →  computes hash, checks dedup
       │
       ▼
  classifier.py     →  code | infra | dependency | unknown
       │
     (code only)
       ▼
  code_fetcher.py   →  downloads source files from GitHub
       │
       ▼
   llm_fixer.py     →  GPT-4o generates fix JSON
       │
       ▼
  github_automation  →  creates branch + commits + Draft PR
       │
       ▼
   database.py      →  persists state at every step
   sse_manager.py   →  broadcasts live updates to dashboard
```

---

## Running Tests

```bash
cd slothops-engine
source venv/bin/activate
python -m pytest tests/ -v
```

All 4 test files should pass with **zero API keys required**.

## Starting the Server

```bash
cd slothops-engine
source venv/bin/activate
cp .env.example .env   # fill in real keys
uvicorn main:app --reload --port 8000
```
