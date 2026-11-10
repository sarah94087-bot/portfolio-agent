"""FastAPI app: health, and the chat, feedback and stats endpoints (chat.py, feedback.py,
stats.py)."""

import time
from typing import Any

from fastapi import FastAPI

from portfolio_agent import __version__, chat, feedback, stats
from portfolio_agent.config import Settings

# Instance bookkeeping for the cold start spike (S2): the first request an instance serves
# after import is the cold one.
_BOOTED_AT = time.monotonic()
_requests_served = 0

app = FastAPI(title="portfolio-agent", version=__version__, docs_url=None, redoc_url=None)
app.include_router(chat.router)
app.include_router(feedback.router)
app.include_router(stats.router)


class _SecurityHeaders:
    """The headers of docs/09-security-privacy.md, section 5, that apply to an API response. The
    web service sets its own. Plain ASGI, so a stream passes through chunk by chunk."""

    HEADERS = ((b"x-content-type-options", b"nosniff"),
               (b"referrer-policy", b"strict-origin-when-cross-origin"))

    def __init__(self, inner: Any) -> None:
        self.inner = inner

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        async def with_headers(message: Any) -> None:
            if message["type"] == "http.response.start":
                message = {**message, "headers": [*message["headers"], *self.HEADERS]}
            await send(message)

        await self.inner(scope, receive, with_headers)


app.add_middleware(_SecurityHeaders)


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


def _warm_knowledge() -> dict:
    """Loads the records once per instance, and checks what a chat turn needs from them first:
    the profile's name. The deploy's smoke test reads this, at no cost in model tokens."""
    from portfolio_agent.retrieval.query import owner_names

    try:
        docs = chat.DEPS.docs()
        owner_names(d.record for d in docs)
    except Exception as exc:
        return {"ready": False, "error": type(exc).__name__}
    return {"ready": True, "records": len(docs)}


@app.get("/api/health")
def health(warm: bool = False, db: bool = True) -> dict:
    """`warm` is what the page sends when it loads (spike S2): one request wakes the function,
    Neon and the embedding model while the visitor reads and types. Without it the check stays
    cheap, for the uptime and smoke checks.

    `db=0` is for the external monitor, every 5 minutes: it answers without touching Neon.
    Neon sleeps after 5 minutes idle, so a database check that often would keep it awake all
    month, about 180 of the free plan's 100 CU-hours (docs/10, section 6)."""
    settings = Settings.from_env()
    if not db:
        result = {"ok": None, "skipped": True}
    else:
        result = _check_db(settings.database_url) if settings.database_url else {"ok": None}
    return {
        "version": __version__,
        "agent_enabled": settings.agent_enabled,
        "db": result,
        **({"embedder": _warm_embedder(), "knowledge": _warm_knowledge()} if warm else {}),
        **_instance_info(),
    }

