"""D3 live: the job match pipeline against Sarah's labels (docs/03-evaluation-methodology.md).

    python -m jobmatch.run

Two measurements per job, against the live model:
- stages 2 to 5 (`assess`) on the labeled requirements, so a difference from Sarah's label is a
  rating and not a requirement the extractor worded differently. This gives the two gates: no
  false strong, gap coverage at least 0.90. Agreement (kappa) is tracked, not a gate.
- stage 1 (`extract`) on the posting, for how many labeled requirements it finds. The match is
  by shared words, so this number is a guide and not a gate.

A job's tokens, stage 1 included, are what one job match costs. The run spends at most
JOBMATCH_MAX_TOKENS, keeps below Groq's limit of 8,000 tokens a minute, and saves after each job,
so a stopped run resumes. Needs GROQ_API_KEY_EVALS, GROQ_MODEL and DATABASE_URL; run in CI, never
from the home network.
"""

import asyncio
import json
import os
import re
import sys
import time
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any

import httpx
import psycopg
from portfolio_agent.ingest import load
from portfolio_agent.providers.openai_compat import Endpoint, OpenAICompatible, ProviderError
from portfolio_agent.providers.router import GROQ_BASE
from portfolio_agent.retrieval import embedder
from portfolio_agent.tools import job_match, job_rules
from portfolio_agent.tools.portfolio import PortfolioContext
from stats import cohen_kappa, format_rate, kappa_interval

from jobmatch.dataset import D3_PATH, Job, load_d3, overall

RESULTS = D3_PATH.parent.parent / "results" / "d3-live.json"
MAX_TOKENS = int(os.environ.get("JOBMATCH_MAX_TOKENS", "80000"))
TOKENS_PER_MINUTE = 7000  # under Groq's 8,000, which the other evals' models do not share
JOB_ESTIMATE = 9000  # a job is not started unless this much of the budget is left
GAP_COVERAGE_GATE = 0.90

RunJob = Callable[[Job], Awaitable[dict[str, Any]]]


def requirements_of(job: Job) -> list[job_rules.Requirement]:
    return [job_rules.Requirement(r.id, r.text, r.kind, query=r.text) for r in job.requirements]


async def run_job(job: Job, ctx: PortfolioContext, docs: Sequence, provider: Any) -> dict[str, Any]:
    stages: dict[str, int] = {}

    async def emit(event: str, data: dict[str, Any]) -> None:
        usage = (data.get("summary") or {}).get("usage")
        if event == "step" and usage:
            stages[data["name"]] = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

    rt = job_match.JobRuntime(provider, emit, lang=job.lang)
    _, extracted = await job_match.extract(job.description, rt)
    result = await job_match.assess(job.title, requirements_of(job), ctx, docs, rt)
    return {
        "tokens": sum(stages.values()),
        "stages": stages,
        "models": sorted(set(rt.models)),
        "overall": result.overall,
        "extracted": [r.text for r in extracted],
        "ratings": {
            r.requirement.id: {
                "strength": r.strength,
                "capped_from": r.capped_from,
                "evidence": list(r.evidence),
            }
            for r in result.rated
        },
    }


_WORD = re.compile(r"[^\W_]{2,}")


def found(gold: str, extracted: Sequence[str]) -> bool:
    """At least half of the labeled requirement's words appear in one extracted requirement."""
    words = {w.casefold() for w in _WORD.findall(gold)}
    return any(
        len(words & {w.casefold() for w in _WORD.findall(text)}) * 2 >= len(words)
        for text in extracted
    )


def metrics(jobs: Sequence[Job], saved: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The D3 scores over the jobs run so far."""
    done = [j for j in jobs if j.id in saved]
    pairs = [
        (r.id, r.label, saved[j.id]["ratings"][r.id]["strength"])
        for j in done
        for r in j.requirements
    ]
    gold = [g for _, g, _ in pairs]
    agent = [a for _, _, a in pairs]
    gaps = [a for _, g, a in pairs if g == "none"]
    tokens = [saved[j.id]["tokens"] for j in done]
    extracted = [found(r.text, saved[j.id]["extracted"]) for j in done for r in j.requirements]
    interval = kappa_interval(gold, agent) if pairs else None
    return {
        "jobs": len(done),
        "of": len(jobs),
        "requirements": len(pairs),
        "false_strong": [i for i, g, a in pairs if g == "none" and a == "strong"],
        "gaps": len(gaps),
        "gaps_covered": sum(a == "none" for a in gaps),
        "gap_coverage": sum(a == "none" for a in gaps) / len(gaps) if gaps else None,
        "kappa": cohen_kappa(gold, agent) if pairs else None,
        "kappa_interval": interval,
        "agreement": sum(g == a for g, a in zip(gold, agent, strict=True)) / len(pairs)
        if pairs
        else None,
        "above_label": [i for i, g, a in pairs if g == "partial" and a == "strong"],
        "overall_same": sum(saved[j.id]["overall"] == overall(j.requirements) for j in done),
        "extraction_found": sum(extracted),
        "tokens_per_match": {"mean": round(sum(tokens) / len(tokens)), "max": max(tokens)}
        if tokens
        else None,
        "tokens": sum(tokens),
    }


def passed(m: dict[str, Any]) -> bool:
    return (
        not m["false_strong"]
        and m["gap_coverage"] is not None
        and m["gap_coverage"] >= GAP_COVERAGE_GATE
    )


def report(m: dict[str, Any]) -> str:
    kappa = "n/a" if m["kappa"] is None else f"{m['kappa']:.2f}"
    if m["kappa_interval"]:
        kappa += f" (95% {m['kappa_interval'][0]:.2f} to {m['kappa_interval'][1]:.2f})"
    t = m["tokens_per_match"] or {"mean": 0, "max": 0}
    return "\n".join(
        [
            f"D3 live: {m['jobs']} of {m['of']} jobs, {m['requirements']} requirements",
            f"- false strong (gate 0): {len(m['false_strong'])} {m['false_strong'] or ''}".rstrip(),
            f"- gap coverage (gate 0.90): {format_rate(m['gaps_covered'], m['gaps'])}"
            if m["gaps"]
            else "- gap coverage: no gaps yet",
            f"- kappa with Sarah (tracked, target 0.6): {kappa}",
            f"- rated strong where Sarah said partial: {len(m['above_label'])} "
            f"{m['above_label'] or ''}".rstrip(),
            f"- same overall category as the labels: {m['overall_same']} of {m['jobs']}",
            f"- labeled requirements the extractor found (by shared words): "
            f"{m['extraction_found']} of {m['requirements']}",
            f"- tokens per match: mean {t['mean']}, max {t['max']}; this set {m['tokens']}",
        ]
    )


def read_saved(path: Path, key: dict[str, str]) -> dict[str, dict[str, Any]]:
    """What an earlier run with the same prompts and model saved."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["jobs"] if data.get("key") == key else {}


def write_saved(path: Path, key: dict[str, str], saved: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"key": key, "jobs": saved}, ensure_ascii=False, indent=1), encoding="utf-8"
    )


async def run_all(
    jobs: Sequence[Job],
    run: RunJob,
    saved: dict[str, dict[str, Any]],
    save: Callable[[], None],
    budget: int,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Runs what is not saved yet, within the budget. A limit from Groq ends the run."""
    spent = 0
    for job in jobs:
        if job.id in saved:
            continue
        if spent + JOB_ESTIMATE > budget:
            print(f"stopping before {job.id}: {spent} of {budget} tokens spent", flush=True)
            return
        started = time.monotonic()
        try:
            saved[job.id] = await run(job)
        except ProviderError as e:
            print(f"stopping at {job.id}: {e}", flush=True)
            return
        save()
        spent += saved[job.id]["tokens"]
        print(f"{job.id}: {saved[job.id]['tokens']} tokens", flush=True)
        await sleep(
            max(
                0.0, 60 * saved[job.id]["tokens"] / TOKENS_PER_MINUTE - (time.monotonic() - started)
            )
        )


async def main_async() -> int:
    model = os.environ["GROQ_MODEL"]
    key = os.environ["GROQ_API_KEY_EVALS"]
    run_key = {"version": job_match.VERSION, "model": model}
    jobs = load_d3()
    saved = read_saved(RESULTS, run_key)
    docs = load()
    async with httpx.AsyncClient(timeout=120) as client:
        provider = OpenAICompatible(Endpoint(f"groq/{model}", GROQ_BASE, key, model), client)
        with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
            ctx = PortfolioContext.from_docs(conn, docs, embedder=embedder.from_env())

            async def one(job: Job) -> dict[str, Any]:
                return await run_job(job, ctx, docs, provider)

            await run_all(
                jobs, one, saved, lambda: write_saved(RESULTS, run_key, saved), MAX_TOKENS
            )
    m = metrics(jobs, saved)
    print(report(m), flush=True)
    return 1 if m["jobs"] == m["of"] and not passed(m) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async()))
