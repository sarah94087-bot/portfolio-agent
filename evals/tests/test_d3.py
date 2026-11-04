"""Checks on the real D3 job-match set (evals/datasets/d3.yaml) against the knowledge base."""

from collections import Counter

import pytest
from portfolio_agent.ingest import load

from jobmatch.dataset import Requirement, load_d3, overall, score


@pytest.fixture(scope="module")
def jobs():
    return load_d3()


def test_every_job_has_requirements_and_at_least_one_must(jobs):
    assert all(any(r.kind == "must" for r in j.requirements) for j in jobs)


def test_evidence_names_real_records_and_gaps_have_none(jobs):
    records = {d.record.id for d in load()}
    for job in jobs:
        for r in job.requirements:
            assert set(r.evidence) <= records, (job.id, r.id, set(r.evidence) - records)
            if r.label == "none":
                assert not r.evidence, (job.id, r.id)


def test_records_not_written_yet_are_flagged_not_cited(jobs):
    records = {d.record.id for d in load()}
    for job in jobs:
        for r in job.requirements:
            assert not set(r.depends_on) & set(r.evidence), (job.id, r.id)
            assert not set(r.depends_on) & records, f"{r.depends_on} exists now: update {r.id}"


def test_the_set_covers_every_category_and_three_injections(jobs):
    # docs/03-evaluation-methodology.md, section 2: high, medium and low match, unrelated roles,
    # and 3 jobs with indirect injection.
    labels = Counter(r.label for j in jobs for r in j.requirements)
    assert labels["none"] > 0 and labels["partial"] > 0
    assert {overall(j.requirements) for j in jobs} == {"high", "partial", "low"}
    assert any(all(r.label == "none" for r in j.requirements) for j in jobs)  # unrelated
    assert sum(j.injection for j in jobs) == 3
    assert 10 <= len(jobs) <= 15


def req(kind: str, label: str) -> Requirement:
    return Requirement(id="1.1", text="x", kind=kind, label=label)


def test_score_weighs_must_twice_and_maps_to_categories():
    # docs/07-advanced-capabilities.md, section 2
    reqs = [req("must", "strong"), req("must", "none"), req("nice", "partial")]
    assert score(reqs) == pytest.approx((2 * 1 + 0 + 0.5) / 5)
    assert overall(reqs) == "partial"
    assert overall([req("must", "strong"), req("nice", "partial")]) == "high"
    assert overall([req("must", "none"), req("nice", "strong")]) == "low"
