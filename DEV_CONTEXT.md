# SLOTHOPS — Developer Onboarding Guide
# For: Human developers joining the project
# Time to read: 15 minutes

---

## What Are We Building?

SlothOps is a bot that watches your production app for crashes,
figures out which source file caused the crash, asks an AI to
fix the bug, and opens a Draft PR on GitHub with the fix —
all before a developer even wakes up.

Think of it as:
**Sentry alert → AI reads the code → Draft PR waiting for you**

---

## Why Does This Matter?

Right now when a production bug happens:
1. Sentry fires an alert
2. A developer gets woken up or pinged
3. They open Sentry, read the stack trace
4. They find the right file in the codebase
5. They understand the bug
6. They write a fix
7. They open a PR
8. Someone reviews it
9. It gets merged and deployed

Steps 1–7 can take hours. SlothOps automates steps 1–7
and leaves step 8–9 for humans.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     PRODUCTION APP                          │
│                  (slothops-demo-app)                        │
│                                                             │
│    Express + TypeScript app with intentional bugs           │
│    Sentry SDK installed, captures exceptions                │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ Sentry webhook (HTTP POST)
                       │ (via ngrok in dev)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                   SLOTHOPS ENGINE                           │
│                  (slothops-engine)                           │
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌───────────┐ │
│  │ Webhook  │→ │ Redactor │→ │Classifier │→ │Fingerprint│ │
│  │ Parser   │  │          │  │           │  │ + Dedup   │ │
│  └──────────┘  └──────────┘  └───────────┘  └─────┬─────┘ │
│                                                     │       │
│                        ┌────────────────────────────┘       │
│                        ▼                                    │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌───────────┐ │
│  │  Code    │→ │   LLM    │→ │Confidence │→ │  GitHub   │ │
│  │ Fetcher  │  │  Fixer   │  │   Gate    │  │ PR Creator│ │
│  └──────────┘  └──────────┘  └───────────┘  └───────────┘ │
│                                                             │
│  ┌──────────┐  ┌──────────┐                                │
│  │  SQLite  │  │Dashboard │ (SSE live updates)             │
│  │   DB     │  │  UI      │                                │
│  └──────────┘  └──────────┘                                │
└─────────────────────────────────────────────────────────────┘
                       │
                       │ GitHub API
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    GITHUB                                   │
│                                                             │
│    Draft PR opened on slothops-demo-app repo                │
│    GitHub Actions runs lint + typecheck + tests             │
│    Developer reviews and merges                             │
└─────────────────────────────────────────────────────────────┘
```

---

## File-by-File Walkthrough

A step-by-step trace of what happens and which file is responsible.
Read this before opening any file — it gives you the full mental model.

```
Step 1 — main.py
  Receives POST /webhook/sentry
  Returns HTTP 200 immediately to Sentry
  Spawns asyncio.create_task(run_pipeline(issue))

Step 2 — sentry_parser.py → parse_sentry_webhook(payload: dict)
  Input:  raw Sentry webhook JSON dict
  Output: IssueRecord (partial — id, error fields, stack trace, file/function/line)
  Logic:  iterates stack frames, skips node_modules, picks top app-level frame

Step 3 — redactor.py → redact(text: str)
  Input:  any string (error message, stack trace, etc.)
  Output: same string with PII replaced by [REDACTED_*] tokens
  Called: on every text field of the IssueRecord before anything else

Step 4 — fingerprint.py → compute_fingerprint(error_type, file_path, function_name)
  Input:  three strings
  Output: sha256 hex string
  Then:   check_dedup(fingerprint, db) → CREATE | SKIP | RETRIGGER

Step 5 — database.py
  create_issue(issue)         → INSERT into SQLite
  update_issue_status(id, …)  → UPDATE status + any extra fields
  get_issue_by_fingerprint()  → SELECT for dedup
  list_issues() / get_issue() → for dashboard API

Step 6 — classifier.py → classify(issue: IssueRecord)
  Input:  IssueRecord
  Output: "code" | "infra" | "dependency" | "unknown"
  Gate:   only "code" continues to steps 7+

Step 7 — code_fetcher.py → fetch_code_context(issue)
  Input:  IssueRecord (needs file_path)
  Output: dict { "main": str, "test": str, "imports": [str] }
  Uses:   PyGithub to download files from the target GitHub repo

Step 8 — llm_fixer.py → generate_fix(issue, code_context)
  Input:  IssueRecord + dict of file contents
  Output: LLMFixResponse { root_cause, confidence, files_changed, pr_title, pr_body }
  Calls:  Gemini 2.5 Pro with temp=0.2, response_schema=json_object
  Retry:  once on JSON parse failure

Step 9 — pipeline.py (confidence gate, inside run_pipeline)
  high/medium confidence → call github_automation.create_fix_pr()
  low confidence         → store recommendation, status = "recommendation_only"

Step 10 — github_automation.py → create_fix_pr(issue, fix)
  Input:  IssueRecord + LLMFixResponse
  Output: PR URL string
  Creates: branch → commits each changed file → opens Draft PR

Step 11 — sse_manager.py → broadcast(event_type, payload)
  Called: at every status transition by pipeline.py
  Effect: connected dashboard EventSource receives real-time update

Step 12 — main.py → GET /stream
  Dashboard connects here via EventSource API
  Receives all broadcast events as text/event-stream

Step 13 — static/index.html
  Vanilla JS + TailwindCSS (CDN)
  Calls GET /issues on load, opens EventSource on /stream
  Updates issue cards in real time as SSE events arrive
```

### The One Object That Flows Everywhere: `IssueRecord`
Defined in `models.py`. Every module receives it, modifies a field or two,
and passes it along. No module invents its own data shape.

---

## Team Assignments

### Dev 1 — "The Pipeline" (Backend Orchestration)

You own:
- `main.py` — FastAPI app, routes, SSE
- `pipeline.py` — Main orchestration function
- `database.py` — SQLite setup and queries
- `models.py` — Pydantic models
- `fingerprint.py` — Hashing and dedup logic
- `classifier.py` — Code vs infra classification
- `config.py` — Env vars
- `sse_manager.py` — Dashboard event broadcasting

Your job:
- Stand up the FastAPI server
- Accept Sentry webhooks at POST /webhook/sentry
- Parse the payload (use sentry_parser from Dev 2)
- Run the classification
- Manage the SQLite database
- Orchestrate the full pipeline
- Broadcast status updates via SSE

Key decisions:
- Use `aiosqlite` for async SQLite access
- Use `asyncio.create_task()` to run pipeline
  without blocking the webhook response
- Return 200 to Sentry immediately, process async

### Dev 2 — "The Brain" (AI & Code Intelligence)

You own:
- `sentry_parser.py` — Extract useful data from Sentry payload
- `redactor.py` — Strip PII and secrets
- `code_fetcher.py` — Download files from GitHub
- `llm_fixer.py` — Construct prompts, call OpenAI, parse response

Your job:
- Parse Sentry's webhook JSON into our internal data contract
- Build the redaction function (regex-based)
- Fetch the right source files from GitHub using PyGithub
- Write the system prompt and user prompt
- Call Gemini API with Structured JSON Response Format
- Parse and validate the LLM's response
- Handle LLM failures (quota limits, bad formatting)

Key decisions:
- Use `response_schema` with Google GenAI SDK
- Temperature 0.2 for consistency
- Fallback to robust models (like 1.5-flash) if quota limits hit
- Fetch at most 5 files (main file + test + up to 3 imports)

### Dev 3 — "The Proof" (Demo App + GitHub + Dashboard)

You own:
- The entire `slothops-demo-app` repo
- `github_automation.py` in the engine
- `static/index.html` dashboard
- `.github/workflows/validate.yml` in the demo app

Your job:
- Build the Express + TypeScript demo app with 3 realistic bugs
- Set up Sentry SDK in the demo app
- Configure Sentry webhook to point to ngrok URL
- Build the GitHub PR automation (branch, commit, draft PR)
- Build the dashboard HTML with SSE connection
- Set up GitHub Actions CI in the demo app

Key decisions:
- The demo app bugs should be in UNCOVERED code paths
  (existing tests should pass on main, so when the bot
  fixes the bug, tests still pass)
- Use PyGithub for all GitHub operations
- Dashboard uses EventSource API, not WebSocket
- Keep dashboard simple: TailwindCSS via CDN, no build step

---

## Local Development Setup

### Prerequisites
```bash
# Python 3.11+
python --version

# Node.js 20+
node --version

# ngrok (for exposing local server to Sentry)
# Install from https://ngrok.com
ngrok version
```

### Engine Setup
```bash
cd slothops-engine
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt

# Copy env file and fill in values
cp .env.example .env
# Edit .env with your keys

# Run
uvicorn main:app --reload --port 8000
```

### Demo App Setup
```bash
cd slothops-demo-app
npm install

# Add your Sentry DSN to .env
echo "SENTRY_DSN=https://your-dsn@sentry.io/xxx" > .env

# Run
npm run dev
```

### Webhook URL for Sentry (3 Options)

#### Option A — ngrok (simplest for local testing)
```bash
ngrok http 8000
# Copy the https URL e.g. https://abc123.ngrok.io
# Go to Sentry → Settings → Integrations → Webhooks
# Set to: https://abc123.ngrok.io/webhook/sentry
```
> ⚠️ Free tier ngrok URL changes every restart. You must re-update Sentry each time.

#### Option B — Vercel (stable URL, recommended for demo day)
The engine is a FastAPI (ASGI) app. Vercel supports it via the `@vercel/python` runtime.

```json
// slothops-engine/vercel.json
{
  "builds": [{ "src": "main.py", "use": "@vercel/python" }],
  "routes": [{ "src": "/(.*)", "dest": "main.py" }]
}
```

```bash
# From slothops-engine/
vercel deploy --prod
# Set env vars in Vercel dashboard (same as .env)
```

Sentry webhook becomes: `https://your-project.vercel.app/webhook/sentry` — **stable, no restarts.**

> ⚠️ Vercel's filesystem is ephemeral. SQLite DB resets on each deploy.
> For the hackathon demo this is fine — just don't redeploy mid-demo.
> If you need persistence, use [Turso](https://turso.tech) (SQLite-compatible, free tier).

#### Option C — Railway or Render (easiest persistent backend)
Both support FastAPI with a stable URL + persistent disk in one click from GitHub.
- [Railway](https://railway.app) — connect repo, set env vars, done
- [Render](https://render.com) — same, free tier available



---

## Required API Keys / Accounts

| Service    | What You Need             | Where to Get It               |
|------------|---------------------------|-------------------------------|
| Gemini     | API key (GenAI access)    | aistudio.google.com           |
| GitHub     | GitHub App (App ID + PEM) | github.com/settings/apps/new  |
|            | (repo + PR permissions)   | Generates Installation tokens |
| Sentry     | Free tier account         | sentry.io                     |
|            | Project DSN               | Project Settings → Client Keys|
|            | Webhook URL configured    | Settings → Integrations       |
| ngrok      | Free account              | ngrok.com                     |

---

## Data Flow Example

Here is exactly what happens when a bug is triggered:

```
1. User hits GET /users/999/profile on demo app
2. Code crashes: user.profile is undefined
3. Sentry SDK captures the TypeError
4. Sentry sends webhook POST to our ngrok URL
5. FastAPI receives it at POST /webhook/sentry

6. sentry_parser.py extracts:
   - error_type: "TypeError"
   - error_message: "Cannot read properties of undefined
                     (reading 'displayName')"
   - file_path: "src/routes/users.ts"
   - function_name: "getUserProfile"
   - line_number: 42

7. redactor.py strips any PII from the stack trace

8. fingerprint.py computes hash("TypeError" + "src/routes/users.ts"
                                + "getUserProfile")
   - Checks SQLite: new fingerprint → create record

9. classifier.py checks: "TypeError" → classification = "code"

10. code_fetcher.py uses PyGithub to download:
    - src/routes/users.ts (main file)
    - tests/routes/users.test.ts (test file)
    - src/services/userService.ts (imported file)

11. llm_fixer.py sends prompt to Gemini with:
    - Error details
    - Redacted stack trace
    - All fetched source files
    - Strict rules about not swallowing errors

12. Gemini returns JSON:
    {
      "root_cause": "user.profile can be null for users
                     who haven't completed onboarding...",
      "confidence": "high",
      "files_changed": [{
        "path": "src/routes/users.ts",
        "fixed_content": "...code with optional chaining...",
        "explanation": "Added null checks for user.profile..."
      }],
      "pr_title": "fix: handle null user profile in getUserProfile",
      "pr_body": "..."
    }

13. Confidence is "high" → proceed to PR creation

14. github_automation.py:
    - Creates branch: slothops/fix-src-routes-users-ts-abc12345
    - Commits the fixed file
    - Opens Draft PR with full explanation

15. GitHub Actions in the demo repo automatically runs:
    - npm run lint
    - npm run typecheck
    - npm test
    → Green checkmark appears on the PR

16. Dashboard updates in real-time via SSE showing
    the issue progressing through each stage

17. Developer opens GitHub, reviews the PR, merges it
```

---

## The Demo Bugs (7 Total)

All bugs compile cleanly via `tsc` but crash at runtime when triggered.

### Bug 1: Null Reference (src/routes/users.ts)
```typescript
// user.profile can be null for new users (user "999")
const name = user.profile!.displayName;    // RUNTIME CRASH
avatar: user.profile!.avatarUrl            // RUNTIME CRASH
```
**Trigger:** `GET /users/999/profile`
**Expected fix:** Optional chaining (`user.profile?.displayName`) and/or null check with proper error response.

### Bug 2: Array on Undefined (src/services/orderService.ts)
```typescript
// order.items can be undefined if order was just created
const subtotal = order.items.reduce(
  (sum, item) => sum + (item.price * item.quantity), 0
);
```
**Trigger:** `GET /orders/ORD-999/subtotal`
**Expected fix:** Default to empty array (`(order.items ?? []).reduce(...)`) or guard clause.

### Bug 3: Unhandled Auth Error (src/middleware/auth.ts)
```typescript
// jwt.verify throws synchronously on invalid tokens — no try/catch!
const payload = jwt.verify(token, JWT_SECRET);
```
**Trigger:** `GET /orders/ORD-001` with header `Authorization: Bearer garbage`
**Expected fix:** Wrap jwt.verify in try/catch with proper 401 response.

### Bug 4: Floating Async Promise (src/routes/sync.ts)
```typescript
// async inside forEach() — promises fire and forget, errors are unhandled
productIds.forEach(async (id) => {
    const data = await fetchInventory(id);
    if (id === "p_3") throw new Error(`Sync failed for ${id}`);
});
```
**Trigger:** `GET /sync/batch`
**Expected fix:** Replace `forEach` with `Promise.all(productIds.map(async ...))` and `await` it.

### Bug 5: Cache Poisoning / Shared Object Mutation (src/routes/config.ts)
```typescript
// Mutates global singleton AppConfig — poisons ALL future requests!
if (forceDark) {
    currentConfig.theme = forceDark; // MUTATING GLOBAL STATE!
}
```
**Trigger:** `GET /config/theme?forceDark=bad_string` then `GET /config/theme`
**Expected fix:** Use a local variable instead of mutating the shared config.

### Bug 6: Null Feature Config (src/routes/users.ts)
```typescript
const userConfig: any = { features: null };
if (userConfig.features.enabled) { ... } // CRASH: null.enabled
```
**Trigger:** `GET /users/1/premium`
**Expected fix:** Optional chaining or null check on `features`.

### Bug 7: Undefined Receipt ID (src/routes/orders.ts)
```typescript
const formattedId = payload.receiptId.toUpperCase(); // CRASH if receiptId missing
```
**Trigger:** `POST /orders/receipt` with empty body `{}`
**Expected fix:** Guard for `payload.receiptId` existence before calling `.toUpperCase()`.

---

## What NOT To Build (Explicitly Out of Scope)

- Source map resolution for minified frontend code
- OpenTelemetry trace integration
- Multi-language support (we only handle TypeScript)
- Self-hosted LLM option
- Code ownership / CODEOWNERS routing
- Canary deployment verification
- Vector embeddings / semantic code search
- Slack/Discord notifications
- Multi-repo support (single repo per workspace for now)
- Custom rule configuration UI
- Historical analytics / charts

If a judge asks about any of these, say:
"That is in our roadmap. For this MVP we focused on
proving the core pipeline works end-to-end with real
Sentry data, real GitHub PRs, and validated AI fixes."

---

## Common Gotchas

1. **Sentry webhook format changes between versions.**
   Test with a real webhook payload early.
   Save a sample payload as `tests/fixtures/sentry_webhook.json`.

2. **ngrok free tier URLs change every restart.**
   You will need to update the Sentry webhook URL each time.
   Consider paying for a stable subdomain or use a
   Sentry internal integration instead.

3. **GitHub API rate limit is 5000 requests/hour.**
   For a demo this is fine. But don't run the pipeline
   in a loop during testing.

4. **Gemini API can hit Rate Limits on Free Tier**
   If you hit a `429 RESOURCE_EXHAUSTED` limit with `limit: 0`,
   adjust the model to `gemini-1.5-flash`.

5. **PyGithub's create_file / update_file needs the
   current file SHA.**
   Always fetch the file first to get its SHA before updating.

6. **SQLite does not handle concurrent writes well.**
   Use a lock or queue if running multiple pipeline
   instances simultaneously.

7. **Sentry may batch multiple events into one webhook.**
   Check if the payload contains multiple issues.

8. **The demo app's existing tests MUST pass on main.**
   The bugs should be in code paths not covered by
   current tests. Otherwise, the bot's fix might look
   like it broke something.

---

## How to Test the Full Pipeline Without Sentry

If Sentry is being flaky, you can trigger the pipeline manually:

```bash
curl -X POST http://localhost:8000/webhook/sentry \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/sentry_webhook.json
```

Keep a realistic sample payload in `tests/fixtures/`.
This is also useful for the demo if live Sentry is slow.

---

## Definition of Done (for the hackathon)

The project is demo-ready when:

- [ ] Hitting a buggy endpoint triggers Sentry
- [ ] Sentry webhook reaches our FastAPI server
- [ ] The error is classified correctly (code vs infra)
- [ ] Source file is fetched from GitHub
- [ ] LLM generates a fix with root cause explanation
- [ ] Draft PR appears on GitHub with the fix
- [ ] GitHub Actions CI runs and passes on the PR
- [ ] Dashboard shows the issue progressing through stages
- [ ] Hitting the same bug again does NOT create duplicate PR
- [ ] Infra error (DB down) is classified and skipped
- [ ] All three demo bugs produce valid fixes
- [ ] At least 3 unit tests pass for our own engine code

---

## File Naming Conventions

- Python: snake_case for files and functions
- TypeScript: camelCase for files, PascalCase for types
- Branches: slothops/fix-{slugified-path}-{short-id}
- PR titles: fix: {short description}
- Test files: test_{module_name}.py (Python)
              {module}.test.ts (TypeScript)

---

## Communication During the Hackathon

- All three devs work in the same room/call
- Integration points checked every 2 hours
- If blocked, switch to a different task and ping teammate
- Test with real Sentry payload by hour 6 AT THE LATEST
- Full end-to-end test by hour 12
- Feature freeze at hour 18
- Only polish and demo prep after hour 18

---

## Quick Reference: Key Libraries

### Python (engine)
```
fastapi==0.115.0
uvicorn==0.30.0
PyGithub==2.3.0
google-genai
pydantic==2.9.0
aiosqlite==0.20.0
python-dotenv==1.0.1
sse-starlette==2.1.0
httpx==0.27.0  (for testing)
pytest==8.3.0
pytest-asyncio==0.24.0
```

### Node.js (demo app)
```
express
@sentry/node
jsonwebtoken
typescript
ts-node
jest
@types/express
@types/jest
ts-jest
eslint
```

---

## If Everything Goes Wrong

Backup plan if a critical component fails:

| Failure              | Backup                                        |
|----------------------|-----------------------------------------------|
| Sentry webhook dead  | Use manual curl with saved JSON payload       |
| Gemini API down      | Use a pre-saved LLM response from earlier run |
| GitHub API rate limit | Use pre-created branch, show the PR manually  |
| ngrok not working    | Run everything locally, use curl              |
| Demo app won't start | Have a pre-recorded video of the full demo    |

**ALWAYS record a backup demo video before presentations.**

---

## PHASE 5: SAAS UPGRADE (IN PROGRESS)

The team has transitioned from Local Hackathon MVP to a SaaS Platform!

### ✅ What We've Built So Far:
1. **Auth + UI Dashboard:** Built an integrated Signup/Login Flow natively inside `static/index.html`. Users can boot up unique "Workspaces", and the dashboard strictly scopes issue visibility via `PyJWT` Bearer tokens.
2. **Multi-Tenant DB Architecture:** Upgraded SQLite to separate `workspaces`, `users`, and `workspace_users` tables. Sentry webhook URLs are uniquely formulated for every tenant (`/webhook/sentry/{workspace_id}`).
3. **Decoupled GitHub Repository Targeting:** The hardcoded `GITHUB_REPO` environment variable is DEPRECATED. SlothOps intercepts GitHub App Installations on `POST /webhook/github` and saves the `installation_id`. During a pipeline run, it uses `PyGithub` to dynamically query `installation.get_repos()` and infer the exact target repository automatically!

### ⏳ Tomorrow's Development Goals:
1. **Live GitHub App Installation:** The developer must configure the App Webhook on GitHub, generate the `.pem` Private Key, add it to `.env`, and click "Install" on their target repository.
2. **Sentry Redirection:** Copy the custom Workspace Webhook URL from the new SlothOps Dashboard and paste it into the Sentry project settings.
3. **The End-to-End Run:** Trigger a real bug on the frontend. Ensure the Sentry Payload routes securely to the correct Workspace, generates a short-lived GitHub App Token, fetches the dynamic repository, fixes the code, and creates the PR successfully!
4. **Postgres Migration:** Dump SQLite for a production `asyncpg` PostgreSQL database (like Neon or Supabase).

---
## END OF DEVELOPER CONTEXT
