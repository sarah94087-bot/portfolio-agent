"""One streaming client for every OpenAI-compatible provider (ADR-0005).

A provider is only a base_url, a key and a model. The client turns the streamed chat completion
into the loop's three events: text deltas as they arrive, tool calls whole once their argument
fragments are joined, and Finish with the usage. Groq's reasoning models also stream a
`reasoning` field; it is not part of the answer and is skipped.

Failures are classified for the router (docs/06-agent-design.md, section 4) before anything is
yielded: a 429 says whether the minute or the day ran out, a 5xx or a slow first byte is
"unavailable". The 8-second timeout covers the wait for the first bytes and every gap between
streamed chunks; a long answer is fine, since chunks (reasoning included) keep arriving.
"""

import json
import re
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from portfolio_agent.providers.base import Event, Finish, Message, TextDelta, ToolCall

FIRST_EVENT_TIMEOUT = 8.0  # seconds to the first token (section 4)
TEMPERATURE = 0.2
MAX_OUTPUT_TOKENS = 800
_DAY = re.compile(r"per day|\(RPD\)|\(TPD\)", re.IGNORECASE)


class ProviderError(Exception):
    """The provider could not serve this call. `retry_after` is in seconds, when known."""

    def __init__(self, kind: str, message: str, retry_after: float | None = None):
        super().__init__(f"{kind}: {message}")
        self.kind = kind  # rate_minute | rate_day | too_large | unavailable | bad_request
        self.retry_after = retry_after


@dataclass(frozen=True)
class Endpoint:
    name: str  # what the trace and the breaker call it, e.g. "groq/openai/gpt-oss-120b"
    base_url: str
    api_key: str
    model: str


def classify(status: int, body: str, headers: httpx.Headers) -> ProviderError:
    retry = headers.get("retry-after")
    retry_after = float(retry) if retry and retry.replace(".", "", 1).isdigit() else None
    if status == 429:
        kind = "rate_day" if _DAY.search(body) else "rate_minute"
        return ProviderError(kind, body[:300], retry_after)
    if status == 413:  # larger than this model takes in a minute; a model with more room may not be
        return ProviderError("too_large", f"HTTP {status}: {body[:300]}", retry_after)
    if status >= 500:
        return ProviderError("unavailable", f"HTTP {status}", retry_after)
    return ProviderError("bad_request", f"HTTP {status}: {body[:300]}")


REASONING_EFFORT_MODELS = ("openai/gpt-oss",)  # those that take "low"


class OpenAICompatible:
    def __init__(self, endpoint: Endpoint, client: httpx.AsyncClient,
                 temperature: float = TEMPERATURE, max_tokens: int = MAX_OUTPUT_TOKENS):
        self.endpoint = endpoint
        self.client = client
        self.temperature = temperature
        self.max_tokens = max_tokens

    @property
    def name(self) -> str:
        return self.endpoint.name

    async def stream(
        self, messages: Sequence[Message], tools: Sequence[dict[str, Any]], **options: Any
    ) -> AsyncIterator[Event]:
        """`options` overrides request fields for one call: temperature, max_tokens,
        tool_choice and reasoning_effort (the job match's structured output, at temperature 0)."""
        body: dict[str, Any] = {
            "model": self.endpoint.model,
            "messages": list(messages),
            "stream": True,
            "stream_options": {"include_usage": True},
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            **options,
        }
        if not self.endpoint.model.startswith(REASONING_EFFORT_MODELS):
            body.pop("reasoning_effort", None)  # a value other models answer 400 to
        if tools:
            body["tools"] = list(tools)
        url = self.endpoint.base_url.rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {self.endpoint.api_key}"}
        timeout = httpx.Timeout(FIRST_EVENT_TIMEOUT, read=FIRST_EVENT_TIMEOUT)
        try:
            async with self.client.stream("POST", url, json=body, headers=headers,
                                          timeout=timeout) as response:
                if response.status_code != 200:
                    text = (await response.aread()).decode("utf-8", "replace")
                    raise classify(response.status_code, text, response.headers)
                async for event in parse(response.aiter_lines(), self.endpoint.model):
                    yield event
        except httpx.TimeoutException as e:
            raise ProviderError("unavailable", f"timeout: {type(e).__name__}") from e
        except httpx.TransportError as e:
            raise ProviderError("unavailable", f"{type(e).__name__}: {e}") from e


async def parse(lines: AsyncIterator[str], model: str) -> AsyncIterator[Event]:
    """SSE lines of a chat completion stream into events. Tool call fragments are keyed by
    their index, and the calls come out whole, in index order, before Finish."""
    calls: dict[int, dict[str, str]] = {}
    usage: dict[str, int] = {}
    seen_model = model
    async for line in lines:
        if not line.startswith("data:"):
            continue
        data = line[len("data:"):].strip()
        if data == "[DONE]":
            break
        chunk = json.loads(data)
        seen_model = chunk.get("model") or seen_model
        if chunk.get("usage"):
            u = chunk["usage"]
            usage = {"input_tokens": u.get("prompt_tokens", 0),
                     "output_tokens": u.get("completion_tokens", 0)}
        # Groq also reports usage under x_groq on the last chunk.
        if (xg := chunk.get("x_groq")) and xg.get("usage") and not usage:
            u = xg["usage"]
            usage = {"input_tokens": u.get("prompt_tokens", 0),
                     "output_tokens": u.get("completion_tokens", 0)}
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            if delta.get("content"):
                yield TextDelta(delta["content"])
            for tc in delta.get("tool_calls") or []:
                slot = calls.setdefault(tc.get("index", 0), {"id": "", "name": "", "args": ""})
                slot["id"] = tc.get("id") or slot["id"]
                fn = tc.get("function") or {}
                slot["name"] = fn.get("name") or slot["name"]
                slot["args"] += fn.get("arguments") or ""
    for i in sorted(calls):
        c = calls[i]
        yield ToolCall(c["id"] or f"call_{i}", c["name"], c["args"])
    yield Finish(seen_model, usage)
