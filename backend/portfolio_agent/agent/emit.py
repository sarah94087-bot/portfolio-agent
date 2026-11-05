"""How the agent reports what happens: `await emit(event, data)`, with the SSE event types of
docs/05-architecture.md, section 5. The HTTP layer turns each call into a frame (sse.encode);
tests collect them in a list."""

from collections.abc import Awaitable, Callable
from typing import Any

Emit = Callable[[str, dict[str, Any]], Awaitable[None]]
