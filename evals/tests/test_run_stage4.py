import json
import os

import pytest

from retrieval.harness import D1Item
from retrieval.run_stage4 import prompt, rank_tool, stage4
from tests.test_embedders import Fake

DB_URL = os.environ.get("TEST_DATABASE_URL")


def test_rank_tool_limits_the_answer_to_the_candidate_ids():
    ranking = rank_tool(["a#all", "b#all"])["function"]["parameters"]["properties"]["ranking"]
    assert ranking["items"]["enum"] == ["a#all", "b#all"]
    assert ranking["maxItems"] == 2


def test_prompt_has_the_question_the_query_and_each_candidate():
    from portfolio_agent.retrieval.lexical import Hit

    text = prompt("שאלה?", "query", [Hit("a#all", "a", ("s",), "alpha", {})])
    assert "Visitor's question: שאלה?" in text and "Search query: query" in text
    assert "[a#all]\nalpha" in text


def items() -> list[D1Item]:
    q = "How does a human approve machine translation output?"
    return [D1Item(id=f"d1-00{n}", question=q, lang="en", category="single_hop",
                   expected_behavior="answer", gold_chunks=["human-gated-translation#problem"],
                   split="dev") for n in (1, 2)]


Q1 = {"d1-001": {"query": "Sarah Halevy human approval of machine translation",
                 "alternatives": []},
      "d1-002": {"query": "machine translation latency", "alternatives": []}}


@pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL not set")
def test_stage4_saves_each_ranking_reuses_it_and_scores_r3_against_r4(tmp_path):
    calls = []

    def reverse(question, query, hits):
        calls.append(query)
        return [h.id for h in reversed(hits)], 100, 0

    path = tmp_path / "r4.json"
    out = stage4(DB_URL, items(), Fake(), Q1, reverse, path, "test-model")
    assert calls == ["human approval of machine translation", "machine translation latency"]
    assert set(out["results"]) == {"R3", "R4"}
    r3, r4 = (out["results"][r]["items"][0]["retrieved"] for r in ("R3", "R4"))
    assert r4 == list(reversed(r3))
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["calls"] == 2 and saved["tokens"] == 200 and saved["model"] == "test-model"
    assert all(r["wait_ms"] == 0 and r["ms"] >= 0 for r in saved["rankings"].values())
    # A second invocation asks for nothing: the rankings are saved, with their candidates.
    again = stage4(DB_URL, items(), Fake(), Q1, reverse, path, "test-model")
    assert len(calls) == 2 and again["status"]["spent_now"] == 0


@pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL not set")
def test_stage4_stops_at_the_token_ceiling_and_says_what_is_left(tmp_path):
    def costly(question, query, hits):
        return [h.id for h in hits], 1000, 0

    out = stage4(DB_URL, items(), Fake(), Q1, costly, tmp_path / "r4.json", max_tokens=500)
    assert "results" not in out
    assert out["status"]["missing"] == ["d1-002"] and out["status"]["calls"] == 1
    pilot = stage4(DB_URL, items(), Fake(), Q1, costly, tmp_path / "p.json", pilot=1)
    assert "results" not in pilot and pilot["status"]["calls"] == 1


@pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL not set")
def test_a_failed_ranking_keeps_r3_order_and_is_counted(tmp_path):
    def failing(question, query, hits):
        return [], 0, 0

    out = stage4(DB_URL, items(), Fake(), Q1, failing, tmp_path / "r4.json")
    assert out["status"]["fallbacks"] == 2
    r3, r4 = (out["results"][r]["items"][0]["retrieved"] for r in ("R3", "R4"))
    assert r4 == r3


def groq(monkeypatch, answers):
    import httpx

    from retrieval import run_stage4

    monkeypatch.setenv("GROQ_API_KEY_EVALS", "test")
    monkeypatch.setenv("GROQ_MODEL", "test-model")
    sent = []

    def answer(request):
        sent.append(request)
        return next(answers)
    client = httpx.Client(transport=httpx.MockTransport(answer))
    return run_stage4.groq_ranker(client), sent


def tool_answer(ids):
    import httpx
    return httpx.Response(200, json={"usage": {"total_tokens": 7}, "choices": [{"message": {
        "tool_calls": [{"function": {"arguments": json.dumps({"ranking": ids})}}]}}]})


def test_a_bad_request_is_tried_once_more(monkeypatch):
    import httpx
    from portfolio_agent.retrieval.lexical import Hit
    hits = [Hit("a#all", "a", (), "", {}), Hit("b#all", "b", (), "", {})]
    rank, sent = groq(monkeypatch, iter([httpx.Response(400), tool_answer(["b#all", "a#all"])]))
    assert rank("q", "q", hits) == (["b#all", "a#all"], 7, 0) and len(sent) == 2


def test_two_bad_requests_leave_r3_order_and_other_errors_raise(monkeypatch):
    import httpx
    from portfolio_agent.retrieval.lexical import Hit
    hits = [Hit("a#all", "a", (), "", {})]
    rank, sent = groq(monkeypatch, iter([httpx.Response(400), httpx.Response(400)]))
    assert rank("q", "q", hits) == ([], 0, 0) and len(sent) == 2
    rank, _ = groq(monkeypatch, iter([httpx.Response(500)]))
    with pytest.raises(httpx.HTTPStatusError):
        rank("q", "q", hits)
