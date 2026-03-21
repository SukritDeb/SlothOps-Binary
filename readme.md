# SlothOps 🦥

> **Production-aware automated bug remediation.** 
> SlothOps watches your applications for crashes via Sentry, intelligently fetces the relevant source code from GitHub, asks GPT-4o to engineer a fix, and opens a Draft Pull Request — all before a developer even wakes up.

```text
Sentry error alert → AI analyzes root cause → Draft PR waiting for your review
```

---

## 🌟 Key Features

*   **Zero-Touch Triaging:** Instantly categorises errors into `code`, `infrastructure`, or `dependency` issues, ignoring alerts that code changes cannot fix.
*   **Privacy First Data Handling:** Automatically redacts PII and secrets (Emails, API Keys, Tokens, JWTs, IPs, etc.) from the stack trace *before* the data ever reaches an LLM.
*   **Intelligent Context Gathering:** Scans the failing file and automatically fetches associated test files and local imports from GitHub to provide the LLM with full context.
*   **Smart Deduplication:** Calculates a SHA-256 fingerprint for every trace. Duplicates are skipped if a fix is already pending, or re-triggered if a previous fix failed in production.
*   **Automated PR Creation:** Automatically branches from `main`, stages the fixed code, and opens a Draft Pull Request enriched with a confidence rating and failure metadata.

---

## 🏗️ Architecture Stack

| Component | Technology | Purpose |
|---|---|---|
| **Engine (Bot)** | Python 3.11, FastAPI | Core pipeline orchestrator, webhook receiver, and SSE broadcaster. |
| **Database** | SQLite, `aiosqlite` | Asynchronous, lightweight persistence layer for tracing issue statuses. |
| **Logic Layer** | OpenAI (GPT-4o), PyGithub | LLM fix generation and direct AST/repository manipulation. |
| **Demo App** | Node.js, TypeScript | (Phase 3) A target application with intentional bugs to demonstrate the bot. |

---

## 🚀 How It Works (End-to-End)

1. **Detection:** A bug crashes in the target app, causing Sentry to fire a realtime webhook.
2. **Ingestion & Redaction:** The engine parses the payload, identifies the top application frame, and strips all PII from the stack trace.
3. **Classification:** The engine decides if this is a `code` bug. Infrastructure blips (like a killed database connection) are ignored.
4. **Context Fetching:** The bot downloads the failing source file, its test file, and relevant local dependencies directly from GitHub.
5. **Fix Generation:** GPT-4o acts as the engineer, providing root-cause analysis and a complete code diff.
6. **Automation:** A neat, formatted Draft PR is automatically staged and opened on GitHub for human review.

---

## 🛠️ Quick Start (Engine)

You can spin up the SlothOps engine locally.

```bash
cd slothops-engine
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # Fill in your OPENAI_API_KEY and GITHUB_TOKEN
uvicorn main:app --reload --port 8000
```

### Try it out manually
You can trigger the pipeline locally using a provided Sentry fixture payload:
```bash
curl -X POST http://localhost:8000/webhook/sentry \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/sentry_webhook.json
```

---

## 🎯 Project Roadmap & Definition of Done

Status of the implementation phases (Engine & Demo Application):

**Phase 1 & 2: The Core Engine (Completed) ✅**
- [x] Webhook receiving endpoint (via FastAPI) is functional.
- [x] Sentry payloads are parsed safely (filtering `node_modules`).
- [x] Redactor strictly removes all PII/Secrets patterns.
- [x] Classifier accurately distinguishes code vs. infrastructure errors.
- [x] Fingerprint deduplication (and 10-minute cooldown logic) functional.
- [x] Code fetcher retrieves relative files via GitHub API.
- [x] LLM writes the fix and explains the root cause.
- [x] GitHub module creates branch, commits, and opens Draft PR safely.
- [x] 100% test passing locally (64/64 automated tests).

**Phase 3: Demo Application & Dashboard (Upcoming) ⏳**
- [ ] Build front-end dashboard UI (`static/index.html`) using SSE live statuses.
- [ ] Develop `slothops-demo-app` (Express/TypeScript) with 3 intentional bugs.
- [ ] Integrate Sentry SDK into Demo App.
- [ ] Connect the live Sentry integration to the Engine webhook.
- [ ] GitHub Actions CI passes on auto-generated PRs.
- [ ] All 3 demo bugs are perfectly fixed by the auto-generated PRs.
