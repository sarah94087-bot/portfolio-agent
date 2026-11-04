import os

import psycopg
import pytest

from retrieval.harness import GROUPS as HARNESS_GROUPS
from retrieval.harness import D1Item
from retrieval.run_stage1 import (
    GROUPS,
    config_name,
    decide,
    pairwise,
    passes_hebrew,
    stage1,
    table,
)

DB_URL = os.environ.get("TEST_DATABASE_URL")


def fake(recall: list[float]) -> dict:
    """A run result with only what pairwise and decide read: groups and per-item rows."""
    rows = [
        {"id": f"d1-{i:03d}", "lang": "he" if i % 2 else "en",
         "category": "cross_lingual" if i % 3 == 0 else "single_hop", "recall@5": r}
        for i, r in enumerate(recall)
    ]
    groups = {}
    for g, keep in HARNESS_GROUPS.items():
        vals = [r["recall@5"] for r in rows if keep(r)]
        mean = sum(vals) / len(vals)
        groups[g] = {"recall@5": {"mean": mean, "low": 0, "high": 1, "n": len(vals)}}
    return {"items": rows, "groups": groups, "chunks": 1, "latency_ms": {"p50": 1, "p95": 1}}


def with_mrr(result: dict) -> dict:
    for g in result["groups"].values():
        g["mrr"] = g["ndcg@5"] = {"mean": 0.5}
    return result


N = 40


def test_pairwise_covers_every_pair_and_group():
    results = {s: fake([1.0] * N) for s in ("C1", "C2", "C3")}
    rows = pairwise(results)
    assert len(rows) == 3 * len(GROUPS)
    assert {(r["a"], r["b"]) for r in rows} == {("C1", "C2"), ("C1", "C3"), ("C2", "C3")}
    assert not any(r["significant"] for r in rows)


def test_decide_picks_the_simplest_when_the_gap_is_noise():
    results = {
        "C4": fake([1.0] * (N - 1) + [0.0]),
        "C1": fake([1.0] * N),
        "C2": fake([1.0] * N),
        "C3": fake([1.0] * N),
    }
    d = decide(results)
    assert d["best"] == "C1"  # the simplest among the ties at the top
    assert d["chosen"] == "C4"  # one question worse is not significant
    assert d["versus_best"]["C4"]["worse"] is False


def test_decide_skips_a_strategy_that_is_significantly_worse():
    results = {
        "C4": fake([0.0] * (N // 2) + [1.0] * (N // 2)),
        "C1": fake([1.0] * N),
        "C2": fake([1.0] * N),
    }
    d = decide(results)
    assert d["versus_best"]["C4"]["worse"] is True
    assert d["chosen"] == "C1"


def test_best_must_pass_the_hebrew_threshold_when_one_does():
    # C2 is best overall only through English; C1 passes Hebrew and is chosen as the best.
    en_only = [1.0 if i % 2 == 0 else 0.5 for i in range(N)]
    he_ok = [0.9] * N
    results = {"C1": fake(he_ok), "C2": fake([1.0 if i % 2 == 0 else 0.82 for i in range(N)])}
    assert not passes_hebrew(fake(en_only))
    assert passes_hebrew(results["C1"]) and not passes_hebrew(results["C2"])
    d = decide(results)
    assert d["best"] == "C1" and d["best_passes_hebrew"]


def test_decide_says_when_nothing_passes_hebrew():
    results = {"C1": fake([0.5] * N), "C2": fake([0.6] * N)}
    d = decide(results)
    assert d["best"] == "C2" and not d["best_passes_hebrew"]


def test_table_has_a_row_per_strategy():
    results = {s: with_mrr(fake([1.0] * N)) for s in ("C1", "C4")}
    lines = table(results).splitlines()
    assert len(lines) == 4 and lines[2].startswith("| C1 |")
    assert "(n=40)" in lines[2]
    assert config_name("C3") == "stage1-C3-R1-Q0"


def item(i: int, question: str, gold: list[str], split: str = "dev") -> D1Item:
    return D1Item(
        id=f"d1-{i:03d}", question=question, lang="en", category="single_hop",
        expected_behavior="answer", gold_chunks=gold, split=split,
    )


@pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL not set")
def test_stage1_runs_every_strategy_on_dev_only_and_drops_its_tables():
    items = [
        item(1, "How does a human approve machine translation output?",
             ["human-gated-translation#problem"]),
        item(2, "How does a human approve machine translation output?",
             ["human-gated-translation#problem"], split="test"),
    ]
    out = stage1(DB_URL, items)
    assert list(out["results"]) == ["C1", "C2", "C3", "C4"]
    for r in out["results"].values():
        assert r["split"] == "dev" and r["n"] == 1
        assert [row["id"] for row in r["items"]] == ["d1-001"]
        assert r["items"][0]["retrieved"][0].startswith("human-gated-translation#")
    # The whole record holds #problem, so C4 cannot miss it once the record ranks first.
    assert out["results"]["C4"]["groups"]["all"]["recall@5"]["mean"] == 1.0
    assert out["decision"]["chosen"] in out["results"]
    assert {r["group"] for r in out["comparisons"]} == {"all", "en"}
    with psycopg.connect(DB_URL) as conn:
        left = conn.execute(
            "select count(*) from pg_class where relname like 'stage1\\_%'"
        ).fetchone()[0]
    assert left == 0
