"""Checks on the real D2 adversarial set (evals/datasets/d2.yaml)."""

from collections import Counter

import pytest
from pydantic import ValidationError

from adversarial.dataset import CRITICAL, Case, load_d2
from jobmatch.dataset import load_d3


@pytest.fixture(scope="module")
def cases():
    return load_d2()


def test_size_categories_and_languages(cases):
    # docs/03-evaluation-methodology.md, section 2: 30 to 40 cases over nine categories
    assert 30 <= len(cases) <= 40
    by_category = Counter(c.category for c in cases)
    assert len(by_category) == 9 and min(by_category.values()) >= 3
    langs = Counter(c.lang for c in cases)
    assert abs(langs["he"] - langs["en"]) <= 4


def test_t1_runs_fifteen_critical_cases_from_every_category(cases):
    critical = [c for c in cases if c.critical]
    assert len(critical) == CRITICAL
    assert {c.category for c in critical} == {c.category for c in cases}


def test_indirect_injections_use_the_d3_injection_jobs(cases):
    injected = {j.id for j in load_d3() if j.injection}
    used = {c.job for c in cases if c.job}
    assert used == injected


def test_a_case_needs_an_attack_and_tools_go_with_their_check():
    base = {"id": "d2-999", "category": "direct_injection", "lang": "en", "expect": "x"}
    with pytest.raises(ValidationError):
        Case(checks=["canary"], **base)
    with pytest.raises(ValidationError):
        Case(turns=["hi"], checks=["canary"], forbidden_tools=["request_contact"], **base)
    with pytest.raises(ValidationError):
        Case(turns=["hi"], checks=["canary"], job="d3-09", **base)
    with pytest.raises(ValidationError):
        Case(turns=["hi"], checks=["forbidden_tools"], forbidden_tools=["send_email"], **base)
