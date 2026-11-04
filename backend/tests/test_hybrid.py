"""R3. The fusion is pure; the search runs only when TEST_DATABASE_URL is set (CI, or local)."""

import os

import psycopg
import pytest

from portfolio_agent import migrate
from portfolio_agent.ingest import Chunk, upsert
from portfolio_agent.retrieval.hybrid import rrf, search
from portfolio_agent.retrieval.vector import add_embedding_column, store_embeddings

DB_URL = os.environ.get("TEST_DATABASE_URL")


def test_rrf_sums_reciprocal_ranks_with_k_60():
    fused = dict(rrf([["a", "b"], ["b", "c"]]))
    assert fused["a"] == pytest.approx(1 / 61)
    assert fused["b"] == pytest.approx(1 / 62 + 1 / 61)
    assert fused["c"] == pytest.approx(1 / 62)


def test_rrf_puts_an_id_found_by_both_first_and_breaks_ties_by_id():
    assert [cid for cid, _ in rrf([["x", "m"], ["y", "m"]])] == ["m", "x", "y"]
    assert [cid for cid, _ in rrf([["b"], ["a"]])] == ["a", "b"]
    assert rrf([[], []]) == []


@pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL not set")
def test_search_returns_what_either_side_finds_with_both_scores():
    migrate.run(DB_URL)
    chunks = [
        Chunk("lex#a", "lex", ("a",),
              "pgvector cosine distance in postgres with an exact scan over every row"),
        Chunk("vec#b", "vec", ("b",), "kafka streams"),
        Chunk("both#c", "both", ("c",), "pgvector inside kafka"),
    ]
    with psycopg.connect(DB_URL, autocommit=True) as conn:
        conn.execute("create temp table h (like chunks including all)")
        try:
            upsert(conn, chunks, "h")
            add_embedding_column(conn, "h", 2)
            store_embeddings(conn, "h", {"lex#a": [0, 1], "vec#b": [1, 0], "both#c": [0.9, 0.1]})
            hits = search(conn, "pgvector", [1, 0], k=5, table="h")
            ids = [h.id for h in hits]
            # First for R1 (shorter, so BM25 ranks it above lex#a) and second for R2.
            assert ids[0] == "both#c"
            assert set(ids) == {"lex#a", "vec#b", "both#c"}
            by_id = {h.id: h for h in hits}
            assert by_id["both#c"].scores["lexical"] and by_id["both#c"].scores["vector"]
            assert by_id["vec#b"].scores["lexical"] is None
            assert by_id["lex#a"].sections == ("a",)
            assert len(search(conn, "pgvector", [1, 0], k=1, table="h")) == 1
        finally:
            conn.execute("drop table h")
