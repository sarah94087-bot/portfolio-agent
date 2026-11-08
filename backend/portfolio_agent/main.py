"""FastAPI app: health, the chat and feedback endpoints (chat.py, feedback.py), and the M1
spike endpoints S1 and S2."""

import asyncio
import time
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from portfolio_agent import __version__, chat, feedback, sse
from portfolio_agent.config import Settings

# Instance bookkeeping for the cold start spike (S2): the first request an instance serves
# after import is the cold one.
_BOOTED_AT = time.monotonic()
_requests_served = 0

app = FastAPI(title="portfolio-agent", version=__version__, docs_url=None, redoc_url=None)
app.include_router(chat.router)
app.include_router(feedback.router)


def _instance_info() -> dict:
    global _requests_served
    _requests_served += 1
    return {
        "cold": _requests_served == 1,
        "instance_uptime_ms": round((time.monotonic() - _BOOTED_AT) * 1000),
    }


def _check_db(database_url: str) -> dict:
    # Lazy import keeps cold start lighter when the database is not needed.
    import psycopg

    started = time.perf_counter()
    try:
        with psycopg.connect(database_url, connect_timeout=2) as conn:
            conn.execute("select 1")
        return {"ok": True, "ms": round((time.perf_counter() - started) * 1000)}
    except psycopg.Error as exc:
        return {"ok": False, "ms": round((time.perf_counter() - started) * 1000),
                "error": type(exc).__name__}


def _warm_embedder() -> dict:
    """Loads the model once per instance. A failure is reported, not raised: the page only asks
    to wake things up, and search without the model still answers, with R1."""
    from portfolio_agent.retrieval import embedder

    started = time.perf_counter()
    try:
        model = embedder.from_env()
    except Exception as exc:
        return {"ready": False, "error": type(exc).__name__}
    return {"ready": model is not None, "ms": round((time.perf_counter() - started) * 1000)}


@app.get("/api/health")
def health(warm: bool = False) -> dict:
    """`warm` is what the page sends when it loads (spike S2): one request wakes the function,
    Neon and the embedding model while the visitor reads and types. Without it the check stays
    cheap, for the uptime and smoke checks."""
    settings = Settings.from_env()
    db = _check_db(settings.database_url) if settings.database_url else {"ok": None}
    return {
        "version": __version__,
        "agent_enabled": settings.agent_enabled,
        "db": db,
        **({"embedder": _warm_embedder()} if warm else {}),
        **_instance_info(),
    }


_SPIKE_WORDS = ["זה", "ניסוי", "הזרמה.", "this", "is", "a", "streaming", "spike."]


async def _spike_events(started: float, info: dict) -> AsyncIterator[str]:
    yield sse.encode("meta", {"spike": "s1", **info})
    ttft_ms = None
    for word in _SPIKE_WORDS:
        await asyncio.sleep(0.05)
        if ttft_ms is None:
            ttft_ms = round((time.perf_counter() - started) * 1000)
        yield sse.encode("token", {"text": word + " "})
    total_ms = round((time.perf_counter() - started) * 1000)
    yield sse.encode("usage", {"ttft_ms": ttft_ms, "total_ms": total_ms})
    yield sse.encode("done")


@app.get("/api/spike/stream")
async def spike_stream() -> StreamingResponse:
    """Fake answer stream for S1: checks SSE survives the Vercel runtime unbuffered."""
    started = time.perf_counter()
    return StreamingResponse(
        _spike_events(started, _instance_info()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
