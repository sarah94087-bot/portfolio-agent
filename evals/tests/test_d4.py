"""Checks on the real D4 conversations set (evals/datasets/d4.yaml)."""

import pytest
from portfolio_agent.ingest import chunk, load
from pydantic import ValidationError

from conversations.dataset import Turn, load_d4
from jobmatch.dataset import load_d3, overall


@pytest.fixture(scope="module")
def convs():
    return load_d4()


def test_size_and_what_the_set_covers(convs):
    # docs/03-evaluation-methodology.md, section 2: 10 to 12 conversations of 3 to 6 turns
    assert 10 <= len(convs) <= 12
    tests = {t for c in convs for t in c.tests}
    assert tests == {"follow_up", "language_switch", "project_to_job", "contact"}


def test_language_switches_really_switch(convs):
    for c in convs:
        langs = [t.lang for t in c.turns]
        assert ("language_switch" in c.tests) == (len(set(langs)) > 1), c.id


def test_gold_chunks_exist():
    ids = {f"{c.record_id}#{s}" for c in chunk(load(), "C1") for s in c.sections}
    for conv in load_d4():
        for t in conv.turns:
            assert set(t.gold_chunks) <= ids, (conv.id, set(t.gold_chunks) - ids)


def test_contact_rules(convs):
    jobs = {j.id: overall(j.requirements) for j in load_d3()}
    for c in convs:
        for i, t in enumerate(c.turns):
            # a draft only after the visitor agreed: an offer comes first
            if "request_contact" in t.tools:
                assert any(p.contact == "offer" for p in c.turns[:i]), c.id
            # US-7.1: a high match is a sign of interest, a low match is not
            if t.job:
                assert t.contact == {"high": "offer", "low": "none"}.get(jobs[t.job], t.contact)


def test_a_turn_has_a_message_or_a_job():
    with pytest.raises(ValidationError):
        Turn(lang="en", expect="x")
    with pytest.raises(ValidationError):
        Turn(user="hi", job="d3-01", lang="en", expect="x", tools=["match_job"])
    with pytest.raises(ValidationError):
        Turn(job="d3-01", lang="en", expect="x")
