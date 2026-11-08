"""The two read tools over the knowledge base: search_portfolio and get_project.

docs/06-agent-design.md, section 3, and the search_portfolio contract in
docs/04-retrieval-design.md, section 8: at most 5 chunks and 3,000 tokens per call, each with
the chunk_id the answer cites and the scores the trace panel shows.

Retrieval is the configuration M3 chose: R3 (ADR-0011) with e5-small (ADR-0012) and Q1 with
the owner's name stripped (ADR-0013), then R4 (ADR-0014). `method` in the trace is the one that
ordered the results: R3 when the reranker is off or failed, and `rerank.fallback` says why.
Without an embedder (tests, or before the embedding migration), the search runs R1 alone and
says so in the trace, rather than failing.
"""

import json
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

import psycopg
from psycopg import sql
from pydantic import BaseModel, ConfigDict, Field

from portfolio_agent.ingest import Doc, count_tokens
from portfolio_agent.retrieval import hybrid, lexical
from portfolio_agent.retrieval.lexical import CANDIDATES, Hit
from portfolio_agent.retrieval.query import name_pattern, owner_names, strip_names
from portfolio_agent.retrieval.rerank import Quota, Ranker, rerank
from portfolio_agent.tools.registry import Tool, ToolResult

MAX_RESULTS = 5
MAX_TOKENS = 3000
RecordType = Literal["project", "experience", "skills", "education", "profile", "faq"]


class Embedder(Protocol):
    def embed_query(self, text: str) -> Sequence[float]: ...


@dataclass(frozen=True)
class Record:
    id: str
    type: str
    title: str


@dataclass
class PortfolioContext:
    conn: psycopg.Connection
    records: dict[str, Record]
    names: tuple[str, ...]
    embedder: Embedder | None = None
    table: str = "chunks"
    ranker: Ranker | None = None
    quota: Quota | None = None
    question: str = ""  # the visitor's own words, which the reranker reads with the query

    @classmethod
    def from_docs(cls, conn: psycopg.Connection, docs: Sequence[Doc], **kw) -> "PortfolioContext":
        records = {}
        for d in docs:
            title = getattr(d.record, "title", None)
            records[d.record.id] = Record(
                d.record.id, d.record.type, title.en if title else d.record.id
            )
        return cls(conn, records, owner_names(d.record for d in docs), **kw)

    def project_ids(self) -> list[str]:
        """What get_project accepts: projects and roles, the records with a full story."""
        return sorted(r.id for r in self.records.values() if r.type in ("project", "experience"))


def _section(chunk_id: str) -> str:
    section = chunk_id.partition("#")[2]
    return "Whole record" if section == "all" else section


EXCERPT = 140


def _excerpt(text: str) -> str:
    """The start of a chunk on one line, without Markdown marks."""
    flat = " ".join(re.sub(r"[#*_>`|]+", " ", text).split())
    return flat if len(flat) <= EXCERPT else flat[:EXCERPT].rsplit(" ", 1)[0] + "…"


def _title(hit: Hit, ctx: PortfolioContext) -> str:
    record = ctx.records.get(hit.record_id)
    return record.title if record else hit.record_id


def _view(hit: Hit, ctx: PortfolioContext) -> dict:
    return {
        "chunk_id": hit.id,
        "record_title": _title(hit, ctx),
        "section": _section(hit.id),
        "text": hit.text,
    }


def _within_budget(hits: Sequence[Hit]) -> list[Hit]:
    """Best first, until the next one would pass the budget. A chunk is never cut, because a
    cut chunk would be cited for text the model never read. The first always stays."""
    kept, used = [], 0
    for hit in hits[:MAX_RESULTS]:
        tokens = count_tokens(hit.text)
        if kept and used + tokens > MAX_TOKENS:
            break
        kept.append(hit)
        used += tokens
    return kept


class SearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=200)
    types: list[RecordType] | None = None


def search_portfolio(args: SearchArgs, ctx: PortfolioContext) -> ToolResult:
    query = strip_names(args.query, name_pattern(ctx.names))
    timings: dict[str, int] = {}
    if ctx.embedder is not None:
        started = time.perf_counter()
        vector = ctx.embedder.embed_query(query)
        timings["embed"] = round((time.perf_counter() - started) * 1000)
        hits = hybrid.search(ctx.conn, query, vector, CANDIDATES, ctx.table, timings)
        method = "R3"
    else:
        started = time.perf_counter()
        hits = lexical.search(ctx.conn, query, CANDIDATES, ctx.table)
        timings["lexical"] = round((time.perf_counter() - started) * 1000)
        hits = [Hit(h.id, h.record_id, h.sections, h.text,
                    {"lexical": h.scores.get("rrf"), "vector": None, "rrf": h.scores.get("rrf")})
                for h in hits]
        method = "R1"
    considered = len(hits)
    ranked = hits
    if args.types:
        wanted = set(args.types)
        hits = [h for h in hits
                if (r := ctx.records.get(h.record_id)) is not None and r.type in wanted]
    reranked = None
    if method == "R3" and ctx.ranker is not None and ctx.quota is not None and len(hits) > 1:
        started = time.perf_counter()
        outcome = rerank(hits, ctx.question or query, query, ctx.ranker, ctx.quota)
        timings["rerank"] = round((time.perf_counter() - started) * 1000)
        hits = outcome.hits
        reranked = {"model": ctx.ranker.name, "tokens": outcome.tokens,
                    "fallback": outcome.fallback}
        if outcome.fallback is None:
            method = "R4"
    order = {h.id: h.scores["rerank"] for h in hits if "rerank" in h.scores}
    kept = _within_budget(hits)
    views = [_view(h, ctx) for h in kept]
    chosen = {h.id for h in kept}
    trace = {
        "query_used": query,
        "method": method,
        "rerank": reranked,
        "results": [
            {**v, "rank": i, "scores": {**h.scores, "rerank": order.get(h.id)}}
            for i, (v, h) in enumerate(zip(views, kept, strict=True), start=1)
        ],
        "candidates_considered": considered,
        # Every candidate in fused order, for the trace panel's table (US-4.2): the scores of
        # each method, and which ones went to the model. A short excerpt, not the whole chunk.
        "candidates": [
            {"chunk_id": h.id, "record_title": _title(h, ctx), "excerpt": _excerpt(h.text),
             "scores": {**h.scores, "rerank": order.get(h.id)}, "selected": h.id in chosen}
            for h in ranked
        ],
        "latency_ms": timings,
    }
    model = {"query_used": query, "results": views}
    if not views:
        model["note"] = "No matching chunks. Say the portfolio has no information on this."
    return ToolResult(_json(model), trace, frozenset(h.id for h in kept))


class ProjectArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)


def get_project(args: ProjectArgs, ctx: PortfolioContext) -> ToolResult:
    rows = ctx.conn.execute(
        sql.SQL("select id, record_id, sections, text from {} where record_id = %s order by id")
        .format(sql.Identifier(ctx.table)),
        (args.id,),
    ).fetchall()
    hits = [Hit(r[0], r[1], tuple(r[2]), r[3]) for r in rows]
    views = [_view(h, ctx) for h in hits]
    trace = {"record_id": args.id, "chunks": [v["chunk_id"] for v in views]}
    return ToolResult(_json({"record_id": args.id, "chunks": views}), trace,
                      frozenset(h.id for h in hits))


def _json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False)


SEARCH = Tool(
    name="search_portfolio",
    description=(
        "Search Sarah's portfolio. Write the query in English with explicit technical terms, "
        "and replace pronouns from the conversation with the project name."
    ),
    params=SearchArgs,
    handler=search_portfolio,
)

GET_PROJECT = Tool(
    name="get_project",
    description="Get the full record of one project or role by id.",
    params=ProjectArgs,
    handler=get_project,
    schema_extra=lambda ctx: {"id": {"enum": ctx.project_ids()}},
)
