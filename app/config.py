"""Central, secret-safe application configuration."""

import os
from dataclasses import dataclass

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
