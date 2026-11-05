"""The router between models, with a circuit breaker (docs/06-agent-design.md, section 4).

Models are tried in the order of ADR-0005. A model whose minute ran out is skipped for a
minute (or for Retry-After); one whose day ran out is skipped until the reset. Requests that
come later go straight to the next model, without spending a call to learn the same thing.
A 5xx or a timeout moves the call to the next model without opening the breaker for long.

A failure before the first event is invisible to the visitor. After text was sent, the router
yields Restart and the next model answers the same round from the start, and the loop tells
the visitor so: transparency is a pillar, so the switch is shown, not hidden.

Minute and 5xx pauses live in memory: they are short, and losing one costs a single call.
A day limit is written to quota_counters through a QuotaStore (guards/quotas.py) and read at
the start of every turn, so it survives a cold start and every instance skips the model.
"""

import os
import time
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from portfolio_agent.providers.base import Event, Message, NeedsFallback
from portfolio_agent.providers.openai_compat import Endpoint, OpenAICompatible, ProviderError

MINUTE = 60.0
DAY_FALLBACK = 3600.0  # when a day limit gives no Retry-After, look again in an hour
UNAVAILABLE_PAUSE = 10.0  # a 5xx or timeout: a short pause, not a long one
GROQ_BASE = "https://api.groq.com/openai/v1"


class Model(Protocol):
    name: str

    def stream(
        self, messages: Sequence[Message], tools: Sequence[dict[str, Any]]
    ) -> AsyncIterator[Event]: ...


@dataclass(frozen=True)
class Restart:
    """The model failed after it had started answering; the next one starts the round over."""

    failed: str
    to: str
    reason: str


class QuotaStore(Protocol):
    def closed(self) -> dict[str, tuple[float, str]]: ...  # name -> (Unix time, reason)

    def close(self, model: str, until: float) -> None: ...


class AllModelsFailed(Exception):
    def __init__(self, code: str, attempts: list[tuple[str, str]]):
        super().__init__(code)
        self.code = code  # quota_exhausted | provider_unavailable (the SSE error codes)
        self.attempts = attempts


@dataclass
class Router:
    models: list[Model]
    clock: Callable[[], float] = time.monotonic
    wall: Callable[[], float] = time.time
    closed_until: dict[str, float] = field(default_factory=dict)  # model name -> time
    open_reason: dict[str, str] = field(default_factory=dict)

    def available(self) -> list[Model]:
        now = self.clock()
        return [m for m in self.models if self.closed_until.get(m.name, 0.0) <= now]

    def trip(self, model: Model, error: ProviderError, store: QuotaStore | None = None) -> None:
        pause = {
            "rate_minute": error.retry_after or MINUTE,
            "rate_day": error.retry_after or DAY_FALLBACK,
            "unavailable": error.retry_after or UNAVAILABLE_PAUSE,
        }.get(error.kind)
        if pause is not None:
            self._close(model.name, self.clock() + pause, error.kind)
            if store is not None and error.kind == "rate_day":
                store.close(model.name, self.wall() + pause)

    def _close(self, name: str, until: float, reason: str) -> None:
        if until > self.closed_until.get(name, 0.0):
            self.closed_until[name] = until
            self.open_reason[name] = reason

    def for_turn(self, store: QuotaStore | None = None) -> "TurnRouter":
        """With a store, what other instances learned today is loaded first."""
        if store is not None:
            offset = self.clock() - self.wall()  # Unix time -> this router's clock
            for name, (until, reason) in store.closed().items():
                self._close(name, until + offset, reason)
        return TurnRouter(self, store)


@dataclass
class TurnRouter:
    """The router as one turn sees it: a model dropped for invalid tool calls stays dropped
    for this turn only, since the next visitor's question may suit it fine."""

    router: Router
    store: QuotaStore | None = None
    dropped: set[str] = field(default_factory=set)
    current: str | None = None
    switches: list[dict[str, str]] = field(default_factory=list)  # for the trace and usage

    def fall_back(self, reason: str) -> None:
        """Called by the loop after the second invalid tool call (section 1)."""
        if self.current is None:
            raise NeedsFallback(reason)
        self.dropped.add(self.current)
        if not self._candidates():
            raise NeedsFallback(reason)
        self.switches.append({"from": self.current, "reason": reason})

    def _candidates(self) -> list[Model]:
        return [m for m in self.router.available() if m.name not in self.dropped]

    async def stream(
        self, messages: Sequence[Message], tools: Sequence[dict[str, Any]]
    ) -> AsyncIterator[Event | Restart]:
        attempts: list[tuple[str, str]] = []
        failed_after_text: tuple[str, str] | None = None
        for model in self._candidates():
            started = False
            if failed_after_text:
                yield Restart(failed_after_text[0], model.name, failed_after_text[1])
                failed_after_text = None
            self.current = model.name
            try:
                async for event in model.stream(messages, tools):
                    started = True
                    yield event
                return
            except ProviderError as e:
                if e.kind == "bad_request":
                    raise  # the request itself is wrong; another model would fail the same
                self.router.trip(model, e, self.store)
                attempts.append((model.name, e.kind))
                self.switches.append({"from": model.name, "reason": e.kind})
                if started:
                    failed_after_text = (model.name, e.kind)
        quota = attempts and all(kind.startswith("rate_") for _, kind in attempts)
        if not attempts:  # every model was already closed before this call
            reasons = [self.router.open_reason.get(m.name, "") for m in self.router.models]
            quota = all(r.startswith("rate_") for r in reasons if r)
        raise AllModelsFailed("quota_exhausted" if quota else "provider_unavailable", attempts)


def from_env(client: httpx.AsyncClient, env: dict[str, str] | None = None) -> Router:
    """The ADR-0005 order from the environment (.env.example): GROQ_MODEL, then
    GROQ_FALLBACK_MODELS in order. No Gemini on the visitor path (ADR-0009)."""
    env = dict(os.environ) if env is None else env
    key = env.get("GROQ_API_KEY")
    if not key:
        raise ValueError("GROQ_API_KEY is not set")
    names = [env.get("GROQ_MODEL") or "openai/gpt-oss-120b"]
    names += [m.strip() for m in env.get("GROQ_FALLBACK_MODELS", "").split(",") if m.strip()]
    names = list(dict.fromkeys(names))
    return Router([
        OpenAICompatible(Endpoint(f"groq/{m}", GROQ_BASE, key, m), client) for m in names
    ])
