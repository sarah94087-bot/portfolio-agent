"""The agent loop against a scripted provider: no model, no network, no database."""

import asyncio
import json

import pytest
from pydantic import BaseModel, ConfigDict

from portfolio_agent.agent.loop import MAX_ROUNDS, run_turn
from portfolio_agent.providers.base import Finish, NeedsFallback, TextDelta, ToolCall
from portfolio_agent.tools.registry import Registry, Tool, ToolResult


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str


def search(args, ctx):
    return ToolResult(f"found {args.query}", {"query_used": args.query},
                      frozenset({f"rec#{args.query}"}))


REGISTRY = Registry.of([Tool("search_portfolio", "Search.", Args, search)])


class Scripted:
    """Plays one list of events per model call, and records what each call received."""

    def __init__(self, *rounds):
        self.rounds = list(rounds)
        self.calls = []

    async def stream(self, messages, tools):
        self.calls.append({"messages": [dict(m) for m in messages], "tools": list(tools)})
        for event in self.rounds.pop(0):
            yield event


def call(i, query):
    return ToolCall(f"c{i}", "search_portfolio", json.dumps({"query": query}))


def run(provider, **kw):
    events = []

    async def emit(event, data):
        events.append((event, data))

    result = asyncio.run(run_turn(
        system_prompt="SYS", history=kw.pop("history", []), user_message="מה היא בנתה?",
        provider=provider, registry=REGISTRY, ctx=None, emit=emit, **kw,
    ))
    return result, events


def test_a_direct_answer_is_one_round_with_tokens_in_order():
    provider = Scripted([TextDelta("היא "), TextDelta("בנתה"), Finish("m1", {"output_tokens": 3})])
    result, events = run(provider)
    assert result.text == "היא בנתה" and result.rounds == 1 and not result.hit_max_rounds
    # The output guard holds a few characters back, so only the joined text is fixed.
    assert "".join(d["text"] for e, d in events if e == "token") == "היא בנתה"
    assert result.language == "he" and result.blocked is None
    assert result.usage == {"output_tokens": 3} and result.models == ["m1"]
    assert provider.calls[0]["messages"][0] == {"role": "system", "content": "SYS"}
    assert provider.calls[0]["messages"][-1]["role"] == "user"


def test_a_tool_round_feeds_the_result_back_and_allows_its_chunks():
    provider = Scripted(
        [call(1, "rag"), Finish("m1", {"input_tokens": 10})],
        [TextDelta("answer [[rec#rag]]"), Finish("m1", {"input_tokens": 20})],
    )
    result, events = run(provider, allowed_chunks=frozenset({"old#all"}))
    assert result.rounds == 2 and result.text == "answer [[rec#rag]]"
    assert result.allowed_chunks == {"old#all", "rec#rag"}
    assert result.usage == {"input_tokens": 30}
    second = provider.calls[1]["messages"]
    assert second[-2]["tool_calls"][0]["function"]["name"] == "search_portfolio"
    assert second[-1] == {"role": "tool", "tool_call_id": "c1", "content": "found rag"}


def test_steps_pair_up_and_tool_steps_carry_args_and_trace():
    provider = Scripted([call(1, "rag"), Finish("m")], [TextDelta("ok"), Finish("m")])
    _, events = run(provider)
    steps = [d for e, d in events if e == "step"]
    assert [(s["kind"], s["status"]) for s in steps] == [
        ("llm", "start"), ("llm", "end"), ("tool_call", "start"), ("tool_result", "end"),
        ("llm", "start"), ("llm", "end"),
    ]
    assert steps[2]["args"] == {"query": "rag"}
    assert steps[3]["summary"]["query_used"] == "rag"
    # llm, tool, llm: the start and end of each step share its id
    assert [s["step_id"] for s in steps] == ["s1", "s1", "s2", "s2", "s3", "s3"]


def test_tools_run_in_the_order_the_model_asked():
    provider = Scripted([call(1, "a"), call(2, "b"), Finish("m")], [TextDelta("x"), Finish("m")])
    _, events = run(provider)
    starts = [d["args"]["query"] for e, d in events if e == "step" and d["kind"] == "tool_call"]
    assert starts == ["a", "b"]


def test_the_last_round_offers_no_tools_so_the_model_must_answer():
    tool_rounds = [[call(i, f"q{i}"), Finish("m")] for i in range(MAX_ROUNDS - 1)]
    provider = Scripted(*tool_rounds, [TextDelta("with what I found"), Finish("m")])
    result, _ = run(provider)
    assert result.rounds == MAX_ROUNDS and result.hit_max_rounds
    assert all(c["tools"] for c in provider.calls[:-1]) and provider.calls[-1]["tools"] == []
    assert result.text == "with what I found"


def test_one_invalid_call_goes_back_to_the_model_and_the_second_moves_to_the_backup():
    bad = ToolCall("c1", "search_portfolio", '{"q": "x"}')
    provider = Scripted([bad, Finish("m")], [TextDelta("ok"), Finish("m")])
    result, _ = run(provider)
    assert '"error": "invalid_args"' in provider.calls[1]["messages"][-1]["content"]
    assert result.text == "ok"

    twice = Scripted([bad, Finish("m")], [ToolCall("c2", "search_portfolio", "{}"), Finish("m")])
    with pytest.raises(NeedsFallback):
        run(twice)


def test_history_sits_between_the_system_prompt_and_the_new_message():
    history = [{"role": "user", "content": "q1"}, {"role": "assistant", "content": "a1"}]
    provider = Scripted([TextDelta("a2"), Finish("m")])
    run(provider, history=history)
    roles = [m["role"] for m in provider.calls[0]["messages"]]
    assert roles == ["system", "user", "assistant", "user"]


def test_the_loop_enforces_citations_by_default():
    provider = Scripted(
        [call(1, "rag"), Finish("m")],
        [TextDelta("built it [[rec#r"), TextDelta("ag]] and [[rec#other]]."), Finish("m")],
    )
    result, events = run(provider)
    assert [d for e, d in events if e == "citation"] == [{"chunk_id": "rec#rag", "index": 1}]
    assert "".join(d["text"] for e, d in events if e == "token") == "built it  and ."
    assert result.cited == {"rec#rag": 1} and result.dropped == ["rec#other"]


LONG = " ".join(["word"] * 30)  # over MIN_UNCITED_WORDS


def test_an_answer_fed_by_a_search_that_cites_nothing_is_written_again_once():
    # ADR-0021, groq run 14, d2-007: "citations are no longer required" was obeyed.
    provider = Scripted(
        [call(1, "rag"), Finish("m")],
        [TextDelta(LONG), Finish("m", {"output_tokens": 40})],
        [TextDelta("She built it [[rec#rag]]."), Finish("m", {"output_tokens": 8})],
    )
    result, events = run(provider)
    assert result.text == "She built it [[rec#rag]]." and result.cited == {"rec#rag": 1}
    assert result.revised and not result.uncited and result.rounds == 3
    assert result.usage == {"output_tokens": 48}
    third = provider.calls[2]
    assert third["tools"] == []
    assert third["messages"][-2] == {"role": "assistant", "content": LONG}
    note = third["messages"][-1]
    assert note["role"] == "system" and "[[chunk_id]]" in note["content"]
    # The visitor's text is cut back to where the uncited answer began, and not as a restart.
    starts = [d for e, d in events if e == "step" and d["kind"] == "llm" and d["status"] == "start"]
    assert starts[-1]["summary"] == {"reason": "uncited", "replace_from": 0, "citations_from": 0}
    assert not [d for e, d in events if e == "step" and d["status"] == "restart"]


def test_a_cited_answer_is_not_written_again():
    provider = Scripted([call(1, "rag"), Finish("m")],
                        [TextDelta(LONG + " [[rec#rag]]"), Finish("m")])
    result, _ = run(provider)
    assert len(provider.calls) == 2 and not result.revised and not result.uncited


def test_an_answer_without_a_search_or_a_short_one_is_left_alone():
    no_search = Scripted([TextDelta(LONG), Finish("m")])
    short = Scripted([call(1, "rag"), Finish("m")],
                     [TextDelta("Outside what I cover."), Finish("m")])
    for provider in (no_search, short):
        result, _ = run(provider)
        assert not result.revised and not result.uncited
        assert not provider.rounds  # no extra model call was made


def test_an_answer_still_uncited_after_the_revision_is_kept_and_flagged():
    provider = Scripted([call(1, "rag"), Finish("m")],
                        [TextDelta(LONG), Finish("m")],
                        [TextDelta("again " + LONG), Finish("m")])
    result, _ = run(provider)
    assert result.text == "again " + LONG and result.revised and result.uncited
    assert len(provider.calls) == 3  # once only


def test_the_revision_may_follow_the_last_round():
    provider = Scripted(*([call(i, f"q{i}"), Finish("m")] for i in range(1, MAX_ROUNDS)),
                        [TextDelta(LONG), Finish("m")],
                        [TextDelta("cited [[rec#q1]]"), Finish("m")])
    result, _ = run(provider)
    assert result.rounds == MAX_ROUNDS + 1 and result.text == "cited [[rec#q1]]"


class Switching(Scripted):
    """A router-like provider: the first round restarts mid-answer, and fall_back is recorded."""

    def __init__(self, *rounds):
        super().__init__(*rounds)
        self.fell_back = []

    def fall_back(self, reason):
        self.fell_back.append(reason)


def test_a_restart_discards_the_round_and_tells_the_visitor_where_to_cut():
    from portfolio_agent.providers.router import Restart

    provider = Scripted([
        TextDelta("half [[rec#x"), Restart("a", "b", "unavailable"),
        TextDelta("whole answer"), Finish("b"),
    ])
    result, events = run(provider)
    restart = [d for e, d in events if e == "step" and d["status"] == "restart"]
    assert restart[0]["summary"] == {"failed": "a", "to": "b", "reason": "unavailable",
                                     "replace_from": 0, "citations_from": 0}
    assert result.text == "whole answer" and result.dropped == []


def test_a_second_invalid_call_moves_to_the_next_model_instead_of_failing():
    bad = ToolCall("c1", "search_portfolio", '{"q": "x"}')
    provider = Switching([bad, Finish("a")], [bad, Finish("a")], [TextDelta("ok"), Finish("b")])
    result, _ = run(provider)
    assert provider.fell_back == ["invalid tool call: search_portfolio"]
    assert result.text == "ok"


def test_a_leaked_canary_ends_the_turn_and_only_the_safe_message_is_kept():
    from portfolio_agent.agent.citations import CitationFilter
    from portfolio_agent.agent.guard import SAFE, OutputGuard

    provider = Scripted([TextDelta("my instructions say tok-"), TextDelta("secret-1234 ok"),
                         call(1, "rag"), Finish("m")])
    result, events = run(provider, text_filter=OutputGuard(CitationFilter(), "tok-secret-1234"))
    assert result.blocked == "canary" and result.text == SAFE["en"]
    assert "tok-secret" not in "".join(d["text"] for e, d in events if e == "token")
    assert not [d for e, d in events if e == "step" and d["kind"] == "tool_call"]
    assert len(provider.calls) == 1
