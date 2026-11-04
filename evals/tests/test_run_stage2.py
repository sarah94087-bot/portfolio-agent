import os

import psycopg
import pytest

from retrieval.harness import D1Item
from retrieval.run_stage2 import RETRIEVERS, TABLE, config_name, labels, stage2
from tests.test_embedders import Fake

DB_URL = os.environ.get("TEST_DATABASE_URL")


def test_labels_name_the_model_for_r2_and_r3_only():
    assert labels(Fake()) == {"R1": "R1", "R2": "R2-fake", "R3": "R3-fake"}
    assert config_name("R3-fake") == "stage2-C4-R3-fake-Q0"


@pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL not set")
def test_stage2_runs_r1_to_r3_on_one_table_and_drops_it():
    q = "How does a human approve machine translation output?"
    items = [
        D1Item(id="d1-001", question=q, lang="en", category="single_hop",
               expected_behavior="answer", gold_chunks=["human-gated-translation#problem"],
               split="dev"),
        D1Item(id="d1-002", question=q, lang="en", category="single_hop",
               expected_behavior="answer", gold_chunks=["human-gated-translation#problem"],
               split="test"),
    ]
    fake = Fake()
    out = stage2(DB_URL, items, fake)
    assert list(out["results"]) == list(RETRIEVERS)
    for r, result in out["results"].items():
        assert result["strategy"] == "C4" and result["n"] == 1, r
        assert result["items"][0]["retrieved"], f"{r} returned nothing"
    assert out["results"]["R3"]["retriever"] == "R3-fake"
    # Passages once; then the dev question once for R2 and once for R3 (Cached dedups in runs).
    kinds = [k for k, _ in fake.calls]
    assert kinds == ["passage", "query", "query"]
    assert out["decision"]["chosen"] in RETRIEVERS
    with psycopg.connect(DB_URL) as conn:
        left = conn.execute(
            "select count(*) from pg_class where relname = %s", (TABLE,)
        ).fetchone()[0]
    assert left == 0
