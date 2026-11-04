"""R2 against Postgres with pgvector. Runs only when TEST_DATABASE_URL is set (CI, or local)."""

import os

import psycopg
import pytest

from portfolio_agent import migrate
from portfolio_agent.ingest import Chunk, upsert
from portfolio_agent.retrieval.vector import (
    add_embedding_column,
    search,
    store_embeddings,
    to_vector,
)

DB_URL = os.environ.get("TEST_DATABASE_URL")


def test_to_vector_is_a_pgvector_literal():
    assert to_vector([1.0, -0.5, 0.25]) == "[1,-0.5,0.25]"


@pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL not set")
def test_search_ranks_by_cosine_and_skips_chunks_without_a_vector():
    migrate.run(DB_URL)
    chunks = [Chunk(f"r#{s}", "r", (s,), f"text {s}") for s in ("a", "b", "c", "d")]
    with psycopg.connect(DB_URL, autocommit=True) as conn:
        conn.execute("create temp table v (like chunks including all)")
        try:
            upsert(conn, chunks, "v")
            add_embedding_column(conn, "v", 3)
            add_embedding_column(conn, "v", 3)  # idempotent
            store_embeddings(conn, "v", {
                "r#a": [1, 0, 0], "r#b": [0.8, 0.6, 0], "r#c": [0, 0, 1],
            })
            hits = search(conn, [1, 0, 0], k=5, table="v")
            assert [h.id for h in hits] == ["r#a", "r#b", "r#c"]
            assert hits[0].scores["vector"] == pytest.approx(1.0)
            assert hits[1].scores["vector"] == pytest.approx(0.8)
            assert hits[0].sections == ("a",)
            assert [h.id for h in search(conn, [0, 0, 1], k=1, table="v")] == ["r#c"]
        finally:
            conn.execute("drop table v")
