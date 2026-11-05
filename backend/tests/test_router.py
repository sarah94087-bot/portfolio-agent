"""The router and its circuit breaker, with fake models and a fake clock."""

import asyncio

import pytest

from portfolio_agent.providers.base import Finish, NeedsFallback, TextDelta
from portfolio_agent.providers.openai_compat import ProviderError
from portfolio_agent.providers.router import (
    DAY_FALLBACK,
    MINUTE,
    AllModelsFailed,
    Restart,
    Router,
)


class Fake:
    """Fails with `fail` (after `after` deltas), or answers with its name."""

    def __init__(self, name, fail=None, after=0, retry_after=None):
        self.name, self.fail, self.after, self.retry_after = name, fail, after, retry_after
        self.calls = 0

    async def stream(self, messages, tools):
        self.calls += 1
        for i in range(self.after):
            yield TextDelta(f"{self.name}-{i} ")
        if self.fail:
            raise ProviderError(self.fail, "x", self.retry_after)
        yield TextDelta(self.name)
        yield Finish(self.name)


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def run(turn):
    async def go():
        return [e async for e in turn.stream([], [])]
    return asyncio.run(go())


def text(events):
    return "".join(e.text for e in events if isinstance(e, TextDelta))


def test_the_primary_answers_when_it_is_healthy():
    a, b = Fake("a"), Fake("b")
    assert text(run(Router([a, b]).for_turn())) == "a" and b.calls == 0


def test_a_minute_limit_skips_the_model_for_a_minute_then_it_is_back():
    clock = Clock()
    a, b = Fake("a", "rate_minute"), Fake("b")
    router = Router([a, b], clock)
    assert text(run(router.for_turn())) == "b"
    assert text(run(router.for_turn())) == "b" and a.calls == 1  # no call spent on a
    clock.t += MINUTE + 1
    a.fail = None
    assert text(run(router.for_turn())) == "a"


def test_a_day_limit_waits_for_retry_after_or_an_hour():
    clock = Clock()
    a, b = Fake("a", "rate_day", retry_after=5000), Fake("b")
    router = Router([a, b], clock)
    run(router.for_turn())
    assert router.closed_until["a"] == 1000 + 5000
    c = Fake("c", "rate_day")
    router2 = Router([c, Fake("d")], clock)
    run(router2.for_turn())
    assert router2.closed_until["c"] == 1000 + DAY_FALLBACK


def test_a_failure_before_any_text_is_invisible():
    events = run(Router([Fake("a", "unavailable"), Fake("b")]).for_turn())
    assert not any(isinstance(e, Restart) for e in events) and text(events) == "b"


def test_a_failure_mid_answer_restarts_the_round_on_the_next_model():
    events = run(Router([Fake("a", "unavailable", after=2), Fake("b")]).for_turn())
    restart = [e for e in events if isinstance(e, Restart)]
    assert restart == [Restart("a", "b", "unavailable")]
    i = events.index(restart[0])
    assert text(events[:i]) == "a-0 a-1 " and text(events[i:]) == "b"


def test_when_every_model_hit_its_limit_the_error_is_quota_exhausted():
    router = Router([Fake("a", "rate_minute"), Fake("b", "rate_day")], Clock())
    with pytest.raises(AllModelsFailed) as e:
        run(router.for_turn())
    assert e.value.code == "quota_exhausted"
    with pytest.raises(AllModelsFailed) as e:  # both are closed now, so no call is made
        run(router.for_turn())
    assert e.value.code == "quota_exhausted" and e.value.attempts == []


def test_when_a_model_is_down_the_error_is_provider_unavailable():
    with pytest.raises(AllModelsFailed) as e:
        run(Router([Fake("a", "unavailable"), Fake("b", "rate_minute")]).for_turn())
    assert e.value.code == "provider_unavailable"


def test_a_bad_request_is_raised_not_routed():
    b = Fake("b")
    with pytest.raises(ProviderError):
        run(Router([Fake("a", "bad_request"), b]).for_turn())
    assert b.calls == 0


def test_fall_back_drops_the_model_for_this_turn_only():
    a, b = Fake("a"), Fake("b")
    router = Router([a, b])
    turn = router.for_turn()
    run(turn)
    turn.fall_back("invalid tool call")
    assert text(run(turn)) == "b"
    assert text(run(router.for_turn())) == "a"  # the next turn starts from the primary
    last = router.for_turn()
    run(last)
    last.fall_back("x")
    run(last)
    with pytest.raises(NeedsFallback):  # no model is left after b
        last.fall_back("again")


def test_from_env_follows_the_adr_order_without_duplicates():
    import httpx

    from portfolio_agent.providers.router import from_env

    env = {"GROQ_API_KEY": "k", "GROQ_MODEL": "openai/gpt-oss-120b",
           "GROQ_FALLBACK_MODELS": "qwen/qwen3.8-27b, openai/gpt-oss-20b,openai/gpt-oss-120b"}
    router = from_env(httpx.AsyncClient(), env)
    assert [m.name for m in router.models] == [
        "groq/openai/gpt-oss-120b", "groq/qwen/qwen3.8-27b", "groq/openai/gpt-oss-20b"]
    with pytest.raises(ValueError):
        from_env(httpx.AsyncClient(), {})
