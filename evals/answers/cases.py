"""The Promptfoo test cases for T1 and T2 (docs/03-evaluation-methodology.md, section 7).

    T1: the 10 smoke questions of D1 below, and the critical D2 cases.
    T2: D1 `dev`, D2 and D4, a fifth a night by T2_SLICE (0 to 4), or all with T2_SLICE=all.

Cases that need a tool not built yet are left out and named in `skipped()`: job descriptions
need match_job (M7). EVAL_JUDGE=off leaves out the judge's rubrics, for a run with the scripted
model that costs nothing.
"""

import json
import os
import sys
from pathlib import Path

EVALS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EVALS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import rubrics  # noqa: E402

from adversarial.dataset import load_d2  # noqa: E402
from conversations.dataset import load_d4  # noqa: E402
from retrieval.harness import load_d1  # noqa: E402

D1_PATH = EVALS / "datasets" / "d1.yaml"
# One or two per category, both languages, all from `dev` (approved by Sarah, 2026-11-05).
SMOKE = [
    "d1-001",  # single_hop, en
    "d1-027",  # multi_hop, he
    "d1-033",  # comparative, en
    "d1-039",  # skill_level, en: Kubernetes, studied only
    "d1-044",  # skill_level, he: C#, studied only
    "d1-051",  # overview_limit, he
    "d1-054",  # unanswerable, en
    "d1-060",  # unanswerable, he
    "d1-069",  # off_topic, he
    "d1-071",  # cross_lingual, he
]
CODE = {  # D2 `checks` -> the code assertions in checks.py
    "canary": ["no_canary", "model_did_not_leak"],
    "private_info": ["no_private_info"],
    "forbidden_tools": ["no_forbidden_tools"],
    "citations": ["citations_valid"],
    "max_output": ["max_output"],
}


def _code(name: str) -> dict:
    return {"type": "python", "value": f"file://checks.py:{name}", "metric": name}


def _judge(metric: str, rubric: str) -> dict | None:
    if os.environ.get("EVAL_JUDGE") == "off":
        return None
    return {"type": "llm-rubric", "value": rubric, "metric": metric}


def _case(id_, set_, turns, lang, asserts, **meta) -> dict:
    return {
        "description": id_,
        # Lists go in as JSON text: Promptfoo reads a list in `vars` as values to test one by
        # one, and would run a case per item (found in the first dry run).
        "vars": {"id": id_, "turns": json.dumps(turns, ensure_ascii=False),
                 "question": turns[-1], "lang": lang,
                 "forbidden_tools": json.dumps(meta.get("forbidden_tools", []))},
        "assert": [a for a in asserts if a],
        "metadata": {"set": set_, "judge": rubrics.VERSION,
                     **{k: v for k, v in meta.items() if k != "forbidden_tools"}},
    }


def d1_case(item) -> dict:
    asserts = [_code(n) for n in ("no_error", "citations_valid", "language_matches",
                                  "no_private_info", "max_output")]
    asserts.append(_judge("behavior", rubrics.behavior(item.expected_behavior)))
    if item.expected_behavior == "answer":
        asserts.append(_judge("grounded", rubrics.grounded()))
    if item.answer_points:
        asserts.append(_judge("completeness", rubrics.completeness(item.answer_points)))
    if item.must_not:
        asserts.append(_judge("must_not", rubrics.must_not(item.must_not)))
    if item.category == "skill_level":
        asserts.append(_judge("skill_honesty", rubrics.skill_honesty()))
    if item.lang == "he":
        asserts.append(_judge("hebrew_address", rubrics.hebrew_address()))
    return _case(item.id, "D1", [*item.history, item.question], item.lang, asserts,
                 category=item.category, split=item.split)


def d2_case(case) -> dict:
    asserts = [_code("no_error")]
    asserts += [_code(n) for check in case.checks for n in CODE[check]]
    asserts.append(_judge("safe_behavior", rubrics.expect(case.expect)))
    if case.must_not:
        asserts.append(_judge("must_not", rubrics.must_not(case.must_not)))
    if case.lang == "he":
        asserts.append(_judge("hebrew_address", rubrics.hebrew_address()))
    return _case(case.id, "D2", case.turns, case.lang, asserts, category=case.category,
                 critical=case.critical, forbidden_tools=case.forbidden_tools)


def d4_case(conv) -> dict:
    asserts = [_code("no_error"), _code("citations_valid"), _code("no_private_info"),
               _judge("conversation", rubrics.conversation([t.expect for t in conv.turns]))]
    return _case(conv.id, "D4", [t.user for t in conv.turns], conv.turns[-1].lang, asserts,
                 title=conv.title)


def _runnable_d2():
    return [c for c in load_d2() if not (c.job or c.job_text)]


def _runnable_d4():
    return [c for c in load_d4() if all(t.user for t in c.turns)]


def t1(config=None) -> list[dict]:
    d1 = {i.id: i for i in load_d1(D1_PATH)}
    return [d1_case(d1[i]) for i in SMOKE] + [d2_case(c) for c in _runnable_d2() if c.critical]


def t2(config=None) -> list[dict]:
    cases = [d1_case(i) for i in load_d1(D1_PATH) if i.split == "dev"]
    cases += [d2_case(c) for c in _runnable_d2()] + [d4_case(c) for c in _runnable_d4()]
    part = os.environ.get("T2_SLICE", "all")
    return cases if part == "all" else cases[int(part)::5]


def tests(config=None) -> list[dict]:
    """The tier run.mjs asked for."""
    return t2() if os.environ.get("EVAL_TIER") == "t2" else t1()


def skipped() -> list[str]:
    """Cases left out until their tool exists."""
    d2 = [c.id for c in load_d2() if c.job or c.job_text]
    d4 = [c.id for c in load_d4() if not all(t.user for t in c.turns)]
    return d2 + d4
