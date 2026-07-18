"""Central, secret-safe application configuration."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Uvicorn does not automatically read .env. Resolve it from the project root
# so `uvicorn app.api:app` works regardless of the caller's current directory.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# Fixed by the assignment. Google shut this model down on 2026-06-01;
# see README.md before attempting a live API call.
GEMINI_MODEL = "gemini-2.5-flash"


@dataclass(frozen=True)
class Settings:
    """Settings read from environment variables at process startup."""

    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    database_path: str = os.getenv("DATABASE_PATH", "data/monitoring.db")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()
