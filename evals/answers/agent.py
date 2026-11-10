"""One eval case through the real chat pipeline, in process (docs/03-evaluation-methodology.md).

The case runs through the same code a visitor's message runs through: the endpoint's turn,
the loop, the tools, the router, the citation filter and the output guard, and the database.
Only four things differ from production, all on purpose:
- the response cache is off, so every answer is fresh;
- the visitor limits are lifted, and every case is its own visitor;
- the generator uses GROQ_API_KEY_EVALS when it is set, so the evals' usage shows apart
  (ADR-0005); the provider token counts in quota_counters are shared, as the Groq quota is;
- nothing is exported to Langfuse.

EVAL_MODEL=scripted swaps the model for a scripted one that searches once and cites the first
result, so the whole harness can be checked without spending a token.
"""

import asyncio
import json
import os
import uuid
from functools import cache
from typing import Any

import httpx
from portfolio_agent import chat
from portfolio_agent.agent import prompt
from portfolio_agent.agent.guard import HEBREW, PRIVATE, language
from portfolio_agent.guards.quotas import Limits
from portfolio_agent.providers.base import Finish, TextDelta, ToolCall
from portfolio_agent.providers.router import from_env
from portfolio_agent.retrieval import rerank

UNLIMITED = Limits(visitor_day=10**9, visitor_minute=10**9, ip_day=10**9, conversation=10**9)


class Scripted:
    """Searches for the question, then answers citing the first chunk it got back."""

    switches: list = []

    async def stream(self, messages, tools):
        last = messages[-1]
        if last["role"] == "user" and tools:
            yield ToolCall("t1", "search_portfolio", json.dumps({"query": last["content"][:200]}))
            yield Finish("scripted", {"input_tokens": 0, "output_tokens": 0})
            return
        ids = []
        if last["role"] == "tool":
            ids = [r["chunk_id"] for r in json.loads(last["content"]).get("results", [])]
        question = next(m["content"] for m in reversed(messages) if m["role"] == "user")
        he = bool(HEBREW.search(question))
        cite = f" [[{ids[0]}]]" if ids else ""
        yield TextDelta(("זו תשובה מתוסרטת" if he else "A scripted answer") + cite + ".")
        yield Finish("scripted", {"input_tokens": 0, "output_tokens": 0})


@cache
def _router():
    env = dict(os.environ)
    if env.get("GROQ_API_KEY_EVALS"):
        env["GROQ_API_KEY"] = env["GROQ_API_KEY_EVALS"]
    return from_env(httpx.AsyncClient(), env)


@cache
def _ranker():
    env = dict(os.environ)
    if env.get("GROQ_API_KEY_EVALS"):
        env["GROQ_API_KEY"] = env["GROQ_API_KEY_EVALS"]
    return rerank.from_env(httpx.Client(), env)


def deps() -> chat.Deps:
    scripted = os.environ.get("EVAL_MODEL") == "scripted"
    return chat.Deps(
        database_url=lambda: os.environ.get("EVAL_DATABASE_URL") or os.environ.get("DATABASE_URL"),
        provider=(lambda quota: Scripted()) if scripted
        else (lambda quota: _router().for_turn(quota)),
        ranker=(lambda: None) if scripted else _ranker,
        limits=lambda: UNLIMITED,
        tracer=lambda: None,
        table=os.environ.get("EVAL_TABLE", "chunks"),
        use_cache=False,
    )


def _events(frame: str) -> tuple[str, dict[str, Any]]:
    lines = dict(line.split(": ", 1) for line in frame.strip().splitlines())
    return lines["event"], json.loads(lines["data"])


async def _turn(message: str, conversation_id: str | None, caller: chat.Caller,
                d: chat.Deps) -> dict[str, Any]:
    req = chat.ChatRequest(message=message, conversation_id=conversation_id,
                           idempotency_key=f"eval-{uuid.uuid4().hex}")
    events = [_events(f) async for f in chat._frames(req, d, caller)]
    meta = next((v for e, v in events if e == "meta"), {})
    usage = next((v for e, v in events if e == "usage"), {})
    error = next((v for e, v in events if e == "error"), None)
    answer = "".join(v["text"] for e, v in events if e == "token")
    sources = next((v["sources"] for e, v in events if e == "sources"), [])
    steps = [v for e, v in events if e == "step"]
    return {
        "user": message,
        "answer": answer,
        "citations": [v["chunk_id"] for e, v in events if e == "citation"],
        "sources": [{"chunk_id": s["chunk_id"], "text": s["text"]} for s in sources],
        "tools": [s["name"] for s in steps if s.get("kind") == "tool_call"],
        "error": error and error.get("code"),
        "blocked": any(s.get("kind") == "guard" for s in steps),
        "canary_in_answer": prompt.canary() in answer,
        "private_info": bool(PRIVATE.search(answer)),
        "language": language(answer),
        "words": len(answer.split()),
        "model": usage.get("model"),
        "fallback": bool(usage.get("fallback")),
        "tokens": {"input": usage.get("input_tokens", 0), "output": usage.get("output_tokens", 0)},
        "conversation_id": meta.get("conversation_id"),
    }


async def run_turns(turns: list[str]) -> list[dict[str, Any]]:
    """Every turn in one conversation, as one visitor. Returns each turn's result."""
    d = deps()
    caller = chat.Caller(visitor_id=f"eval-{uuid.uuid4().hex[:12]}", ip="eval")
    out, cid = [], None
    for message in turns:
        result = await _turn(message, cid, caller, d)
        cid = result["conversation_id"] or cid
        out.append(result)
    return out


@cache
def _loop() -> asyncio.AbstractEventLoop:
    """One event loop for the whole run. The router's client is cached across cases, so its
    pooled connections belong to the loop they were opened on: with asyncio.run per case, the
    first one closed after its loop was gone raised "Event loop is closed" (groq T1 run 11,
    case d1-033)."""
    return asyncio.new_event_loop()


def run(turns: list[str]) -> list[dict[str, Any]]:
    return _loop().run_until_complete(run_turns(turns))
