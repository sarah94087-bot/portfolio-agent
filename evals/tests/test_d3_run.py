"""The D3 live runner's arithmetic, budget and resume, with no model."""

import asyncio

from jobmatch.dataset import Job
from jobmatch.run import (
    JOB_ESTIMATE,
    found,
    metrics,
    passed,
    read_saved,
    requirements_of,
    run_all,
    write_saved,
)
from portfolio_agent.providers.openai_compat import ProviderError


def job(n, labels):
    return Job(
        id=f"d3-{n:02d}",
        title="Role",
        lang="en",
        source="synthetic",
        description="Text.",
        requirements=[
            {"id": f"{n}.{i + 1}", "text": f"Skill {i + 1} work", "kind": "must", "label": x}
            for i, x in enumerate(labels)
        ],
    )


def row(j, strengths, tokens=1000, extracted=("Skill 1 work",), level="partial"):
    return {
        "tokens": tokens,
        "overall": level,
        "extracted": list(extracted),
        "ratings": {r.id: {"strength": s} for r, s in zip(j.requirements, strengths, strict=True)},
    }


def test_a_gap_rated_strong_is_a_false_strong_and_fails_the_gate():
    j = job(1, ["none", "none", "strong"])
    m = metrics([j], {j.id: row(j, ["strong", "none", "strong"])})
    assert m["false_strong"] == ["1.1"]
    assert m["gap_coverage"] == 0.5
    assert not passed(m)


def test_partial_on_a_gap_is_not_false_strong_but_misses_coverage():
    j = job(1, ["none"] * 10)
    m = metrics([j], {j.id: row(j, ["partial"] + ["none"] * 9)})
    assert m["false_strong"] == []
    assert m["gap_coverage"] == 0.9
    assert passed(m)


def test_strong_over_a_partial_label_is_reported_apart():
    j = job(1, ["partial", "none"])
    m = metrics([j], {j.id: row(j, ["strong", "none"])})
    assert m["above_label"] == ["1.1"] and m["false_strong"] == []


def test_only_jobs_that_ran_count():
    a, b = job(1, ["none"]), job(2, ["strong"])
    m = metrics([a, b], {a.id: row(a, ["none"], tokens=700)})
    assert (m["jobs"], m["of"], m["requirements"]) == (1, 2, 1)
    assert m["tokens_per_match"] == {"mean": 700, "max": 700}


def test_no_jobs_yet_is_not_a_pass():
    assert not passed(metrics([job(1, ["none"])], {}))


def test_found_needs_half_of_the_words():
    assert found("Python backend services", ["Backend services in production"])
    assert not found("Python backend services", ["Kubernetes services"])
    assert found("ניסיון ב-Python", ["Python בפרודקשן"])


def test_requirements_use_the_label_text_as_the_query():
    r = requirements_of(job(1, ["none"]))[0]
    assert (r.id, r.text, r.query, r.kind) == ("1.1", "Skill 1 work", "Skill 1 work", "must")


def drive(jobs, run, saved, budget=10**6):
    saves = []

    async def no_sleep(_):
        return None

    asyncio.run(run_all(jobs, run, saved, lambda: saves.append(len(saved)), budget, no_sleep))
    return saves


def test_a_saved_job_is_not_run_again():
    a, b = job(1, ["none"]), job(2, ["none"])
    calls = []

    async def run(j):
        calls.append(j.id)
        return row(j, ["none"])

    saves = drive([a, b], run, {a.id: row(a, ["none"])})
    assert calls == [b.id] and saves == [2]


def test_the_budget_stops_before_a_job_starts():
    jobs = [job(n, ["none"]) for n in range(1, 4)]
    saved = {}

    async def run(j):
        return row(j, ["none"], tokens=JOB_ESTIMATE)

    drive(jobs, run, saved, budget=2 * JOB_ESTIMATE)
    assert list(saved) == [jobs[0].id, jobs[1].id]


def test_a_limit_from_groq_keeps_what_was_saved():
    a, b = job(1, ["none"]), job(2, ["none"])
    saved = {}

    async def run(j):
        if j is b:
            raise ProviderError("rate_day", "over")
        return row(j, ["none"])

    drive([a, b], run, saved)
    assert list(saved) == [a.id]


def test_saved_results_of_other_prompts_are_ignored(tmp_path):
    path = tmp_path / "out" / "d3.json"
    key = {"version": "v1", "model": "m"}
    write_saved(path, key, {"d3-01": {"tokens": 5}})
    assert read_saved(path, key) == {"d3-01": {"tokens": 5}}
    assert read_saved(path, {"version": "v2", "model": "m"}) == {}
    assert read_saved(tmp_path / "none.json", key) == {}
