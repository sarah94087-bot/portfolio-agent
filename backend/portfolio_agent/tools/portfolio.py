"""The two read tools over the knowledge base: search_portfolio and get_project.

docs/06-agent-design.md, section 3, and the search_portfolio contract in
docs/04-retrieval-design.md, section 8: at most 5 chunks and 3,000 tokens per call, each with
the chunk_id the answer cites and the scores the trace panel shows.

Retrieval is the configuration M3 chose: R3 (ADR-0011) with e5-small (ADR-0012) and Q1 with
the owner's name stripped (ADR-0013). R4 is still being evaluated, so `rerank` is null. Without
an embedder (tests, or before the embedding migration), the search runs R1 alone and says so in
the trace, rather than failing.
"""

import json
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


def _view(hit: Hit, ctx: PortfolioContext) -> dict:
    record = ctx.records.get(hit.record_id)
    return {
        "chunk_id": hit.id,
        "record_title": record.title if record else hit.record_id,
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
    if args.types:
        wanted = set(args.types)
        hits = [h for h in hits
                if (r := ctx.records.get(h.record_id)) is not None and r.type in wanted]
    kept = _within_budget(hits)
    views = [_view(h, ctx) for h in kept]
    trace = {
        "query_used": query,
        "method": method,
        "results": [
            {**v, "rank": i, "scores": {**h.scores, "rerank": None}}
            for i, (v, h) in enumerate(zip(views, kept, strict=True), start=1)
        ],
        "candidates_considered": considered,
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
