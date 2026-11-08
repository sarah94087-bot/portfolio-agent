"""The code's part of a job match: caps by proof, and the score (docs/07, section 2)."""

import pytest

from portfolio_agent.tools import job_rules as rules
from portfolio_agent.tools.job_rules import Proof, Rating, Requirement

WORK = Proof("work", (2025, 2026))
CANDIDATES = {"p#all": WORK, "skills#a": Proof("studied"), "skills#b": Proof("listed"),
              "skills#c": Proof("used"), "education#all": Proof("other")}
REQ = Requirement("r1", "Python services", "must")


def enforce(strength, evidence, requirement=REQ):
    return rules.enforce(requirement, Rating(strength, tuple(evidence), "because"), CANDIDATES,
                         "nothing found")


def test_a_project_or_role_passage_allows_strong():
    r = enforce("strong", ["p#all"])
    assert r.strength == "strong" and r.evidence == ("p#all",) and r.capped_from is None


@pytest.mark.parametrize("chunk", ["skills#a", "skills#b", "skills#c", "education#all"])
def test_anything_but_a_project_or_role_is_capped_at_partial(chunk):
    r = enforce("strong", [chunk])
    assert r.strength == "partial" and r.capped_from == "strong"


def test_a_listed_skill_is_marked_as_cv_only():
    assert enforce("partial", ["skills#b"]).cv_only is True
    assert enforce("partial", ["skills#b", "p#all"]).cv_only is False


def test_a_project_next_to_a_skill_still_allows_strong():
    assert enforce("strong", ["skills#a", "p#all"]).strength == "strong"


@pytest.mark.parametrize("strength", ["strong", "partial"])
def test_no_valid_citation_is_a_gap_with_the_fixed_text(strength):
    r = enforce(strength, ["made-up#all"])
    assert r.strength == "none" and r.evidence == () and r.rationale == "nothing found"
    assert r.dropped == ("made-up#all",) and r.capped_from == strength


def test_a_citation_retrieved_for_another_requirement_is_dropped():
    r = rules.enforce(REQ, Rating("strong", ("p#all", "other#all"), "x"), {"p#all": WORK}, "n")
    assert r.evidence == ("p#all",) and r.dropped == ("other#all",)


def test_the_models_none_clears_its_citations():
    r = enforce("none", ["p#all"])
    assert r.strength == "none" and r.evidence == () and r.capped_from is None


@pytest.mark.parametrize("text,years", [
    ("5+ years of Python", 5), ("at least 3 years in production", 3), ("3-5 yrs backend", 3),
    ("5 שנות ניסיון לפחות", 5), ("ניסיון של שנתיים", 2), ("Python", None),
])
def test_years_are_read_from_the_text_too(text, years):
    assert rules.required_years(Requirement("r", text, "must")) == years


def test_years_the_cited_work_does_not_cover_cap_at_partial_and_say_so():
    r = enforce("strong", ["p#all"], Requirement("r", "Python", "must", years=5))
    assert r.strength == "partial" and r.capped_from == "strong"
    assert (r.years_required, r.years_covered) == (5, 2)


def test_years_the_cited_work_covers_do_not_cap():
    r = enforce("strong", ["p#all"], Requirement("r", "Python", "must", years=2))
    assert r.strength == "strong" and r.years_required is None


def test_years_with_no_period_cover_nothing():
    assert rules.years_covered([Proof("studied")]) == 0
    assert enforce("partial", ["skills#a"], Requirement("r", "x", "must", years=1)
                   ).years_covered == 0


def test_a_rationale_is_cut_to_25_words():
    r = rules.enforce(REQ, Rating("strong", ("p#all",), " ".join("w" * 40)), CANDIDATES, "n")
    assert len(r.rationale.split()) == 25 and r.rationale.endswith("…")


def test_at_most_three_citations():
    many = {f"c{i}#all": WORK for i in range(5)}
    r = rules.enforce(REQ, Rating("strong", tuple(many), "x"), many, "n")
    assert len(r.evidence) == 3


def test_the_score_weighs_a_must_twice_a_nice():
    assert rules.score([("must", "strong"), ("nice", "none")]) == pytest.approx(2 / 3)
    assert rules.score([("must", "partial"), ("must", "none")]) == pytest.approx(0.25)
    assert rules.score([]) == 0.0


@pytest.mark.parametrize("value,level", [
    (0.75, "high"), (0.749, "partial"), (0.45, "partial"), (0.449, "low"),
])
def test_categories_at_their_edges(value, level):
    assert rules.overall(value) == level


def test_gaps_list_the_musts_first_whatever_their_order():
    a = enforce("none", [], Requirement("1", "nice one", "nice"))
    b = enforce("none", [], Requirement("2", "must one", "must"))
    c = enforce("strong", ["p#all"], Requirement("3", "covered", "must"))
    assert [g.requirement.id for g in rules.gaps([a, c, b])] == ["2", "1"]
