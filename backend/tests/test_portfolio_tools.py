"""search_portfolio and get_project on the real knowledge base, chunked as C4 (ADR-0010).
The database tests run only when TEST_DATABASE_URL is set (CI, or local)."""

import json
import os

import psycopg
import pytest

from portfolio_agent import migrate
from portfolio_agent.ingest import chunk, load, upsert
from portfolio_agent.providers.openai_compat import ProviderError
from portfolio_agent.retrieval.lexical import Hit
from portfolio_agent.retrieval.rerank import Ranking
from portfolio_agent.tools import portfolio
from portfolio_agent.tools.portfolio import (
    GET_PROJECT,
    MAX_RESULTS,
    MAX_TOKENS,
    SEARCH,
    PortfolioContext,
    Record,
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


@pytest.mark.parametrize(
    ("question", "title"),
    [
        ("מה היא בנתה?", "זמן תגובה"),
        ("מה היא בנתה עם Kafka ו-CLIP embeddings?", "זמן תגובה"),
        ("What did she build?", "Latency"),
        ("", "Latency"),
    ],
)
def test_a_project_is_named_in_the_language_of_the_question(question, title):
    records = {"r1": Record("r1", "project", "Latency", "זמן תגובה")}
    ctx = PortfolioContext(None, records, (), question=question)
    assert portfolio._title(hit(1, 1), ctx) == title


def test_a_record_with_no_hebrew_title_keeps_its_english_one():
    ctx = PortfolioContext(None, {"r1": Record("r1", "project", "Latency")}, (), question="מה?")
    assert portfolio._title(hit(1, 1), ctx) == "Latency"


class Embedder:
    def embed_query(self, text):
        return [0.0]


class Ranker:
    name = "groq/m"

    def __init__(self, answer):
        self.answer = answer
        self.got = None

    def rank(self, question, query, hits):
        self.got = (question, query, [h.id for h in hits])
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


class Quota:
    def closed(self):
        return {}

    def close(self, model, until):
        raise AssertionError("not expected")

    def spend(self, model, tokens):
        pass


def fused(i):
    return Hit(f"r{i}#all", f"r{i}", ("all",), "text", {"lexical": 0.1, "vector": 0.2, "rrf": 0.3})


@pytest.fixture
def searched(monkeypatch):
    """search_portfolio on n fused hits, without a database."""

    def run(ranker, n=4, **args):
        def search(conn, query, vector, k, table, timings, wanted=None):
            hits = [fused(i) for i in range(n)]
            return [h for h in hits if wanted is None or h.record_id in wanted]

        monkeypatch.setattr(portfolio.hybrid, "search", search)
        records = {f"r{i}": Record(f"r{i}", "project" if i % 2 else "faq", f"R{i}")
                   for i in range(4)}
        ctx = PortfolioContext(None, records, (), embedder=Embedder(), ranker=ranker, quota=Quota(),
                               question="the visitor's words")
        return portfolio.search_portfolio(portfolio.SearchArgs(query="q", **args), ctx)
    return run


def test_r4_orders_the_results_and_the_trace_shows_both_orders(searched):
    ranker = Ranker(Ranking(["r2#all", "r0#all", "r3#all", "r1#all"], 2300))
    trace = searched(ranker).trace_view
    assert ranker.got[0] == "the visitor's words"
    assert trace["method"] == "R4"
    assert trace["rerank"] == {"model": "groq/m", "tokens": 2300, "fallback": None}
    assert [r["chunk_id"] for r in trace["results"]][:2] == ["r2#all", "r0#all"]
    assert [r["rank"] for r in trace["results"]] == [1, 2, 3, 4]
    assert trace["results"][0]["scores"]["rerank"] == 1
    # the panel's table stays in fused order, with the model's place beside each
    assert [c["chunk_id"] for c in trace["candidates"]] == [f"r{i}#all" for i in range(4)]
    assert [c["scores"]["rerank"] for c in trace["candidates"]] == [2, 4, 1, 3]
    assert "rerank" in trace["latency_ms"]


def test_a_failed_rerank_is_an_r3_search_that_says_why(searched):
    trace = searched(Ranker(ProviderError("unavailable", "x"))).trace_view
    assert trace["method"] == "R3" and trace["rerank"]["fallback"] == "unavailable"
    assert [r["chunk_id"] for r in trace["results"]] == [f"r{i}#all" for i in range(4)]
    assert all(r["scores"]["rerank"] is None for r in trace["results"])


def test_without_a_ranker_the_search_is_r3(searched):
    trace = searched(None).trace_view
    assert trace["method"] == "R3" and trace["rerank"] is None


def test_the_type_filter_runs_first_so_the_model_reads_only_what_can_be_returned(searched):
    ranker = Ranker(Ranking(["r3#all", "r1#all"], 2300))
    trace = searched(ranker, types=["project"]).trace_view
    assert ranker.got[2] == ["r1#all", "r3#all"]
    assert [r["chunk_id"] for r in trace["results"]] == ["r3#all", "r1#all"]


def test_one_candidate_needs_no_ranking(searched):
    ranker = Ranker(Ranking(["r0#all"], 2300))
    trace = searched(ranker, n=1).trace_view
    assert ranker.got is None and trace["method"] == "R3" and trace["rerank"] is None


def offered_after(monkeypatch, *hits):
    monkeypatch.setattr(portfolio.hybrid, "search", lambda *a, **k: list(hits))
    records = {h.record_id: Record(h.record_id, "project", h.record_id) for h in hits}
    ctx = PortfolioContext(None, records, (), embedder=Embedder())
    before = [s["function"]["name"] for s in REGISTRY.schemas(ctx)]
    portfolio.search_portfolio(portfolio.SearchArgs(query="q"), ctx)
    return before, [s["function"]["name"] for s in REGISTRY.schemas(ctx)]


def test_after_a_whole_record_get_project_is_not_offered(monkeypatch):
    before, after = offered_after(monkeypatch, fused(1))
    assert before == ["search_portfolio", "get_project"]
    assert after == ["search_portfolio"]


def test_after_only_parts_of_records_get_project_is_still_offered(monkeypatch):
    part = Hit("r1#decisions", "r1", ("decisions",), "text", {"lexical": 0.1, "rrf": 0.3})
    _, after = offered_after(monkeypatch, part)
    assert after == ["search_portfolio", "get_project"]


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
    # the trace panel's table: every candidate in fused order, the chosen ones marked
    candidates = trace["candidates"]
    assert len(candidates) == trace["candidates_considered"]
    assert [c["chunk_id"] for c in candidates if c["selected"]] == \
        [r["chunk_id"] for r in trace["results"]]
    assert all(len(c["excerpt"]) <= 141 and "\n" not in c["excerpt"] for c in candidates)
    assert all(not c["excerpt"].startswith("#") for c in candidates)
    assert "candidates" not in model  # the model reads only what was chosen


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


class FakeEmbedder:
    """Deterministic 384-dimension vectors: one axis per known word, so similar texts are close.
    Enough to exercise R3 and ingest without the 130 MB model."""

    WORDS = ["approval", "agent", "mcp", "git", "retrieval", "hybrid", "pgvector", "translation"]

    def __init__(self):
        self.passages = 0

    def _vec(self, text):
        t = text.lower()
        v = [float(t.count(w)) for w in self.WORDS] + [0.0] * (384 - len(self.WORDS))
        v[-1] = 0.1  # never all zero
        n = sum(x * x for x in v) ** 0.5
        return [x / n for x in v]

    def embed_query(self, text):
        return self._vec(text)

    def embed_passages(self, texts):
        self.passages += len(texts)
        return [self._vec(t) for t in texts]


@needs_db
def test_embed_missing_embeds_new_and_changed_chunks_only(docs):
    from dataclasses import replace

    from portfolio_agent.ingest import embed_missing

    chunks = chunk(docs, "C4")
    migrate.run(DB_URL)
    with psycopg.connect(DB_URL, autocommit=True) as conn:
        conn.execute("create temp table e (like chunks including all)")
        try:
            fake = FakeEmbedder()
            upsert(conn, chunks, "e")
            assert embed_missing(conn, chunks, fake, "e") == len(chunks)
            assert embed_missing(conn, chunks, fake, "e") == 0  # nothing left to embed
            changed = [replace(chunks[0], text=chunks[0].text + " More.")] + chunks[1:]
            upsert(conn, changed, "e")
            assert embed_missing(conn, changed, fake, "e") == 1  # the changed one lost its vector
            empty = conn.execute("select count(*) from e where embedding is null").fetchone()[0]
            assert empty == 0
        finally:
            conn.execute("drop table e")


@needs_db
def test_with_an_embedder_search_runs_r3_and_reports_every_timing(docs):
    from portfolio_agent.ingest import embed_missing

    migrate.run(DB_URL)
    with psycopg.connect(DB_URL, autocommit=True) as conn:
        conn.execute("create temp table r (like chunks including all)")
        try:
            chunks = chunk(docs, "C4")
            fake = FakeEmbedder()
            upsert(conn, chunks, "r")
            embed_missing(conn, chunks, fake, "r")
            ctx = PortfolioContext.from_docs(conn, docs, table="r", embedder=fake)
            result, _ = call(ctx, "search_portfolio", query="human approval for git mcp agent")
            trace = result.trace_view
            assert trace["method"] == "R3"
            assert set(trace["latency_ms"]) == {"embed", "lexical", "vector", "fusion"}
            first = trace["results"][0]
            assert first["chunk_id"] == "git-mcp-server#all"
            assert first["scores"]["vector"] is not None and first["scores"]["lexical"] is not None
        finally:
            conn.execute("drop table r")


def sized(i, tokens):
    return Hit(f"r{i}#all", f"r{i}", ("all",), "w " * tokens,
               {"lexical": 0.1, "vector": 0.2, "rrf": 0.3})


def turn(monkeypatch, ranker=None):
    """One turn's context, whose searches return whatever `results` holds at the time."""
    results: list[Hit] = []
    monkeypatch.setattr(portfolio.hybrid, "search", lambda *a, **k: list(results))
    records = {f"r{i}": Record(f"r{i}", "project", f"R{i}") for i in range(10)}
    ctx = PortfolioContext(None, records, (), embedder=Embedder(), ranker=ranker, quota=Quota())

    def search(*hits):
        results[:] = hits
        out = portfolio.search_portfolio(portfolio.SearchArgs(query="q"), ctx)
        return json.loads(out.model_view), out
    return ctx, search


def test_a_chunk_already_given_this_turn_is_named_not_sent_again(monkeypatch):
    ctx, search = turn(monkeypatch)
    search(sized(1, 100), sized(2, 100))
    body, out = search(sized(2, 100), sized(3, 100))
    assert [r["chunk_id"] for r in body["results"]] == ["r3#all"]
    assert body["already_given"] == ["r2#all"]
    assert "r2#all" in out.chunk_ids  # still citable
    assert ctx.sent_tokens == 300


def test_only_repeats_tell_the_model_to_answer_from_them(monkeypatch):
    _, search = turn(monkeypatch)
    search(sized(1, 100))
    body, _ = search(sized(1, 100))
    assert body["results"] == [] and body["already_given"] == ["r1#all"]
    assert "already given" in body["note"]


def test_all_searches_in_a_turn_share_one_budget(monkeypatch):
    ctx, search = turn(monkeypatch)
    search(sized(1, 2400))
    body, _ = search(sized(2, 400), sized(3, 400))  # 600 left: only one fits
    assert [r["chunk_id"] for r in body["results"]] == ["r2#all"]
    assert ctx.sent_tokens == 2800
    body, _ = search(sized(4, 400))
    assert body["results"] == [] and "limit" in body["note"]
    assert ctx.sent_tokens <= portfolio.TURN_MAX_TOKENS


def test_the_first_result_of_the_turn_stays_even_when_larger_than_the_budget(monkeypatch):
    _, search = turn(monkeypatch)
    body, _ = search(sized(1, 4000))
    assert [r["chunk_id"] for r in body["results"]] == ["r1#all"]


def test_only_the_first_search_of_a_turn_is_reranked(monkeypatch):
    ranker = Ranker(Ranking(["r2#all", "r1#all"], 2300))
    _, search = turn(monkeypatch, ranker)
    _, first = search(sized(1, 10), sized(2, 10))
    assert first.trace_view["method"] == "R4"
    ranker.got = None
    _, second = search(sized(3, 10), sized(4, 10))
    assert ranker.got is None
    assert second.trace_view["method"] == "R3"
    assert second.trace_view["rerank"]["fallback"] == "later_search"
