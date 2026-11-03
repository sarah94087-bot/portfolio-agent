import json

import pytest
from portfolio_agent.ingest import Chunk, chunk, load
from pydantic import ValidationError

from retrieval.harness import (
    METRICS,
    D1Item,
    check_gold,
    compare,
    load_d1,
    percentile,
    run,
    write_results,
)

D1 = """
- id: d1-001
  question: "How did she stop machine output from overwriting an editor?"
  lang: en
  category: single_hop
  expected_behavior: answer
  gold_chunks: [demo#decisions]
  split: dev
- id: d1-002
  question: "איך היא מנעה מתרגום אוטומטי לדרוס עריכה של אדם?"
  lang: he
  category: cross_lingual
  expected_behavior: answer
  gold_chunks: [demo#architecture, demo#decisions]
  split: dev
- id: d1-003
  question: "What is her salary expectation?"
  lang: en
  category: unanswerable
  expected_behavior: refuse_no_info
  split: dev
- id: d1-004
  question: "What did she measure?"
  lang: en
  category: single_hop
  expected_behavior: answer
  gold_chunks: [demo#results]
  split: test
"""


def c(id_: str, *sections: str) -> Chunk:
    record, _, _ = id_.partition("#")
    return Chunk(id_, record, sections or (id_.partition("#")[2],), "text")


def fixed(*chunks: Chunk):
    """A retriever that returns the same ranking for every query."""
    return lambda query, k: list(chunks)


@pytest.fixture
def items(tmp_path):
    path = tmp_path / "d1.yaml"
    path.write_text(D1, encoding="utf-8")
    return load_d1(path)


def test_run_scores_only_answerable_questions_of_the_split(items):
    result = run(items, fixed(c("demo#decisions"), c("demo#architecture")))
    assert result["n"] == 2
    assert [r["id"] for r in result["items"]] == ["d1-001", "d1-002"]
    assert result["skipped"] == {"refuse_no_info": 1}
    assert run(items, fixed(c("demo#results")), split="test")["n"] == 1


def test_run_reports_every_metric_per_group(items):
    result = run(items, fixed(c("x#problem"), c("demo#architecture"), c("demo#decisions")))
    assert set(result["groups"]) == {"all", "he", "en", "cross_lingual"}
    assert set(result["groups"]["all"]) == set(METRICS)
    en, he = result["items"]
    assert (en["recall@3"], en["mrr"]) == (1.0, pytest.approx(1 / 3))
    assert (he["recall@3"], he["mrr"]) == (1.0, 0.5)
    assert result["groups"]["en"]["mrr"]["mean"] == pytest.approx(1 / 3)
    assert result["groups"]["all"]["mrr"]["n"] == 2


def test_a_c4_record_finds_gold_sections_through_what_it_covers(items):
    whole = Chunk("demo#all", "demo", ("problem", "architecture", "decisions"), "text")
    result = run(items, fixed(whole))
    assert [r["recall@3"] for r in result["items"]] == [1.0, 1.0]


def test_run_keeps_only_k_results_and_records_what_it_retrieved(items):
    ranking = [c(f"x#s{i}") for i in range(12)] + [c("demo#decisions")]
    result = run(items, fixed(*ranking), k=10)
    assert len(result["items"][0]["retrieved"]) == 10
    assert result["items"][0]["recall@10"] == 0.0


def test_q1_runs_use_the_saved_queries(items):
    seen = []

    def retrieve(query, k):
        seen.append(query)
        return [c("demo#decisions")]

    queries = {"d1-001": "machine translation overwrite human edit", "d1-002": "human gate"}
    result = run(items, retrieve, queries=queries)
    assert seen == list(queries.values())
    assert result["items"][1]["query"] == "human gate"
    with pytest.raises(ValueError, match="d1-002"):
        run(items, retrieve, queries={"d1-001": "x"})


def test_compare_pairs_two_runs_by_question(items):
    weak = run(items, fixed(c("x#problem")))
    strong = run(items, fixed(c("demo#decisions"), c("demo#architecture")))
    d = compare(weak, strong, "recall@5")
    assert d.mean == 1.0
    assert d.significant
    assert compare(weak, strong, "recall@5", group="he").n == 1


def test_compare_refuses_runs_over_different_questions(items):
    with pytest.raises(ValueError, match="same questions"):
        compare(run(items, fixed(c("x#a"))), run(items, fixed(c("x#a")), split="test"))


def test_d1_rules():
    base = dict(id="d1-010", question="q", lang="en", category="single_hop", split="dev")
    with pytest.raises(ValidationError, match="needs gold_chunks"):
        D1Item(**base, expected_behavior="answer")
    with pytest.raises(ValidationError, match="has no gold_chunks"):
        D1Item(**base, expected_behavior="refuse_no_info", gold_chunks=["demo#problem"])
    with pytest.raises(ValidationError):
        D1Item(**{**base, "id": "q10"}, expected_behavior="refuse_no_info")


def test_duplicate_ids_fail(tmp_path):
    path = tmp_path / "d1.yaml"
    path.write_text(D1 + D1, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_d1(path)


def test_gold_chunks_must_exist_in_the_knowledge_base(items):
    c1 = {ch.id for ch in chunk(load(), "C1")}
    errors = check_gold(items, c1)
    assert "d1-001: gold chunk 'demo#decisions' is not in the knowledge base" in errors
    assert check_gold(items, c1 | {"demo#decisions", "demo#architecture", "demo#results"}) == []


def test_percentile_interpolates():
    assert percentile([10, 20, 30, 40], 0.5) == 25
    assert percentile([7], 0.95) == 7


def test_results_file_is_named_by_date_commit_and_config(items, tmp_path):
    result = run(items, fixed(c("demo#decisions")))
    path = write_results(result, "C1-R1-Q0", tmp_path, commit="abc1234")
    assert path.name.endswith("-abc1234-C1-R1-Q0.json")
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["config"] == "C1-R1-Q0"
    assert saved["items"][1]["lang"] == "he"
