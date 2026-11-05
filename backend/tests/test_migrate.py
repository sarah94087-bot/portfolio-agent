"""Runs only when TEST_DATABASE_URL points at an empty Postgres (CI, or local docker compose)."""

import os

import psycopg
import pytest

from portfolio_agent import migrate

DB_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL not set")


def test_migrations_apply_and_are_idempotent():
    first = migrate.run(DB_URL)
    second = migrate.run(DB_URL)
    assert second == []
    with psycopg.connect(DB_URL) as conn:
        names = {r[0] for r in conn.execute("select name from schema_migrations")}
        extensions = {r[0] for r in conn.execute("select extname from pg_extension")}
    assert set(first) <= names
    assert {"vector", "pg_trgm"} <= extensions


def test_chunks_get_a_384_dimension_embedding_column():
    from portfolio_agent.retrieval.vector import embedding_dim

    migrate.run(DB_URL)
    with psycopg.connect(DB_URL) as conn:
        assert embedding_dim(conn, "chunks") == 384
