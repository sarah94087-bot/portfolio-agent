"""D4, the conversations set (docs/03-evaluation-methodology.md, section 2).

Each conversation is 3 to 6 visitor turns. It tests what a single question cannot: a follow-up
that names nothing ("and what was hardest there?"), a language switch mid-conversation, moving
from a project to a job match, and offering contact at the right moment (US-7.1).

Per turn:
- `user` is the visitor's message, or `job` sends a D3 job to match_job.
- `lang` is the language the answer must be in: that of the turn, so a switch is tested (code).
- `gold_chunks`, as in D1: what retrieval must find in that turn, with the history behind it.
- `contact`: `offer` when the turn gives a sign of interest (a high match, an explicit request,
  a question about availability), `none` when offering would be pushy. Empty means either is
  fine. Judged.
- `tools`: tools that must be called in that turn, such as match_job or request_contact (code).
- `expect` and `must_not`, as in D2, for the judge.
"""

from collections import Counter
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

D4_PATH = Path(__file__).resolve().parent.parent / "datasets" / "d4.yaml"
TOOLS = ("search_portfolio", "get_project", "match_job", "render_card", "request_contact")


class Turn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: str | None = None
    job: str | None = Field(default=None, pattern=r"^d3-\d{2}$")
    lang: Literal["he", "en"]
    gold_chunks: list[str] = []
    contact: Literal["offer", "none"] | None = None
    tools: list[Literal[TOOLS]] = []
    expect: str = Field(min_length=1)
    must_not: list[str] = []

    @model_validator(mode="after")
    def user_or_job(self):
        if (self.user is None) == (self.job is None):
            raise ValueError("a turn has a user message or a job, not both")
        if self.job and "match_job" not in self.tools:
            raise ValueError("a job turn must call match_job")
        return self


class Conversation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^d4-\d{2}$")
    title: str = Field(min_length=1)
    tests: list[Literal["follow_up", "language_switch", "project_to_job", "contact"]] = Field(
        min_length=1)
    turns: list[Turn] = Field(min_length=3, max_length=6)


def load_d4(path: Path = D4_PATH) -> list[Conversation]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{path}: D4 is a list of conversations")
    convs = [Conversation.model_validate(r) for r in raw]
    dupes = [i for i, c in Counter(c.id for c in convs).items() if c > 1]
    if dupes:
        raise ValueError(f"{path}: duplicate ids {dupes}")
    return convs
