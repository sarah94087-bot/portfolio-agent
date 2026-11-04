"""D3, the job-match set (docs/03-evaluation-methodology.md, section 2).

Each job is a description, rewritten from a public ad or written from scratch, split into the
requirements the ad states. Sarah labels each requirement `strong`, `partial` or `none`; the
agent's report is later scored against those labels (kappa, gap coverage, false strong).

`overall` is the score of docs/07-advanced-capabilities.md, section 2: strong 1, partial 0.5,
none 0, a `must` weighs twice a `nice`, shown as a category. It lives here until the job-match
pipeline is built in code (M5), so the set can be checked for a spread of categories now.
"""

from collections import Counter
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

D3_PATH = Path(__file__).resolve().parent.parent / "datasets" / "d3.yaml"

Strength = Literal["strong", "partial", "none"]
POINTS = {"strong": 1.0, "partial": 0.5, "none": 0.0}
WEIGHT = {"must": 2, "nice": 1}


class Requirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^\d+\.\d+$")
    text: str = Field(min_length=1)
    kind: Literal["must", "nice"]
    label: Strength
    # Records the label rests on. Empty where the knowledge base holds no evidence: a gap, or a
    # language or soft skill that Sarah knows and the records do not show.
    evidence: list[str] = []
    # Records that do not exist yet. Without them the label drops to partial (see the header).
    depends_on: list[str] = []


class Job(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^d3-\d{2}$")
    title: str = Field(min_length=1)
    lang: Literal["he", "en"]
    source: Literal["rewritten", "synthetic"]
    injection: bool = False
    description: str = Field(min_length=1, max_length=8000)
    requirements: list[Requirement] = Field(min_length=1, max_length=15)

    @model_validator(mode="after")
    def requirement_ids_follow_the_job(self):
        n = int(self.id.split("-")[1])
        bad = [r.id for r in self.requirements if int(r.id.split(".")[0]) != n]
        if bad:
            raise ValueError(f"{self.id}: requirement ids {bad} do not start with {n}.")
        dupes = [i for i, c in Counter(r.id for r in self.requirements).items() if c > 1]
        if dupes:
            raise ValueError(f"{self.id}: duplicate requirement ids {dupes}")
        return self


def score(requirements: list[Requirement]) -> float:
    total = sum(WEIGHT[r.kind] for r in requirements)
    return sum(WEIGHT[r.kind] * POINTS[r.label] for r in requirements) / total


def overall(requirements: list[Requirement]) -> Literal["high", "partial", "low"]:
    s = score(requirements)
    return "high" if s >= 0.75 else "partial" if s >= 0.45 else "low"


def load_d3(path: Path = D3_PATH) -> list[Job]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{path}: D3 is a list of jobs")
    jobs = [Job.model_validate(r) for r in raw]
    dupes = [i for i, c in Counter(j.id for j in jobs).items() if c > 1]
    if dupes:
        raise ValueError(f"{path}: duplicate ids {dupes}")
    return jobs
