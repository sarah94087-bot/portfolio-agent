"""Server-sent events, protocol version 1 (docs/05-architecture.md, section 5).

Every event carries `v: 1`. The client ignores event types it does not know, so new types
can be added without breaking existing clients.
"""

import json
from typing import Any, Literal

PROTOCOL_VERSION = 1

EventType = Literal[
    "meta",
    "step",
    "token",
    "citation",
    "sources",
    "card",
    "contact_draft",
    "usage",
    "error",
    "done",
]

EVENT_TYPES: frozenset[str] = frozenset(EventType.__args__)


def encode(event: EventType, data: dict[str, Any] | None = None) -> str:
    """Encode one event as an SSE frame."""
    if event not in EVENT_TYPES:
        raise ValueError(f"unknown SSE event type: {event}")
    payload = {**(data or {}), "v": PROTOCOL_VERSION}
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {body}\n\n"
