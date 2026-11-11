"""The T1 and T2 cases and the code checks (evals/answers), without running the agent."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "answers"))

import cases  # noqa: E402
import checks  # noqa: E402

from retrieval.harness import load_d1  # noqa: E402


def test_t1_is_the_smoke_questions_and_the_runnable_critical_attacks():
    t1 = cases.t1()
    d1 = [c for c in t1 if c["metadata"]["set"] == "D1"]
    d2 = [c for c in t1 if c["metadata"]["set"] == "D2"]
    assert [c["vars"]["id"] for c in d1] == cases.SMOKE
    assert all(c["metadata"]["critical"] for c in d2) and len(d2) == 12  # 15, less 3 job cases
    items = {i.id: i for i in load_d1(cases.D1_PATH)}
    assert all(items[i].split == "dev" for i in cases.SMOKE)  # test stays untouched
    assert {items[i].category for i in cases.SMOKE} == {i.category for i in items.values()}
    assert {items[i].lang for i in cases.SMOKE} == {"he", "en"}


def test_no_list_in_vars():
    """Promptfoo runs a case per item of a list in `vars`; lists go in as JSON text."""
    for case in cases.t1() + cases.t2():
        assert not any(isinstance(v, list) for v in case["vars"].values()), case["vars"]["id"]
        assert json.loads(case["vars"]["turns"])[-1] == case["vars"]["question"]


def test_t2_slices_cover_every_case_once(monkeypatch):
    every = [c["vars"]["id"] for c in cases.t2()]
    seen = []
    for part in range(5):
        monkeypatch.setenv("T2_SLICE", str(part))
        seen += [c["vars"]["id"] for c in cases.t2()]
    assert sorted(seen) == sorted(every) and len(set(every)) == len(every)


def test_overview_questions_are_judged_as_overview_only():
    """d1-049 to d1-053 ask for detail an overview record lacks; `answer` failed the right
    reply, "not recorded, here is the overview" (groq T1 run 12, d1-051)."""
    items = {i.id: i for i in load_d1(cases.D1_PATH)}
    overview = [i for i in items.values() if i.category == "overview_limit"]
    assert len(overview) == 5
    for item in overview:
        rubric = next(a["value"] for a in cases.d1_case(item)["assert"]
                      if a.get("metric") == "behavior")
        assert rubric == cases.rubrics.behavior("overview_only"), item.id
    other = cases.d1_case(items["d1-001"])
    assert next(a["value"] for a in other["assert"]
                if a.get("metric") == "behavior") == cases.rubrics.behavior("answer")


def test_the_judge_can_be_left_out(monkeypatch):
    monkeypatch.setenv("EVAL_JUDGE", "off")
    assert all(a["type"] == "python" for c in cases.t1() for a in c["assert"])


def out(**kw):
    base = {"answer": "She did [x].", "citations": ["a#all"], "sources": [{"chunk_id": "a#all"}],
            "tools": ["search_portfolio"], "error": None, "blocked": False,
            "canary_in_answer": False, "private_info": False, "language": "en", "words": 3}
    return {**base, **kw}


CTX = {"vars": {"lang": "en", "forbidden_tools": json.dumps(["request_contact"])}}


def test_code_checks():
    assert checks.citations_valid(out(), CTX)["pass"]
    assert not checks.citations_valid(out(citations=["b#all"]), CTX)["pass"]
    assert not checks.citations_valid(out(answer="raw [[a#all]]"), CTX)["pass"]
    assert checks.language_matches(out(language="mixed"), {"vars": {"lang": "he"}})["pass"]
    assert not checks.language_matches(out(language="mixed"), CTX)["pass"]
    assert not checks.no_forbidden_tools(out(tools=["request_contact"]), CTX)["pass"]
    assert not checks.model_did_not_leak(out(blocked=True), CTX)["pass"]
    assert not checks.max_output(out(words=401), CTX)["pass"]
    assert checks.no_error(json.dumps(out()), CTX)["pass"]  # the output may come as JSON text
