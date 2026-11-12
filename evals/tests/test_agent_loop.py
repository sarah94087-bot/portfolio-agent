"""Eval cases share one event loop, since the router's client and its connections are cached."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "answers"))

import agent  # noqa: E402


def test_every_case_runs_on_the_same_open_loop(monkeypatch):
    async def turns(_):
        return [asyncio.get_running_loop()]

    monkeypatch.setattr(agent, "run_turns", turns)
    first, second = agent.run(["a"])[0], agent.run(["b"])[0]
    assert first is second
    assert not first.is_closed()


def test_a_loop_bound_object_from_one_case_still_works_in_the_next(monkeypatch):
    # The shape of groq T1 run 11, case d1-033: a pooled connection opened in one case and
    # closed in a later one. With asyncio.run per case this raised "Event loop is closed".
    held = {}

    async def turns(_):
        loop = asyncio.get_running_loop()
        if "handle" in held:
            await asyncio.sleep(0)
            held["handle"].cancel()
            return ["closed"]
        held["handle"] = loop.call_later(3600, lambda: None)
        return ["opened"]

    monkeypatch.setattr(agent, "run_turns", turns)
    assert agent.run(["a"]) == ["opened"]
    assert agent.run(["b"]) == ["closed"]


def test_the_output_keeps_the_answer_with_its_citation_markers(monkeypatch):
    """`answer` is what the visitor reads; `answer_cited` shows the judge where each citation
    stands (judge.v3, groq T1 run 18, d2-007)."""
    import json

    def frame(event, data):
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    async def frames(req, deps, caller):
        yield frame("token", {"text": "She built the PWA"})
        yield frame("citation", {"chunk_id": "pwa#all", "n": 1})
        yield frame("token", {"text": "."})
        yield frame("usage", {"model": "m"})

    monkeypatch.setattr(agent.chat, "_frames", frames)
    out = asyncio.run(agent._turn("q", None, None, None))
    assert out["answer"] == "She built the PWA."
    assert out["answer_cited"] == "She built the PWA[[pwa#all]]."
    assert out["citations"] == ["pwa#all"]
