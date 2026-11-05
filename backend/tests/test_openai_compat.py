"""The streaming client against a fake HTTP server (httpx.MockTransport): no network."""

import asyncio
import json

import httpx
import pytest

from portfolio_agent.providers.base import Finish, TextDelta, ToolCall
from portfolio_agent.providers.openai_compat import (
    Endpoint,
    OpenAICompatible,
    ProviderError,
    classify,
)

ENDPOINT = Endpoint("groq/test", "https://api.example.test/openai/v1", "k", "test-model")


def sse(*chunks):
    lines = [f"data: {json.dumps(c)}" for c in chunks] + ["data: [DONE]"]
    return "\n\n".join(lines) + "\n\n"


def collect(handler, tools=()):
    seen = {}

    def wrapped(request):
        seen["request"] = request
        return handler(request)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(wrapped)) as client:
            model = OpenAICompatible(ENDPOINT, client)
            return [e async for e in model.stream([{"role": "user", "content": "hi"}], tools)]

    return asyncio.run(go()), seen


def test_text_and_usage_stream_as_events_and_reasoning_is_skipped():
    body = sse(
        {"model": "test-model", "choices": [{"delta": {"reasoning": "thinking..."}}]},
        {"choices": [{"delta": {"content": "היא "}}]},
        {"choices": [{"delta": {"content": "בנתה"}}]},
        {"choices": [], "usage": {"prompt_tokens": 12, "completion_tokens": 3}},
    )
    events, seen = collect(lambda r: httpx.Response(200, text=body))
    assert events == [TextDelta("היא "), TextDelta("בנתה"),
                      Finish("test-model", {"input_tokens": 12, "output_tokens": 3})]
    sent = json.loads(seen["request"].content)
    assert seen["request"].url == "https://api.example.test/openai/v1/chat/completions"
    assert seen["request"].headers["authorization"] == "Bearer k"
    assert sent["stream"] is True and sent["temperature"] == 0.2 and sent["max_tokens"] == 800
    assert "tools" not in sent  # no tools offered on the last round


def tc(index, args, **kw):
    fn = {"arguments": args, **({"name": kw.pop("name")} if "name" in kw else {})}
    return {"index": index, "function": fn, **kw}


def test_tool_call_fragments_are_joined_in_index_order():
    body = sse(
        {"choices": [{"delta": {"tool_calls": [
            tc(1, "", id="c2", name="get_project"),
            tc(0, '{"qu', id="c1", name="search_portfolio"),
        ]}}]},
        {"choices": [{"delta": {"tool_calls": [tc(0, 'ery": "rag"}'), tc(1, '{"id": "x"}')]}}]},
        {"choices": [], "x_groq": {"usage": {"prompt_tokens": 5, "completion_tokens": 9}}},
    )
    events, seen = collect(lambda r: httpx.Response(200, text=body), tools=[{"type": "function"}])
    assert events[:2] == [ToolCall("c1", "search_portfolio", '{"query": "rag"}'),
                          ToolCall("c2", "get_project", '{"id": "x"}')]
    assert events[2] == Finish("test-model", {"input_tokens": 5, "output_tokens": 9})
    assert json.loads(seen["request"].content)["tools"] == [{"type": "function"}]


@pytest.mark.parametrize(("status", "body", "kind"), [
    (429, "Rate limit reached ... tokens per minute (TPM): Limit 8000", "rate_minute"),
    (429, "Rate limit reached ... requests per day (RPD): Limit 1000", "rate_day"),
    (429, "Rate limit reached ... tokens per day (TPD)", "rate_day"),
    (503, "busy", "unavailable"),
    (400, "bad tool schema", "bad_request"),
])
def test_errors_are_classified_for_the_router(status, body, kind):
    with pytest.raises(ProviderError) as e:
        collect(lambda r: httpx.Response(status, text=body, headers={"retry-after": "7"}))
    assert e.value.kind == kind
    if kind != "bad_request":
        assert e.value.retry_after == 7.0


def test_a_timeout_or_a_dropped_connection_is_unavailable():
    for exc in (httpx.ReadTimeout("slow"), httpx.ConnectError("refused")):
        def handler(request, exc=exc):
            raise exc
        with pytest.raises(ProviderError) as e:
            collect(handler)
        assert e.value.kind == "unavailable"


def test_classify_without_retry_after():
    assert classify(429, "per minute", httpx.Headers()).retry_after is None
