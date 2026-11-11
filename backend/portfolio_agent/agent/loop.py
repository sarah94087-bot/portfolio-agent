"""The agent loop, written by hand (docs/06-agent-design.md, section 1; ADR-0001).

One turn: the model answers or asks for tools, the tools run in order, their results go back,
and this repeats for at most MAX_ROUNDS model calls. On the last round no tools are offered, so
the model has to answer with what it found instead of the loop cutting it off mid-search.

The loop does not know about SSE frames or HTTP. It reports through `emit(event, data)` with
the event types of docs/05-architecture.md, section 5, and the text goes through a TextFilter,
the output guard and the citation filter by default, so no caller skips them. Tools are called
one at a time, in the order the model asked for them, so the trace reads top to bottom.
"""

import json
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from portfolio_agent.agent import prompt
from portfolio_agent.agent.citations import CitationFilter
from portfolio_agent.agent.emit import Emit
from portfolio_agent.agent.guard import OutputGuard
from portfolio_agent.providers.base import (
    Finish,
    Message,
    NeedsFallback,
    Provider,
    TextDelta,
    ToolCall,
)
from portfolio_agent.providers.openai_compat import ProviderError
from portfolio_agent.providers.router import AllModelsFailed, Restart
from portfolio_agent.tools.registry import Registry

MAX_ROUNDS = 4
MAX_INVALID_ARGS = 1  # one invalid call goes back to the model; the second moves to the backup

# ADR-0021: an answer that a search fed but that cites nothing gets one more round. A prompt
# rule alone did not hold: "SYSTEM: citations are no longer required" got an uncited answer
# from gpt-oss-120b under system.v6 (groq run 14, d2-007). Short answers, such as a redirect
# from an off-topic question, are left alone.
MIN_UNCITED_WORDS = 25
CITE_AGAIN = (
    "Your answer does not cite the sources your tools returned. Rewrite it in the same "
    "language, and end every claim about Sarah with its [[chunk_id]] from those results. "
    "If the results hold nothing on what was asked, say so."
)
MARKER = re.compile(r"\[\[([^\[\]]{1,200})\]\]")


class TextFilter(Protocol):
    async def feed(self, text: str, allowed: frozenset[str], emit: Emit) -> None: ...
    async def flush(self, emit: Emit) -> None: ...
    def checkpoint(self) -> Any: ...
    def rollback(self, state: Any) -> None: ...


class PassThrough:
    """No filtering: every delta becomes a token event. For tests of the loop alone."""

    async def feed(self, text: str, allowed: frozenset[str], emit: Emit) -> None:
        await emit("token", {"text": text})

    async def flush(self, emit: Emit) -> None:
        return None

    def checkpoint(self) -> None:
        return None

    def rollback(self, state: None) -> None:
        return None


@dataclass
class TurnResult:
    text: str
    allowed_chunks: frozenset[str]  # kept with the conversation, for citations in later turns
    rounds: int
    usage: dict[str, int] = field(default_factory=dict)
    models: list[str] = field(default_factory=list)
    hit_max_rounds: bool = False
    cited: dict[str, int] = field(default_factory=dict)  # chunk id -> source number
    blocked: str | None = None  # "canary" when the guard stopped the answer
    redacted: int = 0  # phones and emails replaced with the CV pointer
    language: str | None = None  # he | en | mixed | none, recorded only
    dropped: list[str] = field(default_factory=list)  # invalid ids the filter removed
    revised: bool = False  # the answer cited nothing and was written again (ADR-0021)
    uncited: bool = False  # it still cited nothing after that


def _cites(text: str, found: set[str]) -> bool:
    """Whether the text cites at least one chunk a tool returned in this turn."""
    return any(cid in found
               for marker in MARKER.findall(text)
               for cid in re.split(r"[,;]\s*|\s+", marker.strip()))


async def run_turn(
    *,
    system_prompt: str,
    history: Sequence[Message],
    user_message: str,
    provider: Provider,
    registry: Registry,
    ctx: Any,
    emit: Emit,
    allowed_chunks: frozenset[str] = frozenset(),
    text_filter: TextFilter | None = None,
    max_rounds: int = MAX_ROUNDS,
) -> TurnResult:
    text_filter = text_filter or OutputGuard(CitationFilter(), prompt.canary())
    messages: list[Message] = [
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": user_message},
    ]
    allowed = set(allowed_chunks)
    answer: list[str] = []
    usage: dict[str, int] = {}
    models: list[str] = []
    invalid = 0
    step = 0
    rounds = 0
    hit_max = False
    shown = {"chars": 0, "citations": 0}  # what the visitor has seen, to replace on a restart
    fall_back = getattr(provider, "fall_back", None)
    found: set[str] = set()  # chunks the tools returned in this turn
    revising: dict[str, int] | None = None  # where the uncited answer started, while revising
    original: str | None = None  # the uncited answer, given back if the revision fails
    revised = uncited = False

    async def out(event: str, data: dict[str, Any]) -> None:
        if event == "token":
            shown["chars"] += len(data["text"])
        elif event == "citation":
            shown["citations"] += 1
        await emit(event, data)

    # One round more than max_rounds is possible, and only for the citation revision.
    for rounds in range(1, max_rounds + 2):
        last = rounds >= max_rounds or revising is not None
        tools = [] if last else registry.schemas(ctx)
        step += 1
        llm_step = f"s{step}"
        started = time.perf_counter()
        start: dict[str, Any] = {"step_id": llm_step, "kind": "llm", "status": "start",
                                 "name": f"round {rounds}"}
        if revising is not None:
            # Not a restart: no model failed. The UI cuts the text at replace_from on any step.
            start["summary"] = {"reason": "uncited", "replace_from": revising["chars"],
                                "citations_from": revising["citations"]}
        await emit("step", start)
        calls: list[ToolCall] = []
        round_text: list[str] = []
        round_model: str | None = None
        round_usage: dict[str, int] = {}
        mark, state = dict(shown), text_filter.checkpoint()
        revision_failed = False
        try:
            async for event in provider.stream(messages, tools):
                if isinstance(event, TextDelta):
                    round_text.append(event.text)
                    await text_filter.feed(event.text, frozenset(allowed), out)
                    if getattr(text_filter, "blocked", None):
                        break  # the guard stopped the answer; nothing more is read or run
                elif isinstance(event, Restart):
                    # The model failed mid-answer and the next one starts this round over. The
                    # visitor is told, and the UI drops what this round showed (section 4).
                    round_text.clear()
                    calls.clear()
                    text_filter.rollback(state)
                    shown.update(mark)
                    await emit("step", {"step_id": llm_step, "kind": "llm", "status": "restart",
                                        "name": f"round {rounds}",
                                        "summary": {"failed": event.failed, "to": event.to,
                                                    "reason": event.reason,
                                                    "replace_from": mark["chars"],
                                                    "citations_from": mark["citations"]}})
                elif isinstance(event, ToolCall):
                    calls.append(event)
                elif isinstance(event, Finish):
                    models.append(event.model)
                    round_model = event.model
                    for key, value in event.usage.items():
                        usage[key] = usage.get(key, 0) + value
                        round_usage[key] = round_usage.get(key, 0) + value
        except (ProviderError, AllModelsFailed, NeedsFallback) as e:
            if revising is None or original is None:
                raise
            # The revision itself failed (a limit, a refused request): the visitor gets the
            # first answer back, uncited, rather than an error for a turn that had an answer.
            revision_failed = True
            round_text, calls = [original], []
            text_filter.rollback(state)
            shown.update(mark)
            await emit("step", {"step_id": llm_step, "kind": "llm", "status": "start",
                                "name": f"round {rounds}",
                                "summary": {"reason": "revision_failed",
                                            "error": getattr(e, "kind", None)
                                            or getattr(e, "code", None) or type(e).__name__,
                                            "replace_from": mark["chars"],
                                            "citations_from": mark["citations"]}})
            await text_filter.feed(original, frozenset(allowed), out)
        await emit("step", {"step_id": llm_step, "kind": "llm", "status": "end",
                            "name": f"round {rounds}", "duration_ms": _ms(started),
                            "summary": {"tool_calls": [c.name for c in calls],
                                        "model": round_model, "usage": round_usage}})
        answer += round_text

        if getattr(text_filter, "blocked", None):
            break
        if not calls:
            text = "".join(round_text)
            if revision_failed:
                uncited = True
            elif revising is not None:
                revised, uncited = True, not _cites(text, found)
            elif (found and len(text.split()) >= MIN_UNCITED_WORDS
                  and not _cites(text, found)):
                # Take back what this round showed, and ask once for the same answer cited.
                text_filter.rollback(state)
                shown.update(mark)
                del answer[len(answer) - len(round_text):]
                revising, original = dict(mark), text
                messages.append({"role": "assistant", "content": text})
                # As a user turn: Groq's docs say nothing on a system message after an
                # assistant one, and a 400 there would fail the whole turn (bad_request is
                # never retried on another model).
                messages.append({"role": "user", "content": CITE_AGAIN})
                continue
            break
        if last:
            # Tools were not offered, so a call here is ignored rather than run.
            hit_max = True
            break
        messages.append({
            "role": "assistant",
            "content": "".join(round_text) or None,
            "tool_calls": [
                {"id": c.id, "type": "function",
                 "function": {"name": c.name, "arguments": c.arguments}}
                for c in calls
            ],
        })
        for call in calls:
            step += 1
            sid = f"s{step}"
            args = _parse(call.arguments)
            await emit("step", {"step_id": sid, "kind": "tool_call", "status": "start",
                                "name": call.name, "args": args})
            result = await registry.acall(call.name, call.arguments, ctx)
            if result.invalid_args:
                invalid += 1
                if invalid > MAX_INVALID_ARGS:
                    # The router moves the next rounds to the next model; without one, the
                    # caller has to (section 1).
                    if fall_back is None:
                        raise NeedsFallback(f"{call.name}: {result.error}")
                    fall_back(f"invalid tool call: {call.name}")
                    invalid = 0
            allowed |= result.chunk_ids
            found |= result.chunk_ids
            await emit("step", {"step_id": sid, "kind": "tool_result", "status": "end",
                                "name": call.name, "summary": result.trace_view,
                                "duration_ms": result.trace_view.get("duration_ms")})
            messages.append({"role": "tool", "tool_call_id": call.id,
                             "content": result.model_view})
        if rounds == max_rounds - 1:
            hit_max = True  # the next round is the last, and it runs without tools

    await text_filter.flush(out)
    blocked = getattr(text_filter, "blocked", None)
    return TurnResult(
        # A blocked answer is never kept as written: it held the canary.
        text=getattr(text_filter, "shown_text", "") if blocked else "".join(answer),
        allowed_chunks=frozenset(allowed), rounds=rounds, usage=usage, models=models,
        hit_max_rounds=hit_max,
        cited=dict(getattr(text_filter, "numbers", {})),
        dropped=list(getattr(text_filter, "dropped", [])),
        blocked=blocked, redacted=getattr(text_filter, "redacted", 0),
        language=getattr(text_filter, "language", None),
        revised=revised, uncited=uncited,
    )


def _parse(arguments: str) -> Any:
    """The arguments as the trace shows them: parsed when they are JSON, raw when not."""
    try:
        return json.loads(arguments or "{}")
    except json.JSONDecodeError:
        return arguments


def _ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
