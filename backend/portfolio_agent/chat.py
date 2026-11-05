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

Not here yet, and next: the response cache and the Langfuse export (docs/11-roadmap.md, M4).
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
from typing import Any
from uuid import UUID

import httpx
import psycopg
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from portfolio_agent import sse
from portfolio_agent.agent import prompt
from portfolio_agent.agent.loop import run_turn
from portfolio_agent.agent.transcript import Transcript, replay
from portfolio_agent.config import Settings
from portfolio_agent.db import conversations as db
from portfolio_agent.guards import visitor
from portfolio_agent.guards.quotas import Denied, Limits, ProviderQuota, admit
from portfolio_agent.ingest import Doc, load
from portfolio_agent.providers.base import NeedsFallback
from portfolio_agent.providers.openai_compat import ProviderError
from portfolio_agent.providers.router import AllModelsFailed, from_env
from portfolio_agent.retrieval import embedder
from portfolio_agent.tools.portfolio import GET_PROJECT, SEARCH, PortfolioContext
from portfolio_agent.tools.registry import Registry

log = logging.getLogger(__name__)
router = APIRouter()

REGISTRY = Registry.of([SEARCH, GET_PROJECT])


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=20_000)  # the 1,000 rule is an SSE error
    conversation_id: UUID | None = None
    company_slug: str | None = Field(default=None, max_length=64)
    idempotency_key: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


@cache
def _router():
    return from_env(httpx.AsyncClient())


@cache
def _docs() -> list[Doc]:
    return load()


@dataclass
class Deps:
    """What a request needs from outside. Tests swap these for fakes."""

    database_url: Callable[[], str | None] = lambda: Settings.from_env().database_url
    provider: Callable[[ProviderQuota], Any] = lambda quota: _router().for_turn(quota)
    embedder: Callable[[], Any] = embedder.from_env
    docs: Callable[[], list[Doc]] = _docs
    agent_enabled: Callable[[], bool] = lambda: Settings.from_env().agent_enabled
    limits: Callable[[], Limits] = Limits.from_env
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    table: str = "chunks"


DEPS = Deps()


@dataclass(frozen=True)
class Caller:
    visitor_id: str
    ip: str  # hashed before it is stored or counted; never sent to a provider


@router.post("/api/chat")
async def chat(req: ChatRequest, request: Request) -> StreamingResponse:
    cookie = request.cookies.get(visitor.COOKIE)
    visitor_id = visitor.read_cookie(cookie)
    if visitor_id is None:  # new, expired, or not ours
        visitor_id, cookie = visitor.new_cookie()
    ip = visitor.client_ip(dict(request.headers), request.client and request.client.host)
    response = StreamingResponse(
        _frames(req, DEPS, Caller(visitor_id, ip)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
    https = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    response.set_cookie(visitor.COOKIE, cookie, max_age=visitor.MAX_AGE, httponly=True,
                        secure=https, samesite="lax", path="/")  # 30 days from the last use
    return response


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
    ttft_ms: int | None = None

    async def emit(self, event: str, data: dict[str, Any] | None = None) -> None:
        data = data or {}
        if event == "token" and self.ttft_ms is None:
            self.ttft_ms = round((time.perf_counter() - self.started) * 1000)
        self.transcript.record(event, data)
        await self.queue.put(sse.encode(event, data))

    async def error(self, code: str, message: str, retryable: bool, **extra: Any) -> None:
        await self.emit("error", {"code": code, "message": message, "retryable": retryable,
                                  **extra})
        await self.emit("done")


async def _turn(req: ChatRequest, deps: Deps, caller: Caller, queue: asyncio.Queue) -> None:
    out = _Out(queue)
    try:
        await _answer(req, deps, caller, out)
    except Exception:  # anything unexpected still ends the stream with a code
        log.exception("chat turn failed")
        await out.error("internal", "Something went wrong on our side.", True)
    finally:
        await queue.put(None)


async def _answer(req: ChatRequest, deps: Deps, caller: Caller, out: _Out) -> None:
    if not deps.agent_enabled():
        return await out.error("provider_unavailable", "The agent is paused.", False)
    limits = deps.limits()
    if len(req.message) > limits.message_chars:
        return await out.error(
            "input_too_long", f"The message is longer than {limits.message_chars} characters.",
            False)
    url = deps.database_url()
    if not url:
        return await out.error("internal", "No database is configured.", True)

    with psycopg.connect(url, autocommit=True, connect_timeout=5) as conn:
        stored = db.find_answer(conn, req.idempotency_key, caller.visitor_id)
        if stored:
            return await _replay(conn, stored, deps, out)

        now = deps.now()
        conversation_id = db.open_conversation(conn, req.conversation_id, req.company_slug,
                                               caller.visitor_id)
        try:
            admit(conn, visitor_id=caller.visitor_id,
                  ip_hash=visitor.ip_hash(conn, caller.ip, now.date()),
                  conversation_id=conversation_id, now=now, limits=limits)
        except Denied as e:
            return await out.error(e.code, e.message, e.retryable, limit=e.limit,
                                   retry_after=e.retry_after)
        history = db.history(conn, conversation_id)
        allowed = db.retrieved_chunks(conn, conversation_id)
        db.save_user(conn, conversation_id, req.message)
        message_id = uuid.uuid4()
        await out.emit("meta", {"conversation_id": str(conversation_id),
                                "message_id": str(message_id),
                                "prompt_version": prompt.VERSION})

        docs = deps.docs()
        ctx = PortfolioContext.from_docs(conn, docs, embedder=deps.embedder(), table=deps.table)
        quota = ProviderQuota(conn, now, limits)
        provider = deps.provider(quota)
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
        model = result.models[-1] if result.models else None
        if model:  # all of the turn's tokens go to the model that finished it; a switch is rare
            quota.spend(model, result.usage.get("input_tokens", 0)
                        + result.usage.get("output_tokens", 0))
        # The same message sent twice at once: the other request saved it, and that is fine.
        with contextlib.suppress(psycopg.errors.UniqueViolation):
            db.save_answer(
                conn, message_id=message_id, conversation_id=conversation_id,
                content=out.transcript.content, model=model, prompt_version=prompt.VERSION,
                usage=result.usage, meta=meta, idempotency_key=req.idempotency_key,
                steps=out.transcript.steps,
            )
        await _sources(conn, out.transcript.cited, docs, deps, out)
        await out.emit("usage", {**result.usage, "ttft_ms": out.ttft_ms,
                                 "total_ms": _since(out.started), "model": model,
                                 "fallback": bool(switches)})
        await out.emit("done")


async def _replay(conn: psycopg.Connection, stored: db.StoredAnswer, deps: Deps,
                  out: _Out) -> None:
    await out.emit("meta", {"conversation_id": str(stored.conversation_id),
                            "message_id": str(stored.id), "replay": True})
    await replay(stored.content, out.emit)
    await _sources(conn, out.transcript.cited, deps.docs(), deps, out)
    await out.emit("usage", {"input_tokens": 0, "output_tokens": 0, "ttft_ms": out.ttft_ms,
                             "total_ms": _since(out.started), "model": stored.model,
                             "fallback": False, "replay": True})
    await out.emit("done")


async def _sources(conn: psycopg.Connection, cited: list[str], docs: list[Doc], deps: Deps,
                   out: _Out) -> None:
    titles = {d.record.id: getattr(getattr(d.record, "title", None), "en", d.record.id)
              for d in docs}
    rows = db.chunk_sources(conn, cited, deps.table)
    await out.emit("sources", {"sources": [
        {"chunk_id": cid, "record_title": titles.get(rid, rid),
         "section": cid.partition("#")[2], "text": text}
        for cid, rid, text in rows
    ]})


def _since(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
