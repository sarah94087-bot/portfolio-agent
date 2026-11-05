"""One trace per chat request, to Langfuse over OpenTelemetry (docs/05-architecture.md; spike S6).

The trace is built from the same events the visitor's browser got, so the trace in Langfuse
and the trace panel in the UI cannot tell different stories. It is sent as OTLP/HTTP JSON with
httpx, as in S6, so no OpenTelemetry SDK ships in the function.

- The trace id is the answer's message id, so a row in `messages` and its trace find each other.
- The session id is the conversation id: the daily job deletes a conversation's traces by it
  (US-12.4), since the Hobby plan has no retention setting (docs/10).
- Emails and phone numbers are masked in everything sent (US-12.3). The answer was already
  masked by the output guard; the visitor's message and tool arguments are masked here.
- Never sent: the visitor id, the IP or its hash, the system prompt, the canary.
- The export runs after `done` and before the stream closes: the visitor already has the whole
  answer, and a serverless instance is not frozen before the trace leaves. It never raises.

A canary leak is a severe event (docs/09-security-privacy.md, section 7): the trace gets level
ERROR and the tag `severe`, and a CRITICAL log line goes to the platform logs.
"""

import base64
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

from portfolio_agent.agent.guard import PRIVATE

log = logging.getLogger(__name__)
TIMEOUT = 3.0
MASK = "[hidden]"
MAX_TEXT = 4000  # longer strings are cut: a trace is for reading, not for archiving


def mask(value: Any) -> Any:
    if isinstance(value, str):
        text = PRIVATE.sub(MASK, value)
        return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + "…"
    if isinstance(value, dict):
        return {k: mask(v) for k, v in value.items()}
    if isinstance(value, list):
        return [mask(v) for v in value]
    return value


@dataclass
class Recorder:
    """The request's events with the time each one left, for span start and end times."""

    started_ns: int = field(default_factory=time.time_ns)
    events: list[tuple[int, str, dict[str, Any]]] = field(default_factory=list)

    def record(self, event: str, data: dict[str, Any]) -> None:
        if event in ("step", "meta", "error", "usage"):
            self.events.append((time.time_ns(), event, data))


@dataclass(frozen=True)
class Turn:
    message: str
    answer: str
    conversation_id: str | None
    message_id: str | None
    dropped: list[str]


def _value(v: Any) -> dict[str, Any]:
    if isinstance(v, bool):
        return {"boolValue": v}
    if isinstance(v, int):
        return {"intValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    if isinstance(v, list) and all(isinstance(x, str) for x in v):
        return {"arrayValue": {"values": [{"stringValue": x} for x in v]}}
    if isinstance(v, str):
        return {"stringValue": v}
    return {"stringValue": json.dumps(v, ensure_ascii=False)}


def _span(trace_id: str, parent: str | None, name: str, start: int, end: int,
          attrs: dict[str, Any]) -> dict[str, Any]:
    return {
        "traceId": trace_id, "spanId": secrets.token_hex(8),
        **({"parentSpanId": parent} if parent else {}),
        "name": name, "kind": 1,
        "startTimeUnixNano": str(start), "endTimeUnixNano": str(max(end, start)),
        "attributes": [{"key": k, "value": _value(v)} for k, v in attrs.items() if v is not None],
    }


def build(rec: Recorder, turn: Turn, environment: str) -> dict[str, Any]:
    """The OTLP body: a root span for the request, a generation per model round, a span per
    tool call, and zero-length events for a guard block and dropped citations."""
    end = time.time_ns()
    trace_id = (turn.message_id or secrets.token_hex(16)).replace("-", "")
    root_id = secrets.token_hex(8)
    meta = next((d for _, e, d in rec.events if e == "meta"), {})
    usage = next((d for _, e, d in rec.events if e == "usage"), {})
    error = next((d for _, e, d in rec.events if e == "error"), None)
    canary = any(e == "step" and d.get("kind") == "guard"
                 and (d.get("summary") or {}).get("blocked") == "canary"
                 for _, e, d in rec.events)
    restarts = [d for _, e, d in rec.events if e == "step" and d.get("status") == "restart"]

    tags = [t for t, on in [("cached", meta.get("cached")), ("replay", meta.get("replay")),
                            ("fallback", usage.get("fallback") or restarts),
                            ("error", error), ("severe", canary)] if on]
    level = "ERROR" if canary else "WARNING" if error else None
    root = {
        "langfuse.trace.name": "chat",
        "langfuse.session.id": turn.conversation_id,
        "langfuse.trace.input": mask(turn.message),
        "langfuse.trace.output": mask(turn.answer),
        "langfuse.trace.tags": tags,
        "langfuse.observation.level": level,
        "langfuse.observation.status_message": (
            "canary leak blocked" if canary else error and error.get("code")),
        "langfuse.trace.metadata.prompt_version": meta.get("prompt_version"),
        "langfuse.trace.metadata.error": error and error.get("code"),
        "langfuse.trace.metadata.limit": error and error.get("limit"),
        "langfuse.trace.metadata.model": usage.get("model"),
        "langfuse.trace.metadata.ttft_ms": usage.get("ttft_ms"),
        "langfuse.trace.metadata.total_ms": usage.get("total_ms"),
        "langfuse.trace.metadata.cached_at": meta.get("cached_at"),
    }
    spans: list[dict[str, Any]] = []
    starts: dict[tuple[str, str], tuple[int, dict[str, Any]]] = {}
    for t, event, data in rec.events:
        if event != "step":
            continue
        kind, status, sid = data.get("kind"), data.get("status"), data.get("step_id", "")
        if status == "start":
            starts[(sid, kind if kind == "llm" else "tool")] = (t, data)
        elif kind == "llm" and status == "end":
            t0, _ = starts.pop((sid, "llm"), (t, data))
            summary = data.get("summary") or {}
            round_usage = summary.get("usage") or {}
            spans.append(_span(trace_id, root_id, data.get("name", "llm"), t0, t, {
                "langfuse.observation.type": "generation",
                "gen_ai.request.model": summary.get("model"),
                "gen_ai.usage.input_tokens": round_usage.get("input_tokens"),
                "gen_ai.usage.output_tokens": round_usage.get("output_tokens"),
                "langfuse.observation.metadata.tool_calls": summary.get("tool_calls"),
            }))
        elif kind == "tool_result":
            t0, start = starts.pop((sid, "tool"), (t, data))
            spans.append(_span(trace_id, root_id, data.get("name", "tool"), t0, t, {
                "langfuse.observation.input": json.dumps(mask(start.get("args")),
                                                         ensure_ascii=False),
                "langfuse.observation.output": json.dumps(mask(data.get("summary")),
                                                          ensure_ascii=False),
            }))
        elif status == "restart" or kind == "guard":
            summary = data.get("summary") or {}
            spans.append(_span(trace_id, root_id, "model_switch" if status == "restart"
                               else "canary_blocked", t, t, {
                "langfuse.observation.type": "event",
                "langfuse.observation.level": "WARNING" if status == "restart" else "ERROR",
                "langfuse.observation.metadata.failed": summary.get("failed"),
                "langfuse.observation.metadata.to": summary.get("to"),
                "langfuse.observation.metadata.reason": summary.get("reason"),
            }))
    if turn.dropped:
        spans.append(_span(trace_id, root_id, "citation_dropped", end, end, {
            "langfuse.observation.type": "event", "langfuse.observation.level": "WARNING",
            "langfuse.observation.metadata.chunk_ids": turn.dropped,
        }))
    spans.insert(0, {**_span(trace_id, None, "chat_turn", rec.started_ns, end, root),
                     "spanId": root_id})
    return {"resourceSpans": [{
        "resource": {"attributes": [
            {"key": "service.name", "value": {"stringValue": "portfolio-agent"}},
            {"key": "deployment.environment", "value": {"stringValue": environment}},
        ]},
        "scopeSpans": [{"scope": {"name": "portfolio_agent"}, "spans": spans}],
    }]}


@dataclass(frozen=True)
class Exporter:
    endpoint: str
    auth: str
    environment: str

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Exporter | None":
        env = dict(os.environ) if env is None else env
        public, secret = env.get("LANGFUSE_PUBLIC_KEY"), env.get("LANGFUSE_SECRET_KEY")
        if not public or not secret:
            return None
        # Only the origin counts: a URL copied from the Langfuse UI carries a /project/ path.
        url = urlparse(env.get("LANGFUSE_HOST") or "https://cloud.langfuse.com")
        return cls(
            endpoint=f"{url.scheme}://{url.netloc}/api/public/otel/v1/traces",
            auth=base64.b64encode(f"{public}:{secret}".encode()).decode(),
            environment=env.get("VERCEL_ENV") or "local",
        )

    async def send(self, body: dict[str, Any], client: httpx.AsyncClient) -> bool:
        try:
            r = await client.post(self.endpoint, json=body, timeout=TIMEOUT, headers={
                "Authorization": f"Basic {self.auth}", "Content-Type": "application/json"})
            if r.status_code >= 300:
                log.warning("langfuse export: HTTP %s %s", r.status_code, r.text[:200])
            return r.status_code < 300
        except httpx.HTTPError as e:  # a trace is never worth a failed request
            log.warning("langfuse export failed: %s", e)
            return False


async def export(rec: Recorder, turn: Turn, exporter: "Exporter | None",
                 client: httpx.AsyncClient) -> None:
    body = build(rec, turn, exporter.environment if exporter else "local")
    if any(s["name"] == "canary_blocked"
           for s in body["resourceSpans"][0]["scopeSpans"][0]["spans"]):
        log.critical("SEVERE: canary leak blocked in conversation %s, message %s",
                     turn.conversation_id, turn.message_id)
    if exporter is not None:
        await exporter.send(body, client)
