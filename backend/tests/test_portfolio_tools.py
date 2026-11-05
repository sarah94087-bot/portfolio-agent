"""search_portfolio and get_project on the real knowledge base, chunked as C4 (ADR-0010).
The database tests run only when TEST_DATABASE_URL is set (CI, or local)."""

import json
import os

import psycopg
import pytest

from portfolio_agent import migrate
from portfolio_agent.ingest import chunk, load, upsert
from portfolio_agent.retrieval.lexical import Hit
from portfolio_agent.tools.portfolio import (
    GET_PROJECT,
    MAX_RESULTS,
    MAX_TOKENS,
    SEARCH,
    PortfolioContext,
    _within_budget,
)
from portfolio_agent.tools.registry import Registry

DB_URL = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL not set")
REGISTRY = Registry.of([SEARCH, GET_PROJECT])


def hit(i, words):
    return Hit(f"r{i}#all", f"r{i}", ("all",), " ".join(["w"] * words))


def test_the_budget_keeps_whole_chunks_best_first():
    hits = [hit(1, 1500), hit(2, 1400), hit(3, 200)]
    assert [h.id for h in _within_budget(hits)] == ["r1#all", "r2#all"]
    assert [h.id for h in _within_budget([hit(1, MAX_TOKENS + 500)])] == ["r1#all"]
    assert len(_within_budget([hit(i, 10) for i in range(9)])) == MAX_RESULTS


@pytest.fixture(scope="module")
def docs():
    return load()


@pytest.fixture
def ctx(docs):
    migrate.run(DB_URL)
    with psycopg.connect(DB_URL, autocommit=True) as conn:
        conn.execute("create temp table kb (like chunks including all)")
        upsert(conn, chunk(docs, "C4"), "kb")
        yield PortfolioContext.from_docs(conn, docs, table="kb")
        conn.execute("drop table kb")


def call(ctx, name, **args):
    result = REGISTRY.call(name, json.dumps(args), ctx)
    assert result.error is None, result.model_view
    return result, json.loads(result.model_view)


@needs_db
def test_search_follows_the_contract(ctx):
    result, model = call(ctx, "search_portfolio", query="hybrid retrieval with RRF and pgvector")
    trace = result.trace_view
    assert trace["method"] == "R1"  # no embedder in tests
    assert 1 <= len(trace["results"]) <= MAX_RESULTS
    first = trace["results"][0]
    assert set(first) == {"chunk_id", "record_title", "section", "text", "rank", "scores"}
    assert first["rank"] == 1 and first["scores"]["rerank"] is None
    assert "this-agent#all" in result.chunk_ids
    assert result.chunk_ids == {r["chunk_id"] for r in model["results"]}
    assert "scores" not in model["results"][0]  # trace data stays out of the model's view
    assert trace["candidates_considered"] >= len(trace["results"])


@needs_db
def test_search_strips_the_owners_name(ctx):
    result, model = call(ctx, "search_portfolio", query="Sarah Halevy pgvector")
    assert model["query_used"] == "pgvector" == result.trace_view["query_used"]


@needs_db
def test_types_keep_only_records_of_those_types(ctx):
    result, _ = call(ctx, "search_portfolio", query="Python", types=["skills"])
    assert result.chunk_ids and all(c.startswith("skills#") for c in result.chunk_ids)


@needs_db
def test_no_match_tells_the_model_to_say_so(ctx):
    _, model = call(ctx, "search_portfolio", query="zzqx")
    assert model["results"] == [] and "no information" in model["note"]


@needs_db
def test_get_project_returns_the_whole_record(ctx):
    result, model = call(ctx, "get_project", id="git-mcp-server")
    assert [c["chunk_id"] for c in model["chunks"]] == ["git-mcp-server#all"]
    assert model["chunks"][0]["record_title"].startswith("grounded-git-mcp")
    assert result.chunk_ids == {"git-mcp-server#all"}


@needs_db
def test_get_project_accepts_only_project_and_role_ids(ctx):
    enum = GET_PROJECT.schema(ctx)["function"]["parameters"]["properties"]["id"]["enum"]
    assert "this-agent" in enum and "ainsof-capital" in enum
    assert "faq" not in enum and "skills" not in enum
    for bad in ("faq", "made-up-project"):
        assert REGISTRY.call("get_project", json.dumps({"id": bad}), ctx).error == "invalid_args"
