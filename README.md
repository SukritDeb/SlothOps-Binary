<p align="center">
  <h1 align="center">SlothOps</h1>
  <p align="center"><strong>Autonomous Bug Remediation & Production Self-Healing for GitHub</strong></p>
  <p align="center">
    <em>From crash to fix — zero human intervention.</em>
  </p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Gemini_2.5_Pro-4285F4?logo=google&logoColor=white" alt="Gemini">
  <img src="https://img.shields.io/badge/GitHub_App-181717?logo=github&logoColor=white" alt="GitHub">
  <img src="https://img.shields.io/badge/Sentry-362D59?logo=sentry&logoColor=white" alt="Sentry">
</p>

---

## What is SlothOps?

SlothOps is a **closed-loop, production-aware** pipeline that converts live application crashes into reviewed code fixes — automatically. It listens for real-time error events via Sentry, fetches the relevant source from GitHub, generates validated fixes using an LLM, runs a full QA suite, and opens a governed Pull Request — all before a developer even looks at the alert.

If a broken commit makes it to production and breaks the deployment, SlothOps catches the failure, **automatically rolls back `main`**, and immediately attempts to self-heal the broken code on a side branch.

---

## How SlothOps Works

SlothOps operates through three interconnected pipelines that cover the full lifecycle of a production bug.

### Pipeline 1 — Error Remediation

Triggered when a **Sentry webhook** fires on a new or recurring production exception.

```
Sentry Alert
  │
  ▼
┌─────────────────────────────────────┐
│  1. INGEST & REDACT                 │
│     Parse payload, strip all PII,   │
│     tokens, secrets, emails, IPs    │
│     before anything reaches the LLM │
├─────────────────────────────────────┤
│  2. FINGERPRINT & DEDUPLICATE       │
│     SHA-256 hash of error signature │
│     Skip if fix is already pending  │
│     Re-trigger if prior fix failed  │
├─────────────────────────────────────┤
│  3. CLASSIFY                        │
│     code │ infra │ dependency        │
│     Only "code" bugs proceed        │
├─────────────────────────────────────┤
│  4. FETCH CONTEXT                   │
│     Source file + test file + local  │
│     imports from GitHub via API     │
├─────────────────────────────────────┤
│  5. GENERATE FIX (LLM)             │
│     Root-cause analysis + code diff │
│     via Gemini 2.5 Pro              │
├─────────────────────────────────────┤
│  6. OPEN DRAFT PR                   │
│     Branch from main, commit fix,   │
│     open PR with confidence rating  │
└─────────────────────────────────────┘
  │
  ▼
Developer reviews & merges
```

### Pipeline 2 — Pre-Merge QA Gate

Triggered on every **Pull Request** (opened / synchronized) via GitHub webhook.

```
PR Opened / Updated
  │
  ▼
┌─────────────────────────────────────┐
│  1. STYLE REVIEW                    │
│     AI reviews code against team's  │
│     developer.json preferences      │
├─────────────────────────────────────┤
│  2. ARCHITECTURE REVIEW             │
│     LLM evaluates design patterns,  │
│     logic, and potential regressions │
├─────────────────────────────────────┤
│  3. QA SANDBOX                      │
│     Clone repo → detect stack →     │
│     install deps → run agents:      │
│                                     │
│     ┌───────────────────────────┐   │
│     │ • Static Analysis (lint)  │   │
│     │ • Functionality Tests     │   │
│     │ • VAPT Security Scan     │   │
│     │ • Regression Tests       │   │
│     │ • Performance Baseline   │   │
│     │ • Stress Testing         │   │
│     └───────────────────────────┘   │
├─────────────────────────────────────┤
│  4. COMMIT STATUS                   │
│     Sets GitHub Commit Status:      │
│     ✅ success  or  ❌ failure       │
│     Blocks merge if QA fails        │
└─────────────────────────────────────┘
  │
  ▼
QA Report posted as PR comment
```

### Pipeline 3 — Production Auto-Rollback & Self-Healing

Triggered when a **`deployment_status: failure`** webhook fires on `main` (e.g. from Vercel).

```
Vercel Build Fails on main
  │
  ▼
┌─────────────────────────────────────┐
│  1. DETECT                          │
│     deployment_status webhook       │
│     with state = "failure"          │
├─────────────────────────────────────┤
│  2. ROLLBACK                        │
│     Clone repo in sandbox           │
│     Create backup branch            │
│     git revert bad commit on main   │
│     Push → production restored ✅   │
│                                     │
│  ⛔ Loop Prevention:                │
│  Aborts if commit message starts    │
│  with "Revert" (prevents infinite   │
│  revert chains)                     │
├─────────────────────────────────────┤
│  3. AUTO-RESOLVE                    │
│     Fetch build logs + broken code  │
│     LLM generates fix               │
│     Commit fix to backup branch     │
│     Open Auto-Fix PR → main         │
├─────────────────────────────────────┤
│  4. RE-CYCLE (up to 3×)            │
│     If the Auto-Fix PR also fails   │
│     deployment, SlothOps re-enters  │
│     step 3 with updated build logs  │
│     Max 3 attempts before abandon   │
└─────────────────────────────────────┘
  │
  ▼
Auto-Fix PR ready for review
```

---

## Tech Stack

| Layer | Technology | Role |
|---|---|---|
| **Engine** | Python 3.11 · FastAPI · Uvicorn | Webhook receiver, pipeline orchestrator, SSE broadcaster |
| **LLM** | Google Gemini 2.5 Pro / Flash | Code fix generation, QA orchestration, style & architecture review |
| **Database** | SQLite · aiosqlite | Async persistence for issues, QA reports, rollbacks, resolutions |
| **Source Control** | PyGithub · GitHub App | Repository access, PR creation, commit status checks |
| **Monitoring** | Sentry SDK | Error detection webhooks for the target application |
| **Frontend** | Vanilla HTML/CSS/JS · TailwindCSS · SSE | Real-time command center dashboard |
| **Demo App** | Node.js · TypeScript · Express | Target application with intentional bugs for demonstration |

---

## Quick Start

```bash
# 1. Clone and set up the engine
cd slothops-engine
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Fill in: GEMINI_API_KEY, GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY, SMTP_*

# 3. Run
uvicorn main:app --reload --port 8000
```

### Test locally with a Sentry fixture

```bash
curl -X POST http://localhost:8000/webhook/sentry \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/sentry_webhook.json
```

---

## Project Structure

```
binary/
├── slothops-engine/           # Core Python engine
│   ├── main.py                # FastAPI app, webhook handlers, SSE
│   ├── pipeline.py            # Error remediation orchestrator
│   ├── rollback.py            # Production rollback logic
│   ├── resolution.py          # Auto-fix resolution after rollback
│   ├── qa_pipeline.py         # QA sandbox orchestrator
│   ├── qa_agents/             # Modular QA agents
│   │   ├── static_analysis.py
│   │   ├── functionality.py
│   │   ├── vapt.py
│   │   ├── regression.py
│   │   ├── performance.py
│   │   └── stress_test.py
│   ├── llm_fixer.py           # LLM prompt engineering & fix parsing
│   ├── github_automation.py   # PR creation, commit status, reviews
│   ├── database.py            # Async SQLite CRUD
│   ├── models.py              # Pydantic schemas
│   ├── static/                # Dashboard frontend
│   │   ├── index.html
│   │   └── style.css
│   └── tests/                 # Engine unit tests
│
└── slothops-demo-app/         # Demo Express/TS app with seeded bugs
    ├── src/
    └── tests/
```

---

## Dashboard

The SlothOps Command Center provides a real-time dual-pane view:

- **Issues Panel** — Live-updating cards showing each issue's journey through the remediation pipeline (Ingested → Redacted → Classified → LLM Fixing → PR Created)
- **Engine Terminal** — Streaming server logs via SSE
- **QA Pipeline Tab** — Per-PR QA reports with drill-down into each agent's results
- **Rollback Cards** — Production rollback events with nested auto-resolution attempt history

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| **PII redaction before LLM** | No sensitive data ever leaves the server boundary |
| **SHA-256 fingerprinting** | Prevents duplicate PRs; re-triggers only on regression |
| **Git revert (not force-push)** | Clean, auditable rollback history |
| **Revert-loop prevention** | Aborts rollback if the commit is itself a "Revert" |
| **Max 3 resolution attempts** | Prevents infinite LLM fix-fail cycles |
| **aiosqlite with 10s timeout** | Handles concurrent webhook bursts without DB lock crashes |
| **GitHub App (not PAT)** | Scoped permissions, automatic installation linking |

---

## Environment Variables

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | Google Gemini API key for LLM operations |
| `GITHUB_APP_ID` | GitHub App ID for repository access |
| `GITHUB_APP_PRIVATE_KEY` | GitHub App private key (PEM format) |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` | Email notification delivery |
| `QA_EMAIL_RECIPIENT` | Recipient for QA and rollback alerts |
| `JWT_SECRET` | Dashboard authentication signing key |
| `SENTRY_DSN` | Sentry DSN for the demo application |

---

<p align="center">
  <sub>Built for the hackathon. Designed to ship.</sub>
</p>
