"""The system prompt (docs/06-agent-design.md, section 2).

The prompt is a versioned file, and its version is recorded with every answer. The canary is
not in the file, because the repo is public: it comes from CANARY_TOKEN at runtime, or a random
one per process when that is not set (local runs), and the output guard watches for it.
"""

import os
import secrets
from functools import cache
from pathlib import Path

PROMPTS = Path(__file__).parent / "prompts"
VERSION = "system.v1"
PLACEHOLDER = "{canary}"


@cache
def canary() -> str:
    return os.environ.get("CANARY_TOKEN") or secrets.token_hex(16)


def system_prompt(version: str = VERSION, token: str | None = None) -> str:
    text = (PROMPTS / f"{version}.md").read_text(encoding="utf-8")
    if text.count(PLACEHOLDER) != 1:
        raise ValueError(f"{version}.md must hold {PLACEHOLDER} exactly once")
    return text.replace(PLACEHOLDER, token or canary())
