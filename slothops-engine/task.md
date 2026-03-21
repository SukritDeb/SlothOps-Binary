# slothops-engine — Module Task Guide

This is the FastAPI backend that runs the entire bug remediation pipeline.  
Each module has a single responsibility. Do NOT merge modules.

---

## Pipeline at a Glance

```
Sentry Webhook
     │
     ▼
[main.py] → receive & dispatch
     │
     ▼
[sentry_parser.py] → extract error metadata
     │
     ▼
[redactor.py] → strip PII/secrets
     │
     ▼
[fingerprint.py] → hash + dedup check
     │
     ▼
[database.py] → persist issue record
     │
     ▼
[classifier.py] → code | infra | dependency | unknown
     │
   (code only)
     ▼
[code_fetcher.py] → pull files from GitHub
     │
     ▼
[llm_fixer.py] → GPT-4o fix generation
     │
     ▼
[github_automation.py] → branch + commit + Draft PR
     │
     ▼
[sse_manager.py] → broadcast status to dashboard
```

---

## Module Checklist

### `main.py` — FastAPI Entry Point
- [ ] Define FastAPI app instance
- [ ] Register `POST /webhook/sentry` route (returns 200 immediately)
- [ ] Spawn `asyncio.create_task(run_pipeline(issue))` for async processing
- [ ] Register `GET /stream` SSE endpoint
- [ ] Register `GET /issues` and `GET /issues/{id}` endpoints
- [ ] Serve `static/index.html` at `GET /`
- [ ] Register `GET /health` endpoint
- [ ] Mount SSE with `sse-starlette`

### `pipeline.py` — Main Orchestrator
- [ ] Define `run_pipeline(issue: IssueRecord) -> None`
- [ ] Call each stage in order: parse → redact → fingerprint → classify → fetch → fix → PR
- [ ] Update `status` in DB at each stage transition
- [ ] Broadcast SSE event at each stage via `sse_manager`
- [ ] Handle stage failures gracefully:  
  - LLM fails → `status = "fixing_failed"`  
  - GitHub fails → `status = "pr_creation_failed"`  
- [ ] Do NOT use catch-all exception handlers

### `config.py` — Environment Variables
- [ ] Load all env vars via `python-dotenv`
- [ ] Export typed settings: `OPENAI_API_KEY`, `GITHUB_TOKEN`, `GITHUB_REPO`, `DATABASE_PATH`, `PORT`, `LOG_LEVEL`
- [ ] Raise on missing required keys at startup

### `models.py` — Pydantic Models + DB Schema
- [ ] Define `IssueRecord` Pydantic model matching the internal data contract
- [ ] Define `LLMFixResponse` Pydantic model for GPT-4o output
- [ ] Define `FileChange` model for per-file changes
- [ ] Include all status, classification, confidence enums

### `database.py` — SQLite via aiosqlite
- [ ] Create `issues` table on startup (schema from AI_CONTEXT.md)
- [ ] Create indexes on `fingerprint` and `status`
- [ ] `create_issue(issue: IssueRecord) -> None`
- [ ] `get_issue_by_fingerprint(fingerprint: str) -> IssueRecord | None`
- [ ] `update_issue_status(id: str, status: str, **kwargs) -> None`
- [ ] `list_issues() -> list[IssueRecord]`
- [ ] `get_issue(id: str) -> IssueRecord | None`

### `fingerprint.py` — Hashing + Deduplication
- [ ] `compute_fingerprint(error_type, file_path, function_name) -> str`  
  - Uses `sha256(error_type + file_path + function_name)`
- [ ] `check_dedup(fingerprint: str, db) -> DedupeAction`  
  - Returns: `CREATE | SKIP | RETRIGGER`
- [ ] Implement cooldown: do not re-trigger same fingerprint within 10 minutes
- [ ] Handle `pr_created` → skip, `pr_merged` → retrigger, `ignored` → skip

### `classifier.py` — Error Classification
- [ ] `classify(issue: IssueRecord) -> str`  
  - Returns: `code | infra | dependency | unknown`
- [ ] Check INFRA_SIGNALS against error_type + message + stack_trace
- [ ] Check CODE_SIGNALS (TypeError, ReferenceError, RangeError, etc.)
- [ ] Check DEPENDENCY_SIGNALS (`node_modules` in file_path)
- [ ] Default to `unknown` if no signal matches

### `redactor.py` — PII + Secret Stripping
- [ ] `redact(text: str) -> str`
- [ ] Strip: email, bearer token, api_key, ip_address, jwt, uuid, phone, credit_card
- [ ] Replace each match with `[REDACTED_{PATTERN_NAME}]`
- [ ] Apply redaction BEFORE any data reaches the LLM or gets logged

### `sentry_parser.py` — Webhook Payload Parser
- [ ] `parse_sentry_webhook(payload: dict) -> IssueRecord`
- [ ] Extract: error_type, error_message, file_path, function_name, line_number, stack_trace
- [ ] Skip frames from `node_modules/`
- [ ] Use top application-level frame for file/function
- [ ] Assign new UUID for `id`
- [ ] Handle missing/malformed fields gracefully

### `code_fetcher.py` — GitHub File Fetcher
- [ ] `fetch_code_context(issue: IssueRecord) -> dict[str, str]`
- [ ] Fetch failing source file (full content) via PyGithub
- [ ] Detect and fetch associated test file (e.g., `src/` → `tests/`, `.ts` → `.test.ts`)
- [ ] Detect and fetch local imports referenced in the failing file (max 3)
- [ ] Do NOT fetch entire repo
- [ ] Handle GitHub 404 gracefully (file may not exist)

### `llm_fixer.py` — GPT-4o Fix Generator
- [ ] `generate_fix(issue: IssueRecord, code_context: dict) -> LLMFixResponse`
- [ ] Use exact system prompt from AI_CONTEXT.md
- [ ] Use exact user prompt template from AI_CONTEXT.md
- [ ] Call with `temperature=0.2`, `response_format={"type": "json_object"}`
- [ ] Parse JSON response into `LLMFixResponse`
- [ ] On JSON parse failure: retry once with follow-up message
- [ ] On second failure: raise exception → pipeline marks `fixing_failed`
- [ ] Inject recurrence context if `previous_fix_id` is set

### `github_automation.py` — PR Creator
- [ ] `create_fix_pr(issue: IssueRecord, fix: LLMFixResponse) -> str`  
  - Returns PR URL
- [ ] Create branch: `slothops/fix-{slugified-path}-{issue-id[:8]}`
- [ ] Commit each changed file (fetch SHA first before updating)
- [ ] Open DRAFT Pull Request against `main`
- [ ] PR body format per AI_CONTEXT.md (root cause, confidence, error table, warning footer)
- [ ] Add `needs-careful-review` label for medium confidence
- [ ] Never auto-merge, never force-push

### `sse_manager.py` — Dashboard Event Broadcaster
- [ ] Global SSE event queue
- [ ] `broadcast(event_type: str, payload: dict) -> None`
- [ ] Client connects at `GET /stream` receives all future events
- [ ] Emit events at each pipeline stage transition

---

## Tests Checklist (`tests/`)

- [ ] `test_classifier.py` — infra vs code vs dependency vs unknown
- [ ] `test_redactor.py` — PII patterns stripped correctly
- [ ] `test_fingerprint.py` — same inputs → same hash, dedup logic
- [ ] `test_sentry_parser.py` — correct frame extraction from fixture payload
- [ ] Save real Sentry webhook JSON to `tests/fixtures/sentry_webhook.json`

---

## Dashboard (`static/index.html`)

- [ ] Connect to `GET /stream` using `EventSource` API
- [ ] Display a live feed of issues moving through pipeline stages
- [ ] Show issue list from `GET /issues`
- [ ] Use TailwindCSS via CDN (no build step)
- [ ] Show PR link when status = `pr_created`
