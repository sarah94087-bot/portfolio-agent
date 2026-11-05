"""The load command against a test database, with a fake embedder. Needs TEST_DATABASE_URL."""

import os

import psycopg
import pytest

from portfolio_agent import load
from portfolio_agent.retrieval.embedder import DIM

DB_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL not set")
TABLE = "load_kb"


class FakeE5:
    def __init__(self, model_dir, check=True):
        self.calls = 0

    def embed_passages(self, texts):
        self.calls += 1
        return [[1.0] + [0.0] * (DIM - 1) for _ in texts]


@pytest.fixture
def table(monkeypatch):
    monkeypatch.setattr(load.embedder, "E5Embedder", FakeE5)
    load.migrate.run(DB_URL)
    with psycopg.connect(DB_URL, autocommit=True) as conn:
        conn.execute(f"drop table if exists {TABLE}")
        conn.execute(f"create table {TABLE} (like chunks including all)")
    yield TABLE
    with psycopg.connect(DB_URL, autocommit=True) as conn:
        conn.execute(f"drop table {TABLE}")


def test_a_dry_run_writes_nothing(table):
    out = load.run(DB_URL, None, dry_run=True, table=table, log=lambda _: None)
    assert out["insert"] > 0 and out["update"] == out["delete"] == 0
    with psycopg.connect(DB_URL) as conn:
        assert conn.execute(f"select count(*) from {table}").fetchone()[0] == 0


def test_a_load_writes_every_chunk_with_a_vector_and_a_second_changes_nothing(table):
    first = load.run(DB_URL, "models", table=table, log=lambda _: None)
    assert first["inserted"] == first["embedded"] > 0 and first["deleted"] == 0
    second = load.run(DB_URL, "models", table=table, log=lambda _: None)
    assert second["inserted"] == second["updated"] == second["embedded"] == 0
    assert second["kb_version"] == first["kb_version"]


def test_a_chunk_no_longer_in_the_portfolio_is_deleted_and_shown_first(table):
    load.run(DB_URL, "models", table=table, log=lambda _: None)
    with psycopg.connect(DB_URL, autocommit=True) as conn:
        conn.execute(f"insert into {table} (id, record_id, sections, text, context_header,"
                     " aliases, norm, content_hash) values ('gone#all', 'gone', '{all}', 't',"
                     " 'h', '', 'n', 'x')")
    lines = []
    load.run(DB_URL, None, dry_run=True, table=table, log=lines.append)
    assert "would delete 1: gone#all" in lines
    out = load.run(DB_URL, "models", table=table, log=lambda _: None)
    assert out["deleted"] == 1


def test_without_model_files_nothing_is_written(table, monkeypatch):
    with pytest.raises(SystemExit):
        load.run(DB_URL, None, table=table, log=lambda _: None)


def test_the_target_is_shown_without_the_password():
    assert load.where("postgresql://u:secret@db.example.com/app") == "db.example.com:5432/app"
