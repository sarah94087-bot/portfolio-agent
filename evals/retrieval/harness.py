"""Retrieval eval harness: scores one retriever configuration on D1.

Implements docs/04-retrieval-design.md, section 4: per configuration, Recall@3/5/10, MRR,
nDCG@5 and latency p50/p95, overall and separately for Hebrew, English and cross_lingual.
Only questions that expect an answer have gold chunks, so only they are scored here; refusals
are measured on the answers (docs/03-evaluation-methodology.md, section 3).
Per-question scores stay in the result, so `compare` can pair two runs question by question.
"""

import json
import subprocess
import time
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
from statistics import fmean
from typing import Literal

import yaml
from portfolio_agent.ingest import Chunk
from pydantic import BaseModel, ConfigDict, Field, model_validator

from retrieval.metrics import first_hits, ndcg_at, recall_at, reciprocal_rank
from stats import Difference, bootstrap_mean, paired_bootstrap

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"

METRICS = ("recall@3", "recall@5", "recall@10", "mrr", "ndcg@5")
# Each group reads a result row, so a saved run can be regrouped without D1.
GROUPS: dict[str, Callable[[dict], bool]] = {
    "all": lambda r: True,
    "he": lambda r: r["lang"] == "he",
    "en": lambda r: r["lang"] == "en",
    "cross_lingual": lambda r: r["category"] == "cross_lingual",
}

# A retriever takes the query and how many chunks to return, best first.
Retriever = Callable[[str, int], Sequence[Chunk]]


class D1Item(BaseModel):
    """One D1 question, as in docs/03-evaluation-methodology.md, section 2."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^d1-\d{3}$")
    question: str = Field(min_length=1)
    lang: Literal["he", "en"]
    category: Literal[
        "single_hop", "multi_hop", "comparative", "skill_level", "overview_limit",
        "unanswerable", "off_topic", "cross_lingual",
    ]
    expected_behavior: Literal["answer", "refuse_no_info", "redirect_off_topic"]
    gold_chunks: list[str] = []
    answer_points: list[str] = []
    must_not: list[str] = []
    split: Literal["dev", "test"]

    @model_validator(mode="after")
    def gold_only_when_answering(self):
        if self.expected_behavior == "answer" and not self.gold_chunks:
            raise ValueError("a question that expects an answer needs gold_chunks")
        if self.expected_behavior != "answer" and self.gold_chunks:
            raise ValueError(f"a {self.expected_behavior} question has no gold_chunks")
        return self


def load_d1(path: Path) -> list[D1Item]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{path}: D1 is a list of questions")
    items = [D1Item.model_validate(r) for r in raw]
    dupes = [i for i, n in Counter(item.id for item in items).items() if n > 1]
    if dupes:
        raise ValueError(f"{path}: duplicate ids {dupes}")
    return items


def check_gold(items: Sequence[D1Item], c1_ids: set[str]) -> list[str]:
    """Gold chunks that are not C1 ids of the knowledge base: renamed or missing sections."""
    return [
        f"{item.id}: gold chunk '{g}' is not in the knowledge base"
        for item in items for g in item.gold_chunks if g not in c1_ids
    ]


def score(item: D1Item, chunks: Sequence[Chunk]) -> dict[str, float]:
    ranked = [[f"{c.record_id}#{s}" for s in c.sections] for c in chunks]
    gold = set(item.gold_chunks)
    hits = first_hits(ranked, gold)
    return {
        "recall@3": recall_at(hits, len(gold), 3),
        "recall@5": recall_at(hits, len(gold), 5),
        "recall@10": recall_at(hits, len(gold), 10),
        "mrr": reciprocal_rank(hits),
        "ndcg@5": ndcg_at(hits, len(gold), 5),
    }


def percentile(values: Sequence[float], q: float) -> float:
    s = sorted(values)
    pos = (len(s) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def run(
    items: Sequence[D1Item],
    retrieve: Retriever,
    split: Literal["dev", "test"] = "dev",
    queries: dict[str, str] | None = None,
    k: int = 10,
) -> dict:
    """Runs every scored question of one split. `queries` holds the saved Q1 rewrites by id."""
    in_split = [i for i in items if i.split == split]
    scored = [i for i in in_split if i.expected_behavior == "answer"]
    if not scored:
        raise ValueError(f"no questions to score in split '{split}'")
    if queries is not None:
        missing = [i.id for i in scored if i.id not in queries]
        if missing:
            raise ValueError(f"no saved query for {missing}")
    rows, latencies = [], []
    for item in scored:
        query = queries[item.id] if queries is not None else item.question
        start = time.perf_counter()
        chunks = list(retrieve(query, k))[:k]
        latencies.append((time.perf_counter() - start) * 1000)
        rows.append({
            "id": item.id, "lang": item.lang, "category": item.category, "query": query,
            "retrieved": [c.id for c in chunks], **score(item, chunks),
        })
    groups = {}
    for name, keep in GROUPS.items():
        members = [r for r in rows if keep(r)]
        if members:
            groups[name] = {m: summarize([r[m] for r in members]) for m in METRICS}
    return {
        "split": split,
        "n": len(rows),
        "skipped": dict(Counter(
            i.expected_behavior for i in in_split if i.expected_behavior != "answer"
        )),
        "groups": groups,
        "latency_ms": {"p50": percentile(latencies, 0.5), "p95": percentile(latencies, 0.95)},
        "items": rows,
    }


def summarize(values: Sequence[float]) -> dict:
    low, high = bootstrap_mean(values)
    return {"mean": fmean(values), "low": low, "high": high, "n": len(values)}


def compare(a: dict, b: dict, metric: str = "recall@5", group: str = "all") -> Difference:
    """b minus a, paired by question (docs/03-evaluation-methodology.md, section 5)."""
    keep = GROUPS[group]
    sa, sb = ({r["id"]: r[metric] for r in run["items"] if keep(r)} for run in (a, b))
    if sa.keys() != sb.keys():
        raise ValueError("the two runs did not score the same questions")
    ids = sorted(sa)
    return paired_bootstrap([sa[i] for i in ids], [sb[i] for i in ids])


def write_results(
    result: dict, config: str, results_dir: Path = RESULTS_DIR, commit: str | None = None
) -> Path:
    """evals/results/<date>-<commit>-<config>.json, for the report and the quality page."""
    if commit is None:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    today = date.today().isoformat()
    path = results_dir / f"{today}-{commit}-{config}.json"
    results_dir.mkdir(parents=True, exist_ok=True)
    payload = {"config": config, "commit": commit, "date": today, **result}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
