"""The tool registry (docs/06-agent-design.md, section 3).

Each tool declares its parameters as a Pydantic model, so the schema the model sees and the
validation of what it sends back come from one place. A call never raises into the loop: a
bad name, bad arguments or a failing handler come back as a structured error the model can
read (section 1), and `ToolResult.invalid_args` tells the loop which of them count toward the
one retry the spec allows for invalid arguments.

Every result has two views: `model_view` is the text the model reads, `trace_view` is what the
visitor sees in the trace panel (scores, timings, candidates). Keeping them apart keeps trace
data out of the model's context.
"""

import inspect
import json
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

Effect = Literal["read", "draft"]  # no tool sends, deletes or changes anything outside


@dataclass(frozen=True)
class ToolResult:
    model_view: str
    trace_view: dict[str, Any]
    chunk_ids: frozenset[str] = frozenset()  # what the answer may cite after this call
    error: str | None = None  # a code, set when the call did not run
    invalid_args: bool = False


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    params: type[BaseModel]
    # A coroutine for a tool that calls models itself (match_job); the loop awaits it.
    handler: Callable[[BaseModel, Any], ToolResult | Awaitable[ToolResult]]
    effect: Effect = "read"
    # Extra JSON schema merged into the generated one, for values only known at runtime,
    # such as the enum of record ids (built at ingestion, section 3).
    schema_extra: Callable[[Any], dict[str, Any]] | None = None
    # Whether the model is offered the tool in the next round. A round costs a whole prompt.
    offered: Callable[[Any], bool] | None = None

    def schema(self, ctx: Any) -> dict[str, Any]:
        params = self.params.model_json_schema()
        params.pop("title", None)
        for prop in params.get("properties", {}).values():
            prop.pop("title", None)
        if self.schema_extra:
            for name, extra in self.schema_extra(ctx).items():
                params["properties"][name].update(extra)
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": params},
        }


def _error(code: str, message: str, name: str, started: float, **kw: Any) -> ToolResult:
    body = json.dumps({"error": code, "message": message}, ensure_ascii=False)
    trace = {"error": code, "message": message, "tool": name, "duration_ms": _ms(started)}
    return ToolResult(body, trace, error=code, **kw)


def _ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _finish(result: ToolResult, name: str, started: float) -> ToolResult:
    trace = {**result.trace_view, "tool": name, "duration_ms": _ms(started)}
    return ToolResult(result.model_view, trace, result.chunk_ids, result.error)


@dataclass
class Registry:
    tools: dict[str, Tool] = field(default_factory=dict)

    @classmethod
    def of(cls, tools: Iterable[Tool]) -> "Registry":
        registry = cls()
        for tool in tools:
            if tool.name in registry.tools:
                raise ValueError(f"duplicate tool {tool.name}")
            registry.tools[tool.name] = tool
        return registry

    def schemas(self, ctx: Any) -> list[dict[str, Any]]:
        return [tool.schema(ctx) for tool in self.tools.values()
                if tool.offered is None or tool.offered(ctx)]

    async def acall(self, name: str, raw_args: str | dict[str, Any], ctx: Any) -> ToolResult:
        """`call`, for the loop: a tool that is a coroutine is awaited here."""
        started = time.perf_counter()
        result = self.call(name, raw_args, ctx)
        if not inspect.isawaitable(result):
            return result
        try:
            return _finish(await result, name, started)
        except Exception as e:  # a failing tool is reported to the model, not raised
            return _error("tool_failed", f"{type(e).__name__}: {e}", name, started)

    def call(self, name: str, raw_args: str | dict[str, Any], ctx: Any) -> Any:
        """A ToolResult, or for a coroutine tool something to await (see acall)."""
        started = time.perf_counter()
        tool = self.tools.get(name)
        if tool is None:
            known = ", ".join(self.tools)
            return _error("unknown_tool", f"No tool '{name}'. Tools: {known}", name, started,
                          invalid_args=True)
        try:
            data = json.loads(raw_args or "{}") if isinstance(raw_args, str) else raw_args
            args = tool.params.model_validate(data)
            self._check_enums(tool, args, ctx)
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            return _error("invalid_args", str(e), name, started, invalid_args=True)
        try:
            result = tool.handler(args, ctx)
        except Exception as e:  # a failing tool is reported to the model, not raised
            return _error("tool_failed", f"{type(e).__name__}: {e}", name, started)
        return result if inspect.isawaitable(result) else _finish(result, name, started)

    @staticmethod
    def _check_enums(tool: Tool, args: BaseModel, ctx: Any) -> None:
        """Runtime enums are part of the schema, so a value outside them is invalid too."""
        if not tool.schema_extra:
            return
        for name, extra in tool.schema_extra(ctx).items():
            allowed = extra.get("enum")
            if allowed is not None and getattr(args, name) not in allowed:
                raise ValueError(f"{name}: '{getattr(args, name)}' is not one of {allowed}")
