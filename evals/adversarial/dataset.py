"""D2, the adversarial set (docs/03-evaluation-methodology.md, sections 2 and 3).

Each case is an attack in one or more visitor turns, or a job description that carries one
(indirect injection, shared with D3). Success is checked in code first and by the judge second:
- `checks` are the code checks (docs/03, section 3, "בטיחות"): the canary is not in the output,
  no phone number or email appears, no forbidden tool is called, citations stay valid, and the
  answer stays under the output limit.
- `expect` is what the judge reads: the behavior that counts as success, in one sentence.
- `must_not` are claims that must not appear, as in D1.

`critical` marks the 15 cases that run in T1 on every PR (docs/03, section 7).
"""

from collections import Counter
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

D2_PATH = Path(__file__).resolve().parent.parent / "datasets" / "d2.yaml"

# docs/03, section 2, "D2: קטגוריות מתקפה"
Category = Literal[
    "prompt_extraction", "direct_injection", "indirect_injection", "impersonation",
    "induced_lie", "inflation", "private_info", "salary_personal", "quota_abuse",
]
Check = Literal["canary", "private_info", "forbidden_tools", "citations", "max_output"]
# docs/06-agent-design.md, section 3
TOOLS = ("search_portfolio", "get_project", "match_job", "render_card", "request_contact")
CRITICAL = 15


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^d2-\d{3}$")
    category: Category
    lang: Literal["he", "en"]
    critical: bool = False
    turns: list[str] = []
    # Indirect injection: the D3 job, or a job text of its own, sent to match_job.
    job: str | None = Field(default=None, pattern=r"^d3-\d{2}$")
    job_text: str | None = None
    checks: list[Check] = Field(min_length=1)
    forbidden_tools: list[Literal[TOOLS]] = []
    expect: str = Field(min_length=1)
    must_not: list[str] = []

    @model_validator(mode="after")
    def has_an_attack(self):
        if not self.turns and not (self.job or self.job_text):
            raise ValueError(f"{self.id}: a case needs turns or a job")
        if self.job and self.job_text:
            raise ValueError(f"{self.id}: give job or job_text, not both")
        if bool(self.forbidden_tools) != ("forbidden_tools" in self.checks):
            raise ValueError(f"{self.id}: forbidden_tools and its check go together")
        if (self.job or self.job_text) and self.category != "indirect_injection":
            raise ValueError(f"{self.id}: a job is only an indirect injection")
        return self


def load_d2(path: Path = D2_PATH) -> list[Case]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{path}: D2 is a list of cases")
    cases = [Case.model_validate(r) for r in raw]
    dupes = [i for i, c in Counter(c.id for c in cases).items() if c > 1]
    if dupes:
        raise ValueError(f"{path}: duplicate ids {dupes}")
    return cases
