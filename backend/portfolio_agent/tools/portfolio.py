"""The two read tools over the knowledge base: search_portfolio and get_project.

docs/06-agent-design.md, section 3, and the search_portfolio contract in
docs/04-retrieval-design.md, section 8: at most 5 chunks and 3,000 tokens per call, each with
the chunk_id the answer cites and the scores the trace panel shows.

A turn has the same 3,000 tokens for all its tool results together (docs/06-agent-design.md,
section 5), not 3,000 for each call: the model may search several times, and every result stays
in the next round's request. Without this cap three searches made the answer round larger than
any model's minute (T1 runs 15 and 16, case d2-007). A chunk this turn already returned is not
sent again; its id is listed, so it can still be cited. Only the turn's first search is
reranked: the reranker spends the answer model's own minute (ADR-0014), and the answer needs it.

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
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import psycopg
from psycopg import sql
from pydantic import BaseModel, ConfigDict, Field

from portfolio_agent.agent.guard import language
from portfolio_agent.ingest import Doc, count_tokens
from portfolio_agent.retrieval import hybrid, lexical
from portfolio_agent.retrieval.lexical import CANDIDATES, Hit
from portfolio_agent.retrieval.query import name_pattern, owner_names, strip_names
from portfolio_agent.retrieval.rerank import Quota, Ranker, rerank
from portfolio_agent.tools.registry import Tool, ToolResult

MAX_RESULTS = 5
MAX_TOKENS = 3000
TURN_MAX_TOKENS = MAX_TOKENS  # every tool result in one turn together (docs/06, section 5)
RecordType = Literal["project", "experience", "skills", "education", "profile", "faq"]


class Embedder(Protocol):
    def embed_query(self, text: str) -> Sequence[float]: ...


@dataclass(frozen=True)
class Record:
    id: str
    type: str
    title: str
    title_he: str | None = None


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
    # A search this turn returned at least one whole record. Then get_project is not offered:
    # asking for the record again costs a round against Groq's 8,000 tokens a minute. The model
    # can still reach another project by searching for it. The tool is removed, and its enum
    # is not narrowed, since Groq answers 400 to a tool call outside the schema's enum.
    has_whole_record: bool = False
    job: Any = None  # tools/job_match.py, JobTool: set when this turn may run a job match
    cards: Any = None  # tools/cards.py, CardTool: set when this turn may show cards
    retrieved: set[str] = field(default_factory=set)  # records found in this conversation
    sent: set[str] = field(default_factory=set)  # chunk ids the model was given this turn
    sent_tokens: int = 0  # their size, against TURN_MAX_TOKENS
    searches: int = 0  # search_portfolio calls this turn; only the first is reranked

    @classmethod
    def from_docs(cls, conn: psycopg.Connection, docs: Sequence[Doc], **kw) -> "PortfolioContext":
        records = {}
        for d in docs:
            title = getattr(d.record, "title", None)
            records[d.record.id] = Record(
                d.record.id, d.record.type, title.en if title else d.record.id,
                getattr(title, "he", None),
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
    """The name the model copies into its answer, so in the language it will answer in: that of
    the visitor's message. A Hebrew sentence full of English terms counts as "mixed"."""
    record = ctx.records.get(hit.record_id)
    if record is None:
        return hit.record_id
    hebrew = language(ctx.question) in ("he", "mixed")
    return (record.title_he if hebrew else None) or record.title


def _view(hit: Hit, ctx: PortfolioContext) -> dict:
    return {
        "chunk_id": hit.id,
        "record_title": _title(hit, ctx),
        "section": _section(hit.id),
        "text": hit.text,
    }


def _within_budget(hits: Sequence[Hit], budget: int = MAX_TOKENS,
                   keep_first: bool = True) -> list[Hit]:
    """Best first, until the next one would pass the budget. A chunk is never cut, because a
    cut chunk would be cited for text the model never read. The first stays when keep_first
    (the turn's first results): a search that returns nothing helps nobody."""
    kept, used = [], 0
    for hit in hits[:MAX_RESULTS]:
        tokens = count_tokens(hit.text)
        if used + tokens > budget and (kept or not keep_first):
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
    # Inside the search, not after it: a type with few chunks rarely reaches the overall top
    # candidates, and filtering those afterwards would leave nothing.
    records = None
    if args.types:
        wanted = set(args.types)
        records = [r.id for r in ctx.records.values() if r.type in wanted]
    if ctx.embedder is not None:
        started = time.perf_counter()
        vector = ctx.embedder.embed_query(query)
        timings["embed"] = round((time.perf_counter() - started) * 1000)
        hits = hybrid.search(ctx.conn, query, vector, CANDIDATES, ctx.table, timings, records)
        method = "R3"
    else:
        started = time.perf_counter()
        hits = lexical.search(ctx.conn, query, CANDIDATES, ctx.table, records)
        timings["lexical"] = round((time.perf_counter() - started) * 1000)
        hits = [Hit(h.id, h.record_id, h.sections, h.text,
                    {"lexical": h.scores.get("rrf"), "vector": None, "rrf": h.scores.get("rrf")})
                for h in hits]
        method = "R1"
    considered = len(hits)
    ranked = hits
    reranked = None
    can_rerank = (method == "R3" and ctx.ranker is not None and ctx.quota is not None
                  and len(hits) > 1)
    first_search = ctx.searches == 0
    ctx.searches += 1
    if can_rerank and not first_search:
        reranked = {"model": ctx.ranker.name, "tokens": 0, "fallback": "later_search"}
    elif can_rerank:
        started = time.perf_counter()
        outcome = rerank(hits, ctx.question or query, query, ctx.ranker, ctx.quota)
        timings["rerank"] = round((time.perf_counter() - started) * 1000)
        hits = outcome.hits
        reranked = {"model": ctx.ranker.name, "tokens": outcome.tokens,
                    "fallback": outcome.fallback}
        if outcome.fallback is None:
            method = "R4"
    order = {h.id: h.scores["rerank"] for h in hits if "rerank" in h.scores}
    repeated = [h.id for h in hits[:MAX_RESULTS] if h.id in ctx.sent]
    fresh = [h for h in hits if h.id not in ctx.sent]
    left = TURN_MAX_TOKENS - ctx.sent_tokens
    kept = _within_budget(fresh, min(MAX_TOKENS, left), keep_first=not ctx.sent)
    over_budget = bool(fresh) and not kept
    _count_sent(kept, ctx)
    ctx.has_whole_record = ctx.has_whole_record or any(h.id.endswith("#all") for h in kept)
    ctx.retrieved.update(h.record_id for h in kept)
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
        "already_given": repeated,
        "turn_tokens": ctx.sent_tokens,
        # Every candidate in fused order, for the trace panel's table (US-4.2): the scores of
        # each method, and which ones went to the model. A short excerpt, not the whole chunk.
        "candidates": [
            {"chunk_id": h.id, "record_title": _title(h, ctx), "excerpt": _excerpt(h.text),
             "scores": {**h.scores, "rerank": order.get(h.id)}, "selected": h.id in chosen}
            for h in ranked
        ],
        "latency_ms": timings,
    }
    model: dict[str, Any] = {"query_used": query, "results": views}
    if repeated:
        model["already_given"] = repeated
    if over_budget:
        model["note"] = ("The tool results for this question have reached their limit. Answer "
                         "from the results already given, and cite them.")
    elif not views and repeated:
        model["note"] = "Only chunks already given this turn match. Answer from them."
    elif not views:
        model["note"] = "No matching chunks. Say the portfolio has no information on this."
    return ToolResult(_json(model), trace, frozenset(h.id for h in kept) | frozenset(repeated))


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
    ctx.retrieved.update(h.record_id for h in hits)
    # The whole record is sent even past the turn's budget: a part of it would be cited as if
    # it were all. Chunks already given this turn are named, not repeated.
    repeated = [h.id for h in hits if h.id in ctx.sent]
    hits = [h for h in hits if h.id not in ctx.sent]
    _count_sent(hits, ctx)
    views = [_view(h, ctx) for h in hits]
    trace = {"record_id": args.id, "chunks": [v["chunk_id"] for v in views],
             "already_given": repeated}
    body: dict[str, Any] = {"record_id": args.id, "chunks": views}
    if repeated:
        body["already_given"] = repeated
    return ToolResult(_json(body), trace, frozenset(h.id for h in hits) | frozenset(repeated))


def _count_sent(hits: Sequence[Hit], ctx: PortfolioContext) -> None:
    ctx.sent.update(h.id for h in hits)
    ctx.sent_tokens += sum(count_tokens(h.text) for h in hits)


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
    offered=lambda ctx: not ctx.has_whole_record,
)
