"""The Langfuse trace: its shape, what is masked, what never leaves, and a failing export."""

import asyncio
import json
import logging
import uuid

import httpx

from portfolio_agent import tracing


def spans(body):
    return body["resourceSpans"][0]["scopeSpans"][0]["spans"]


def attrs(span):
    out = {}
    for a in span["attributes"]:
        (kind, v), = a["value"].items()
        out[a["key"]] = [x["stringValue"] for x in v["values"]] if kind == "arrayValue" else v
    return out


def turn_events(rec, *, canary=False, error=None):
    mid = str(uuid.uuid4())
    rec.record("meta", {"conversation_id": "c-1", "message_id": mid, "prompt_version": "system.v1"})
    rec.record("step", {"step_id": "s1", "kind": "llm", "status": "start", "name": "round 1"})
    rec.record("step", {"step_id": "s1", "kind": "llm", "status": "end", "name": "round 1",
                        "summary": {"tool_calls": ["search_portfolio"], "model": "groq/m",
                                    "usage": {"input_tokens": 900, "output_tokens": 20}}})
    rec.record("step", {"step_id": "s2", "kind": "tool_call", "status": "start",
                        "name": "search_portfolio", "args": {"query": "write to me at a@b.co"}})
    rec.record("step", {"step_id": "s2", "kind": "tool_result", "status": "end",
                        "name": "search_portfolio", "summary": {"method": "R3", "results": []}})
    if canary:
        rec.record("step", {"step_id": "guard", "kind": "guard", "status": "end",
                            "summary": {"blocked": "canary"}})
    if error:
        rec.record("error", {"code": error, "limit": "minute"})
    rec.record("usage", {"model": "groq/m", "ttft_ms": 400, "total_ms": 1200, "fallback": False})
    rec.record("token", {"text": "x"})
    return mid


def build(**kw):
    rec = tracing.Recorder()
    mid = turn_events(rec, **{k: kw.pop(k) for k in ("canary", "error") if k in kw})
    turn = tracing.Turn(message=kw.get("message", "call me on 050-1234567"),
                        answer=kw.get("answer", "She did."), conversation_id="c-1",
                        message_id=mid, dropped=kw.get("dropped", []))
    return mid, tracing.build(rec, turn, "preview")


def test_one_root_with_a_generation_per_round_and_a_span_per_tool():
    mid, body = build()
    all_spans = spans(body)
    root, llm, tool = all_spans
    assert root["traceId"] == mid.replace("-", "") and "parentSpanId" not in root
    assert {s["parentSpanId"] for s in (llm, tool)} == {root["spanId"]}
    a = attrs(root)
    assert a["langfuse.session.id"] == "c-1" and a["langfuse.trace.output"] == "She did."
    assert a["langfuse.trace.metadata.prompt_version"] == "system.v1"
    g = attrs(llm)
    assert g["langfuse.observation.type"] == "generation" and g["gen_ai.request.model"] == "groq/m"
    assert g["gen_ai.usage.input_tokens"] == "900"
    assert tool["name"] == "search_portfolio"
    assert int(tool["endTimeUnixNano"]) >= int(tool["startTimeUnixNano"])
    env = body["resourceSpans"][0]["resource"]["attributes"]
    assert {"key": "deployment.environment", "value": {"stringValue": "preview"}} in env


def test_emails_and_phones_are_masked_and_no_visitor_data_leaves():
    _, body = build()
    sent = json.dumps(body)
    assert "1234567" not in sent and "a@b.co" not in sent and tracing.MASK in sent
    for word in ("visitor", "ip_hash", "pa_vid"):
        assert word not in sent


def test_a_canary_block_is_a_severe_error_and_logged_critical(caplog):
    _, body = build(canary=True)
    root = attrs(spans(body)[0])
    assert root["langfuse.observation.level"] == "ERROR" and "severe" in root["langfuse.trace.tags"]
    assert any(s["name"] == "canary_blocked" for s in spans(body))
    rec = tracing.Recorder()
    mid = turn_events(rec, canary=True)
    with caplog.at_level(logging.CRITICAL):
        asyncio.run(tracing.export(rec, tracing.Turn("q", "safe", "c-1", mid, []), None,
                                   httpx.AsyncClient()))
    assert "SEVERE" in caplog.text and mid in caplog.text


def test_errors_and_dropped_citations_are_marked():
    _, body = build(error="rate_limited", dropped=["made-up#all"])
    root = attrs(spans(body)[0])
    assert root["langfuse.observation.level"] == "WARNING"
    assert root["langfuse.trace.metadata.error"] == "rate_limited"
    assert root["langfuse.trace.metadata.limit"] == "minute"
    dropped = next(s for s in spans(body) if s["name"] == "citation_dropped")
    assert attrs(dropped)["langfuse.observation.metadata.chunk_ids"] == ["made-up#all"]


def test_the_exporter_needs_both_keys_and_keeps_only_the_origin():
    assert tracing.Exporter.from_env({"LANGFUSE_PUBLIC_KEY": "pk"}) is None
    e = tracing.Exporter.from_env({"LANGFUSE_PUBLIC_KEY": "pk", "LANGFUSE_SECRET_KEY": "sk",
                                   "LANGFUSE_HOST": "https://cloud.langfuse.com/project/x/traces"})
    assert e.endpoint == "https://cloud.langfuse.com/api/public/otel/v1/traces"
    assert e.environment == "local"


def test_a_failing_export_never_raises():
    e = tracing.Exporter("https://lf.test/api/public/otel/v1/traces", "auth", "local")
    seen = []

    def handler(request):
        seen.append(request.headers["authorization"])
        raise httpx.ConnectError("blocked")

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await e.send({"resourceSpans": []}, client)
    assert asyncio.run(go()) is False and seen == ["Basic auth"]
    ok = httpx.MockTransport(lambda r: httpx.Response(200, json={}))

    async def go_ok():
        async with httpx.AsyncClient(transport=ok) as client:
            return await e.send({"resourceSpans": []}, client)
    assert asyncio.run(go_ok()) is True
