"""Shared helpers for the M1 spikes. Spikes read keys from the local .env and use the
evals keys, so they never spend production quota (docs/10-ops-and-costs.md, section 3)."""

import json
import os
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "spikes" / "results"

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"
GROQ_BASE = "https://api.groq.com/openai/v1"

HEBREW = re.compile(r"[֐-׿]")
LATIN = re.compile(r"[A-Za-z]")


def load_env() -> None:
    """Load ROOT/.env into os.environ without overriding variables already set."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def require(*names: str) -> dict[str, str]:
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        raise SystemExit(f"missing in .env: {', '.join(missing)}")
    return {n: os.environ[n] for n in names}


def hebrew_ratio(text: str) -> float:
    he, la = len(HEBREW.findall(text)), len(LATIN.findall(text))
    return he / (he + la) if he + la else 0.0


def save(name: str, payload: object) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"{name}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
