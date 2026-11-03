"""Settings read from environment variables. Names are documented in .env.example."""

import os
from dataclasses import dataclass


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    agent_enabled: bool

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.environ.get("DATABASE_URL") or None,
            agent_enabled=_flag("AGENT_ENABLED", default=True),
        )
