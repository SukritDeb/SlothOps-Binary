"""
SlothOps Engine — Configuration
Loads environment variables and exposes typed settings.
Raises RuntimeError on missing required keys at startup.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    """Return env var value or raise if missing."""
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return value


# ── Required keys ────────────────────────────────────────────────────────
GEMINI_API_KEY = _require("GEMINI_API_KEY")
GITHUB_TOKEN: str = _require("GITHUB_TOKEN")
GITHUB_REPO: str = _require("GITHUB_REPO")

# --- Optional (sensible defaults) ---
SENTRY_WEBHOOK_SECRET: str | None = os.getenv("SENTRY_WEBHOOK_SECRET")
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "./slothops.db")
PORT: int = int(os.getenv("PORT", "8000"))
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
