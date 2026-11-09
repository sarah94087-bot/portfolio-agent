"""POST /api/chat: one visitor message in, one streamed answer out (docs/05-architecture.md,
sections 4 to 6).

The order of one request: input checks, a resent message answered from the database, the
conversation and its history, the agent loop with its events streamed as they happen, then the
answer saved with its steps, and `sources`, `usage` and `done` last. Every failure ends in an
`error` event with a fixed code, so the UI picks a screen by code, never by text.

A resent message (same idempotency_key, US-10.5) is answered from the database: the stored
answer is replayed through the citation filter, with no model call and no quota spent.

Who asks is the signed visitor cookie (guards/visitor.py), renewed on every request. Limits
are counted in quota_counters after the replay check, so a resent message is free, and before
the message is saved, so a refused one leaves nothing behind (guards/quotas.py).

A first question already answered under the same prompt and knowledge base is served from
the response cache (db/cache.py): no model call, and it still works when every model is down.

A job posting sent from the composer's job mode skips the agent loop and goes straight to the
match_job pipeline (ADR-0016), so that only the extraction stage reads it. It counts as 3
messages, may be 8,000 characters, and its report comes as a `card` event.

Every request ends with one trace to Langfuse (tracing.py), sent after `done`.
"""

import asyncio
import contextlib
import logging
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cache
from typing import Any, Literal
from uuid import UUID

import httpx
import psycopg
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from portfolio_agent import sse, tracing
from portfolio_agent.agent import prompt
from portfolio_agent.agent.loop import run_turn
from portfolio_agent.agent.transcript import Transcript, replay
from portfolio_agent.config import Settings
from portfolio_agent.db import cache as response_cache
from portfolio_agent.db import conversations as db
from portfolio_agent.guards import visitor
from portfolio_agent.guards.quotas import Denied, Limits, ProviderQuota, admit
from portfolio_agent.ingest import Doc, load
from portfolio_agent.providers.base import NeedsFallback
from portfolio_agent.providers.openai_compat import ProviderError
from portfolio_agent.providers.router import AllModelsFailed, from_env
from portfolio_agent.retrieval import embedder, rerank
from portfolio_agent.tools import job_match, job_report
from portfolio_agent.tools.job_match import MATCH_JOB, JobResult, JobRuntime, JobTool
from portfolio_agent.tools.portfolio import GET_PROJECT, SEARCH, PortfolioContext
from portfolio_agent.tools.registry import Registry

log = logging.getLogger(__name__)
router = APIRouter()

REGISTRY = Registry.of([SEARCH, GET_PROJECT, MATCH_JOB])
JOB_CHARS = 8000  # docs/09-security-privacy.md, section 4
JOB_COST = 3


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=20_000)  # the 1,000 rule is an SSE error
    conversation_id: UUID | None = None
    company_slug: str | None = Field(default=None, max_length=64)
    idempotency_key: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    # The page's language: record titles in `sources` come in it. The answer's own language
    # follows the question (US-11.1), not this.
    lang: Literal["he", "en"] = "en"
    mode: Literal["question", "job"] = "question"  # "job": the composer's paste-a-posting mode


@cache
def _router():
    return from_env(httpx.AsyncClient())


@cache
def _http() -> httpx.AsyncClient:
    return httpx.AsyncClient()


@cache
def _ranker() -> rerank.GroqRanker | None:
    return rerank.from_env(httpx.Client())


@cache
def _docs() -> list[Doc]:
    return load()


@dataclass
class Deps:
    """What a request needs from outside. Tests swap these for fakes."""

    database_url: Callable[[], str | None] = lambda: Settings.from_env().database_url
    provider: Callable[[ProviderQuota], Any] = lambda quota: _router().for_turn(quota)
    embedder: Callable[[], Any] = embedder.from_env
    ranker: Callable[[], Any] = _ranker  # None without a Groq key: the search stays R3
    docs: Callable[[], list[Doc]] = _docs
    agent_enabled: Callable[[], bool] = lambda: Settings.from_env().agent_enabled
    limits: Callable[[], Limits] = Limits.from_env
    tracer: Callable[[], Any] = tracing.Exporter.from_env  # None without Langfuse keys
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    table: str = "chunks"
    use_cache: bool = True  # evals turn it off: they measure a fresh answer


DEPS = Deps()


@dataclass(frozen=True)
class Caller:
    visitor_id: str
    ip: str  # hashed before it is stored or counted; never sent to a provider
    site: str = ""  # this site's address, for the link in a downloaded report


@router.post("/api/chat")
async def chat(req: ChatRequest, request: Request) -> StreamingResponse:
    cookie = request.cookies.get(visitor.COOKIE)
    visitor_id = visitor.read_cookie(cookie)
    if visitor_id is None:  # new, expired, or not ours
        visitor_id, cookie = visitor.new_cookie()
    ip = visitor.client_ip(dict(request.headers), request.client and request.client.host)
    response = StreamingResponse(
        _frames(req, DEPS, Caller(visitor_id, ip, _site(request))),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
    https = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    response.set_cookie(visitor.COOKIE, cookie, max_age=visitor.MAX_AGE, httponly=True,
                        secure=https, samesite="lax", path="/")  # 30 days from the last use
    return response


def _site(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    return f"{proto}://{host}"


@router.get("/api/job-match/{message_id}")
def job_report_of(message_id: UUID, request: Request, lang: Literal["he", "en"] = "en") -> Response:
    """A report the visitor made, for the link in the downloaded file (US-5.3). Only with the
    cookie it was made under, and the same 404 for anyone else's or for one that is gone."""
    visitor_id = visitor.read_cookie(request.cookies.get(visitor.COOKIE))
    url = DEPS.database_url()
    if visitor_id is None or not url:
        return Response(status_code=404)
    with psycopg.connect(url, autocommit=True, connect_timeout=5) as conn:
        stored = db.find_report(conn, message_id, visitor_id)
        if stored is None:
            return Response(status_code=404)
        card = stored.meta["card"]
        rows = _source_rows(conn, job_chunks(card["data"]), DEPS.docs(), lang, DEPS.table)
    markdown = _markdown(card["data"], lang, stored.created_at.date().isoformat(),
                         _report_link(_site(request), lang, message_id), rows)
    return JSONResponse({
        "conversation_id": str(stored.conversation_id), "message_id": str(message_id),
        "card": {**card, "markdown": markdown}, "sources": rows,
        "posting_chars": stored.meta.get("posting_chars"),
    }, headers={"Cache-Control": "no-store"})


@router.delete("/api/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: UUID, request: Request) -> Response:
    """The visitor deletes their conversation at once (US-12.4): 204, or 404 when it is not
    theirs or is gone already, so nobody learns which ids exist. Traces already in Langfuse go
    in the daily retention job, by the ids of its answers (retention.py)."""
    visitor_id = visitor.read_cookie(request.cookies.get(visitor.COOKIE))
    if visitor_id is None:
        return Response(status_code=404)
    url = DEPS.database_url()
    if not url:
        return Response(status_code=503)
    with psycopg.connect(url, autocommit=True, connect_timeout=5) as conn:
        deleted = db.delete_conversation(conn, conversation_id, visitor_id)
    return Response(status_code=204 if deleted else 404)


async def _frames(req: ChatRequest, deps: Deps, caller: Caller) -> AsyncIterator[str]:
    """The turn runs as a task and pushes frames; this hands them to the response as they
    come, so the first token reaches the browser while the model is still writing."""
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    task = asyncio.create_task(_turn(req, deps, caller, queue))
    while (frame := await queue.get()) is not None:
        yield frame
    await task


@dataclass
class _Out:
    queue: asyncio.Queue
    started: float = field(default_factory=time.perf_counter)
    transcript: Transcript = field(default_factory=Transcript)
    trace: tracing.Recorder = field(default_factory=tracing.Recorder)
    ttft_ms: int | None = None
    setup_ms: int | None = None  # until `meta`: the database work before the model starts
    dropped: list[str] = field(default_factory=list)
    lang: str = "en"  # the page's, for record titles

    async def emit(self, event: str, data: dict[str, Any] | None = None) -> None:
        data = data or {}
        if event == "meta" and self.setup_ms is None:
            self.setup_ms = _since(self.started)
        if event == "token" and self.ttft_ms is None:
            self.ttft_ms = round((time.perf_counter() - self.started) * 1000)
        self.transcript.record(event, data)
        self.trace.record(event, data)
        await self.queue.put(sse.encode(event, data))

    async def error(self, code: str, message: str, retryable: bool, **extra: Any) -> None:
        await self.emit("error", {"code": code, "message": message, "retryable": retryable,
                                  **extra})
        await self.emit("done")


async def _turn(req: ChatRequest, deps: Deps, caller: Caller, queue: asyncio.Queue) -> None:
    out = _Out(queue, lang=req.lang)
    try:
        await _answer(req, deps, caller, out)
    except Exception:  # anything unexpected still ends the stream with a code
        log.exception("chat turn failed")
        await out.error("internal", "Something went wrong on our side.", True)
    try:  # after done, before the stream closes (tracing.py says why)
        meta = next((d for _, e, d in out.trace.events if e == "meta"), {})
        # A posting goes to the extraction call only, so the trace gets its size, not its text.
        asked = f"[job posting, {len(req.message)} characters]" if req.mode == "job" \
            else req.message
        answer = out.transcript.card["data"]["summary"] if out.transcript.card \
            else out.transcript.text
        await tracing.export(out.trace, tracing.Turn(
            message=asked, answer=answer, dropped=out.dropped,
            conversation_id=meta.get("conversation_id"), message_id=meta.get("message_id"),
        ), deps.tracer(), _http())
    except Exception:
        log.exception("trace export failed")
    finally:
        await queue.put(None)


async def _answer(req: ChatRequest, deps: Deps, caller: Caller, out: _Out) -> None:
    if not deps.agent_enabled():
        return await out.error("provider_unavailable", "The agent is paused.", False)
    limits = deps.limits()
    is_job = req.mode == "job"
    max_chars = JOB_CHARS if is_job else limits.message_chars
    if len(req.message) > max_chars:
        return await out.error(
            "input_too_long", f"The message is longer than {max_chars} characters.", False)
    url = deps.database_url()
    if not url:
        return await out.error("internal", "No database is configured.", True)

    with psycopg.connect(url, autocommit=True, connect_timeout=5) as conn:
        stored = db.find_answer(conn, req.idempotency_key, caller.visitor_id)
        if stored:
            return await _replay(conn, stored, deps, caller, req, out)

        now = deps.now()
        # Sent before, and the stream dropped before the answer was saved: continue from the
        # saved question, so it is in the history once and the conversation counts it once.
        # The visitor's own limits still count it, since the model runs again.
        pending = db.find_question(conn, req.idempotency_key, caller.visitor_id)
        conversation_id = pending.conversation_id if pending else db.open_conversation(
            conn, req.conversation_id, req.company_slug, caller.visitor_id)
        try:
            admit(conn, visitor_id=caller.visitor_id,
                  ip_hash=visitor.ip_hash(conn, caller.ip, now.date()),
                  conversation_id=conversation_id, now=now, limits=limits,
                  cost=JOB_COST if is_job else 1, resent=pending is not None)
        except Denied as e:
            return await out.error(e.code, e.message, e.retryable, limit=e.limit,
                                   retry_after=e.retry_after)
        history = db.history(conn, conversation_id, exclude=pending and pending.message_id)
        allowed = db.retrieved_chunks(conn, conversation_id)
        if not pending:
            db.save_user(conn, conversation_id, req.message, req.idempotency_key,
                         job_posting=is_job)
        message_id = uuid.uuid4()
        if is_job:
            return await _job(conn, req, deps, caller, out, conversation_id, message_id, now,
                              limits)
        cache_key = None
        if deps.use_cache and not history:  # only a first question, from the cache
            kb = response_cache.kb_version(conn, deps.table)
            cache_key = response_cache.key(req.message, prompt.VERSION, kb)
            hit = response_cache.get(conn, cache_key, now)
            if hit:
                return await _cached(conn, hit, conversation_id, message_id, req, deps, out)
        await out.emit("meta", {"conversation_id": str(conversation_id),
                                "message_id": str(message_id),
                                "prompt_version": prompt.VERSION})

        docs = deps.docs()
        quota = ProviderQuota(conn, now, limits)
        ctx = PortfolioContext.from_docs(conn, docs, embedder=deps.embedder(), table=deps.table,
                                         ranker=deps.ranker(), quota=quota, question=req.message)
        provider = deps.provider(quota)

        async def publish(found: JobResult) -> None:
            await _send_card(_card(found), req.lang, now, message_id, caller, conn, deps, out)

        def charge() -> None:  # the message counted 1 when it came in; a job match is 3
            admit(conn, visitor_id=caller.visitor_id,
                  ip_hash=visitor.ip_hash(conn, caller.ip, now.date()),
                  conversation_id=conversation_id, now=now, limits=limits, cost=JOB_COST - 1,
                  resent=True)

        ctx.job = JobTool(JobRuntime(provider, out.emit, req.lang, quota.spend, publish, charge),
                          docs)
        try:
            result = await run_turn(
                system_prompt=prompt.system_prompt(), history=history,
                user_message=req.message, provider=provider, registry=REGISTRY, ctx=ctx,
                emit=out.emit, allowed_chunks=allowed,
            )
        except AllModelsFailed as e:
            return await out.error(e.code, "No model can answer right now.", True)
        except (NeedsFallback, ProviderError) as e:
            log.warning("turn failed: %s", e)
            return await out.error("provider_unavailable", "No model can answer right now.", True)

        switches = list(getattr(provider, "switches", []))
        meta = {
            "allowed_chunks": sorted(result.allowed_chunks), "cited": result.cited,
            "dropped": result.dropped, "blocked": result.blocked, "redacted": result.redacted,
            "language": result.language, "rounds": result.rounds,
            "hit_max_rounds": result.hit_max_rounds, "switches": switches,
        }
        if out.transcript.card:
            meta["card"] = out.transcript.card
        out.dropped = result.dropped
        model = result.models[-1] if result.models else None
        if model:  # all of the turn's tokens go to the model that finished it; a switch is rare
            # Under the router's name for it, as the provider reports a shorter one: a model
            # past its visitor share is closed by that name (quotas.ProviderQuota.closed).
            quota.spend(getattr(provider, "current", None) or model,
                        result.usage.get("input_tokens", 0) + result.usage.get("output_tokens", 0))
        if out.transcript.card:  # the tool's own model calls, spent and counted in the tool
            for key, value in ctx.job.runtime.usage.items():
                result.usage[key] = result.usage.get(key, 0) + value
        # The same message sent twice at once: the other request saved it, and that is fine.
        with contextlib.suppress(psycopg.errors.UniqueViolation):
            db.save_answer(
                conn, message_id=message_id, conversation_id=conversation_id,
                content=out.transcript.content, model=model, prompt_version=prompt.VERSION,
                usage=result.usage, meta=meta, idempotency_key=req.idempotency_key,
                steps=out.transcript.steps,
            )
        clean = not (result.blocked or switches or result.hit_max_rounds or out.transcript.card)
        if cache_key and clean and out.transcript.text.strip():
            response_cache.put(conn, cache_key, response_cache.Cached(
                content=out.transcript.content, steps=out.transcript.steps, model=model,
                allowed_chunks=meta["allowed_chunks"], created_at=now.isoformat()), now)
        await _sources(conn, _cited(out), docs, deps, out)
        # For the trace panel (US-4.3): the time before the model started, and how many
        # citations were removed and contact details hidden before the answer was shown.
        await out.emit("usage", {**result.usage, "ttft_ms": out.ttft_ms,
                                 "total_ms": _since(out.started), "setup_ms": out.setup_ms,
                                 "model": model, "fallback": bool(switches),
                                 "dropped": len(result.dropped), "redacted": result.redacted})
        await out.emit("done")


def _card(result: JobResult) -> dict[str, Any]:
    return {"kind": "job_match", "data": result.card_data}


def job_chunks(data: dict[str, Any]) -> list[str]:
    return list(job_report.numbering(data))


def _report_link(site: str, lang: str, message_id: UUID | str) -> str:
    return f"{site}/{lang}?report={message_id}"


def _titles(docs: list[Doc], lang: str) -> dict[str, str]:
    def title(d: Doc) -> str:
        t = getattr(d.record, "title", None)
        return getattr(t, lang, None) or getattr(t, "en", None) or d.record.id

    return {d.record.id: title(d) for d in docs}


def _source_rows(conn: psycopg.Connection, cited: list[str], docs: list[Doc], lang: str,
                 table: str) -> list[dict[str, Any]]:
    titles = _titles(docs, lang)
    return [{"chunk_id": cid, "record_title": titles.get(rid, rid),
             "section": cid.partition("#")[2], "text": text, "commit": commit}
            for cid, rid, text, commit in db.chunk_sources(conn, cited, table)]


def _markdown(data: dict[str, Any], lang: str, date: str, link: str,
              rows: list[dict[str, Any]]) -> str:
    sources = [(r["chunk_id"], r["record_title"]) for r in rows]
    return job_report.render(data, lang=lang, date=date, link=link, sources=sources)


async def _send_card(card: dict[str, Any], lang: str, now: datetime, message_id: UUID,
                     caller: Caller, conn: psycopg.Connection, deps: Deps, out: _Out) -> None:
    """The card goes out with its Markdown, made here so a replay gets this link and date."""
    rows = _source_rows(conn, job_chunks(card["data"]), deps.docs(), lang, deps.table)
    markdown = _markdown(card["data"], lang, now.date().isoformat(),
                         _report_link(caller.site, lang, message_id), rows)
    await out.emit("card", {**card, "markdown": markdown})


def _cited(out: _Out) -> list[str]:
    """What the answer cites and what the report cites, for the `sources` event."""
    from_card = job_chunks(out.transcript.card["data"]) if out.transcript.card else []
    return list(dict.fromkeys([*from_card, *out.transcript.cited]))


async def _job(conn: psycopg.Connection, req: ChatRequest, deps: Deps, caller: Caller, out: _Out,
               conversation_id: UUID, message_id: UUID, now: datetime, limits: Limits) -> None:
    """The composer's job mode: the pipeline with no agent loop, so the posting reaches one
    model call only (docs/07, section 2; ADR-0016). The result is kept by the posting's hash."""
    docs = deps.docs()
    meta_event = {"conversation_id": str(conversation_id), "message_id": str(message_id),
                  "prompt_version": job_match.VERSION}
    posting_chars = len(req.message)
    cache_key = None
    if deps.use_cache:
        kb = response_cache.kb_version(conn, deps.table)
        cache_key = response_cache.key(req.message, f"{job_match.VERSION}:{req.lang}", kb)
        hit = response_cache.get(conn, cache_key, now)
        if hit and hit.card:
            await out.emit("meta", {**meta_event, "cached": True, "cached_at": hit.created_at})
            for step in hit.steps:
                await out.emit("step", step)
            await _send_card(hit.card, req.lang, now, message_id, caller, conn, deps, out)
            with contextlib.suppress(psycopg.errors.UniqueViolation):
                db.save_answer(
                    conn, message_id=message_id, conversation_id=conversation_id,
                    content=hit.content, model=hit.model, prompt_version=job_match.VERSION,
                    usage={}, meta={"allowed_chunks": hit.allowed_chunks, "card": hit.card,
                                    "direct": True, "cached": True, "cached_at": hit.created_at,
                                    "posting_chars": posting_chars},
                    idempotency_key=req.idempotency_key, steps=hit.steps,
                )
            await _sources(conn, _cited(out), docs, deps, out)
            await out.emit("usage", {"input_tokens": 0, "output_tokens": 0,
                                     "total_ms": _since(out.started), "model": hit.model,
                                     "fallback": False, "cached": True})
            return await out.emit("done")

    await out.emit("meta", meta_event)
    quota = ProviderQuota(conn, now, limits)
    ctx = PortfolioContext.from_docs(conn, docs, embedder=deps.embedder(), table=deps.table,
                                     ranker=None, quota=quota, question="")
    provider = deps.provider(quota)
    runtime = JobRuntime(provider, out.emit, req.lang, quota.spend)
    try:
        found = await job_match.run(req.message, ctx, docs, runtime)
    except AllModelsFailed as e:
        return await out.error(e.code, "No model can answer right now.", True)
    except (NeedsFallback, ProviderError, job_match.BadOutput) as e:
        log.warning("job match failed: %s", e)
        return await out.error("provider_unavailable", "No model can answer right now.", True)

    switches = list(getattr(provider, "switches", []))
    model = runtime.models[-1] if runtime.models else None
    out.dropped = runtime.dropped
    if found is None:
        text = job_match.NO_REQUIREMENTS[req.lang]
        await out.emit("token", {"text": text})
        with contextlib.suppress(psycopg.errors.UniqueViolation):
            db.save_answer(conn, message_id=message_id, conversation_id=conversation_id,
                           content=text, model=model, prompt_version=job_match.VERSION,
                           usage=runtime.usage, meta={"allowed_chunks": [], "switches": switches},
                           idempotency_key=req.idempotency_key, steps=out.transcript.steps)
    else:
        card = _card(found)
        await _send_card(card, req.lang, now, message_id, caller, conn, deps, out)
        meta = {"allowed_chunks": found.chunk_ids, "card": card, "direct": True,
                "dropped": runtime.dropped, "switches": switches, "score": round(found.score, 3),
                "posting_chars": posting_chars}
        with contextlib.suppress(psycopg.errors.UniqueViolation):
            db.save_answer(conn, message_id=message_id, conversation_id=conversation_id,
                           content=found.summary, model=model, prompt_version=job_match.VERSION,
                           usage=runtime.usage, meta=meta, idempotency_key=req.idempotency_key,
                           steps=out.transcript.steps)
        if cache_key and not switches:
            response_cache.put(conn, cache_key, response_cache.Cached(
                content=found.summary, steps=out.transcript.steps, model=model,
                allowed_chunks=found.chunk_ids, created_at=now.isoformat(), card=card), now)
    await _sources(conn, _cited(out), docs, deps, out)
    await out.emit("usage", {**runtime.usage, "ttft_ms": None, "total_ms": _since(out.started),
                             "setup_ms": out.setup_ms, "model": model,
                             "fallback": bool(switches), "dropped": len(runtime.dropped),
                             "redacted": 0, "job_match": True})
    await out.emit("done")


async def _cached(conn: psycopg.Connection, hit: response_cache.Cached,
                  conversation_id: UUID,
                  message_id: UUID, req: ChatRequest, deps: Deps, out: _Out) -> None:
    """The original trace and answer, marked as cached, saved as this conversation's answer so
    the next turn sees it and may cite what it retrieved. No model call, no tokens."""
    await out.emit("meta", {"conversation_id": str(conversation_id),
                            "message_id": str(message_id), "prompt_version": prompt.VERSION,
                            "cached": True, "cached_at": hit.created_at})
    for step in hit.steps:
        await out.emit("step", step)
    await replay(hit.content, out.emit)
    with contextlib.suppress(psycopg.errors.UniqueViolation):
        db.save_answer(
            conn, message_id=message_id, conversation_id=conversation_id,
            content=hit.content, model=hit.model, prompt_version=prompt.VERSION, usage={},
            meta={"allowed_chunks": hit.allowed_chunks, "cited": out.transcript.cited,
                  "cached": True, "cached_at": hit.created_at},
            idempotency_key=req.idempotency_key, steps=hit.steps,
        )
    await _sources(conn, out.transcript.cited, deps.docs(), deps, out)
    await out.emit("usage", {"input_tokens": 0, "output_tokens": 0, "ttft_ms": out.ttft_ms,
                             "total_ms": _since(out.started), "model": hit.model,
                             "fallback": False, "cached": True})
    await out.emit("done")


async def _replay(conn: psycopg.Connection, stored: db.StoredAnswer, deps: Deps, caller: Caller,
                  req: ChatRequest, out: _Out) -> None:
    await out.emit("meta", {"conversation_id": str(stored.conversation_id),
                            "message_id": str(stored.id), "replay": True})
    if card := stored.meta.get("card"):
        await _send_card(card, req.lang, deps.now(), stored.id, caller, conn, deps, out)
    if not stored.meta.get("direct"):  # a direct report's text is the card's summary
        await replay(stored.content, out.emit)
    await _sources(conn, _cited(out), deps.docs(), deps, out)
    await out.emit("usage", {"input_tokens": 0, "output_tokens": 0, "ttft_ms": out.ttft_ms,
                             "total_ms": _since(out.started), "model": stored.model,
                             "fallback": False, "replay": True})
    await out.emit("done")


async def _sources(conn: psycopg.Connection, cited: list[str], docs: list[Doc], deps: Deps,
                   out: _Out) -> None:
    await out.emit("sources", {"sources": _source_rows(conn, cited, docs, out.lang, deps.table)})


def _since(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
