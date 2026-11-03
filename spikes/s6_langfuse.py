"""Spike S6: does a trace sent over OpenTelemetry (OTLP/HTTP, JSON) reach Langfuse with the
fields the trace panel needs (docs/08-transparency.md, section 2)?

    python spikes/s6_langfuse.py

Afterwards, open the trace in Langfuse and check that the span tree, durations, model name
and token counts are shown. That last check is by eye.
"""

import base64
import os
import secrets
import time
from urllib.parse import urlparse

import httpx
from common import load_env, require


def span(trace_id: str, span_id: str, parent: str | None, name: str,
         start_ns: int, end_ns: int, attrs: dict) -> dict:
    return {
        "traceId": trace_id,
        "spanId": span_id,
        **({"parentSpanId": parent} if parent else {}),
        "name": name,
        "kind": 1,
        "startTimeUnixNano": str(start_ns),
        "endTimeUnixNano": str(end_ns),
        "attributes": [
            {"key": k, "value": {"intValue": str(v)} if isinstance(v, int) else {"stringValue": v}}
            for k, v in attrs.items()
        ],
    }


def main() -> None:
    load_env()
    env = require("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")
    # Only the origin counts: a URL copied from the Langfuse UI carries a /project/... path.
    url = urlparse(os.environ.get("LANGFUSE_HOST") or "https://cloud.langfuse.com")
    host = f"{url.scheme}://{url.netloc}"
    auth = base64.b64encode(
        f"{env['LANGFUSE_PUBLIC_KEY']}:{env['LANGFUSE_SECRET_KEY']}".encode()
    ).decode()

    trace_id = secrets.token_hex(16)
    root, llm, tool = secrets.token_hex(8), secrets.token_hex(8), secrets.token_hex(8)
    t0 = time.time_ns()
    ms = 1_000_000
    spans = [
        span(trace_id, root, None, "chat_turn", t0, t0 + 1400 * ms,
             {"spike": "s6", "langfuse.trace.name": "spike-s6"}),
        span(trace_id, tool, root, "search_portfolio", t0 + 20 * ms, t0 + 180 * ms,
             {"tool.query": "human review machine translation", "retrieval.candidates": 20}),
        span(trace_id, llm, root, "llm.generate", t0 + 200 * ms, t0 + 1380 * ms,
             {"gen_ai.request.model": "spike-model", "gen_ai.usage.input_tokens": 1620,
              "gen_ai.usage.output_tokens": 200}),
    ]
    body = {"resourceSpans": [{
        "resource": {"attributes": [
            {"key": "service.name", "value": {"stringValue": "portfolio-agent"}}]},
        "scopeSpans": [{"scope": {"name": "spike"}, "spans": spans}],
    }]}
    r = httpx.post(
        f"{host}/api/public/otel/v1/traces",
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
        json=body,
        timeout=20,
    )
    print(f"HTTP {r.status_code} {r.text[:200]}")
    print(f"trace id: {trace_id}  (search for it in Langfuse > Traces)")


if __name__ == "__main__":
    main()
