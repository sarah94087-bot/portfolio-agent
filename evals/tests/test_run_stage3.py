import os

import psycopg
import pytest
from portfolio_agent.retrieval.lexical import Hit

from retrieval.harness import D1Item
from retrieval.rewrite import messages, parse, tool
from retrieval.run_stage3 import SIMPLEST_FIRST, TABLE, mean_of_runs, multi_query, stage3
from tests.test_embedders import Fake

DB_URL = os.environ.get("TEST_DATABASE_URL")


def call(arguments: str) -> dict:
    return {"tool_calls": [{"function": {"name": "search_portfolio", "arguments": arguments}}]}


def test_q1_tool_is_the_agent_schema_and_q2_adds_two_phrasings():
    q1 = tool("q1")["function"]["parameters"]
    q2 = tool("q2")["function"]["parameters"]
    assert q1["required"] == ["query"] and "alternative_queries" not in q1["properties"]
    alt = q2["properties"]["alternative_queries"]
    assert alt["minItems"] == alt["maxItems"] == 2
    assert q2["required"] == ["query", "alternative_queries"]


def test_parse_reads_the_tool_arguments_and_refuses_a_missing_call():
    assert parse(call('{"query": " kafka latency "}'), "q1") == {
        "query": "kafka latency", "alternatives": []}
    got = parse(call('{"query": "a", "alternative_queries": ["b", "c"]}'), "q2")
    assert got == {"query": "a", "alternatives": ["b", "c"]}
    with pytest.raises(ValueError):
        parse({"content": "hi"}, "q1")
    with pytest.raises(ValueError):
        parse(call('{"query": "a", "alternative_queries": ["b"]}'), "q2")


def test_messages_put_a_follow_ups_history_before_the_question():
    base = {"id": "d1-001", "lang": "en", "category": "multi_hop",
            "expected_behavior": "answer", "gold_chunks": ["r#s"], "split": "dev"}
    alone = messages(D1Item(question="q?", **base))
    assert [m["role"] for m in alone] == ["system", "user"]
    follow = messages(D1Item(question="And there?", history=["Tell me about X."], **base))
    assert [m["content"] for m in follow[1:]] == ["Tell me about X.", "And there?"]


def hit(cid: str) -> Hit:
    return Hit(cid, cid.split("#")[0], ("s",), "text", {"rrf": 0.1})


def test_multi_query_fuses_the_rankings_of_every_phrasing():
    rankings = {"q": ["a#1", "b#1"], "alt1": ["b#1", "c#1"], "alt2": ["b#1"]}
    seen = []

    def search(query, k):
        seen.append(query)
        return [hit(c) for c in rankings[query]]

    hits = multi_query(search, {"q": ["alt1", "alt2"]})("q", 2)
    assert seen == ["q", "alt1", "alt2"]
    assert [h.id for h in hits] == ["b#1", "a#1"]  # b is in all three lists
    assert hits[0].scores["multi_rrf"] == pytest.approx(1 / 62 + 1 / 61 + 1 / 61)


def result(recalls: list[float], queries: list[str]) -> dict:
    rows = [{"id": f"d1-{i:03d}", "lang": "he", "category": "single_hop", "query": q,
             "recall@3": r, "recall@5": r, "recall@10": r, "mrr": r, "ndcg@5": r}
            for i, (r, q) in enumerate(zip(recalls, queries, strict=True))]
    return {"split": "dev", "skipped": {}, "items": rows,
            "groups": {"all": {"recall@5": {"mean": sum(recalls) / len(recalls)}}},
            "latency_ms": {"p50": 10.0, "p95": 20.0}}


def test_mean_of_runs_averages_each_question_and_keeps_every_query():
    runs = [result([1.0, 0.0], ["a", "b"]), result([0.0, 0.0], ["a2", "b2"]),
            result([1.0, 1.0], ["a3", "b3"])]
    out = mean_of_runs(runs)
    assert [r["recall@5"] for r in out["items"]] == pytest.approx([2 / 3, 1 / 3])
    assert out["items"][0]["query"] == ["a", "a2", "a3"]
    assert out["groups"]["he"]["recall@5"]["mean"] == pytest.approx(0.5)
    assert out["per_run_recall@5"] == pytest.approx([0.5, 0.0, 1.0])
    assert out["runs"] == 3
    other = result([1.0, 1.0], ["a", "b"])
    other["items"][1]["id"] = "d1-999"
    with pytest.raises(ValueError):
        mean_of_runs([runs[0], other])


@pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL not set")
def test_stage3_scores_q0_q1_and_the_mean_of_q2_runs_and_drops_its_table():
    question = "איך אדם מאשר תרגום מכונה?"
    items = [D1Item(id="d1-001", question=question, lang="he", category="cross_lingual",
                    expected_behavior="answer", gold_chunks=["human-gated-translation#problem"],
                    split="dev")]
    q1 = {"d1-001": {"query": "Sarah Halevy human approval of machine translation",
                     "alternatives": []}}
    q2 = [{"d1-001": {"query": f"machine translation review {r}",
                      "alternatives": ["Sarah's human gate translation", "translation editor"]}}
          for r in (1, 2, 3)]
    out = stage3(DB_URL, items, Fake(), q1, q2)
    assert list(out["results"]) == list(SIMPLEST_FIRST)
    assert out["results"]["Q0"]["items"][0]["query"] == question
    # The name comes off the agent's query (ADR-0013), and never off the visitor's question.
    assert out["results"]["Q1"]["items"][0]["query"] == "human approval of machine translation"
    assert out["results"]["Q2"]["runs"] == 3 and len(out["q2_runs"]) == 3
    assert out["results"]["Q2"]["items"][0]["query"][2] == "machine translation review 3"
    assert out["decision"]["chosen"] in SIMPLEST_FIRST
    with psycopg.connect(DB_URL) as conn:
        left = conn.execute(
            "select count(*) from pg_class where relname = %s", (TABLE,)
        ).fetchone()[0]
    assert left == 0
