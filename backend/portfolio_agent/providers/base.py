"""What the agent loop needs from a model provider (docs/06-agent-design.md, section 4).

One OpenAI-compatible client serves every provider (ADR-0005), so the loop speaks in OpenAI
chat messages and receives three kinds of events. The router between providers, with its
circuit breaker, implements the same interface and is the only thing the loop talks to.
"""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

Message = dict[str, Any]


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # JSON text, as the model wrote it; the registry validates it


@dataclass(frozen=True)
class Finish:
    model: str
    usage: dict[str, int] = field(default_factory=dict)  # input_tokens, output_tokens


Event = TextDelta | ToolCall | Finish


class Provider(Protocol):
    def stream(
        self, messages: Sequence[Message], tools: Sequence[dict[str, Any]], **options: Any
    ) -> AsyncIterator[Event]:
        """One model call. Text arrives as deltas, tool calls whole, and Finish comes last.
        `options` overrides request fields for this call (temperature, max_tokens, tool_choice)."""
        ...


class NeedsFallback(Exception):
    """The model sent invalid tool arguments twice in one turn. The router moves the turn to
    the backup model (docs/06-agent-design.md, section 1)."""
