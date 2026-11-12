"""The router and its circuit breaker, with fake models and a fake clock."""

import asyncio

import pytest

from portfolio_agent.providers.base import Finish, NeedsFallback, TextDelta
from portfolio_agent.providers.openai_compat import ProviderError
from portfolio_agent.providers.router import (
    DAY_FALLBACK,
    MAX_MINUTE_WAIT,
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


class Busy(Fake):
    """A minute limit on the first `times` calls, then a normal answer."""

    def __init__(self, name, retry_after, times=1):
        super().__init__(name)
        self.pause, self.times = retry_after, times

    async def stream(self, messages, tools):
        if self.calls < self.times:
            self.calls += 1
            raise ProviderError("rate_minute", "x", self.pause)
        async for event in super().stream(messages, tools):
            yield event


def sleeper():
    slept = []

    async def sleep(seconds):
        slept.append(seconds)
    return slept, sleep


def test_a_short_minute_limit_is_waited_out_on_the_same_model():
    slept, sleep = sleeper()
    a, b = Busy("a", 7.0), Fake("b")
    turn = Router([a, b], sleep=sleep).for_turn()
    assert text(run(turn)) == "a" and b.calls == 0
    assert slept == [7.0] and turn.switches == []


def test_a_long_minute_limit_moves_on_without_waiting():
    slept, sleep = sleeper()
    a, b = Busy("a", MAX_MINUTE_WAIT + 1), Fake("b")
    assert text(run(Router([a, b], sleep=sleep).for_turn())) == "b"
    assert slept == []


def test_a_minute_limit_without_retry_after_moves_on_without_waiting():
    slept, sleep = sleeper()
    a, b = Fake("a", "rate_minute"), Fake("b")
    assert text(run(Router([a, b], sleep=sleep).for_turn())) == "b"
    assert slept == []


def test_a_model_is_waited_for_once_in_a_call():
    slept, sleep = sleeper()
    a, b = Busy("a", 2.0, times=2), Fake("b")
    assert text(run(Router([a, b], sleep=sleep).for_turn())) == "b"
    assert slept == [2.0] and a.calls == 2


def test_the_waits_of_one_turn_are_capped_together():
    slept, sleep = sleeper()
    a, b, c = Busy("a", 7.0), Busy("b", 7.0), Fake("c")
    turn = Router([a, b, c], sleep=sleep).for_turn()
    assert text(run(turn)) == "a" and slept == [7.0]
    a.calls, a.times = 0, 1
    # A second 7 seconds would pass the cap: a is left at once, and b does not wait either.
    b.times = 0
    assert text(run(turn)) == "b" and slept == [7.0]


def test_a_limit_after_text_was_sent_does_not_wait():
    slept, sleep = sleeper()
    a, b = Fake("a", "rate_minute", after=1, retry_after=2.0), Fake("b")
    events = run(Router([a, b], sleep=sleep).for_turn())
    assert slept == [] and any(isinstance(e, Restart) for e in events)


def test_a_day_limit_is_not_waited_out():
    slept, sleep = sleeper()
    a, b = Fake("a", "rate_day", retry_after=2.0), Fake("b")
    assert text(run(Router([a, b], sleep=sleep).for_turn())) == "b"
    assert slept == []


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


def test_a_request_too_large_for_one_model_moves_on_and_leaves_it_open():
    # groq T1 run 11, case d1-027: qwen's 7,000 input tokens a minute could not take 7,315,
    # and the 413 failed the whole turn instead of reaching the next model.
    a, b = Fake("a", "too_large"), Fake("b")
    router = Router([a, b])
    events = run(router.for_turn())
    assert text(events) == "b"
    assert router.available() == [a, b]  # a smaller request still fits a


def test_when_every_model_is_too_small_the_error_is_provider_unavailable():
    with pytest.raises(AllModelsFailed) as e:
        run(Router([Fake("a", "too_large"), Fake("b", "too_large")]).for_turn())
    assert e.value.code == "provider_unavailable"


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


class Store:
    """quota_counters as the router sees it, shared between "instances"."""

    def __init__(self):
        self.until = {}

    def closed(self):
        return {name: (until, "rate_day") for name, until in self.until.items()}

    def close(self, model, until):
        self.until[model] = max(until, self.until.get(model, 0.0))


def test_a_day_limit_is_written_to_the_store_and_a_cold_instance_skips_the_model():
    store, wall = Store(), Clock()
    wall.t = 1_700_000_000.0
    a, b = Fake("a", "rate_day", retry_after=5000), Fake("b")
    run(Router([a, b], Clock(), wall).for_turn(store))
    assert store.until == {"a": 1_700_000_000.0 + 5000}

    a2 = Fake("a")  # a new instance after a cold start: a is healthy as far as it knows
    cold = Router([a2, Fake("b")], Clock(), wall)
    assert text(run(cold.for_turn(store))) == "b" and a2.calls == 0
    wall.t += 5001
    cold2 = Router([a2, Fake("b")], Clock(), wall)
    assert text(run(cold2.for_turn(store))) == "a"


def test_a_minute_limit_stays_in_memory():
    store = Store()
    run(Router([Fake("a", "rate_minute"), Fake("b")], Clock()).for_turn(store))
    assert store.until == {}


def test_when_the_store_closes_every_model_the_error_is_quota_exhausted():
    store, wall = Store(), Clock()
    store.until = {"a": wall.t + 100, "b": wall.t + 100}
    a, b = Fake("a"), Fake("b")
    with pytest.raises(AllModelsFailed) as e:
        run(Router([a, b], Clock(), wall).for_turn(store))
    assert e.value.code == "quota_exhausted" and a.calls == b.calls == 0


def test_the_vision_router_has_one_model_named_like_the_main_routers():
    import httpx

    from portfolio_agent.providers.router import from_env, vision_from_env

    env = {"GROQ_API_KEY": "k", "GROQ_MODEL": "openai/gpt-oss-120b",
           "GROQ_FALLBACK_MODELS": "qwen/qwen3.8-27b"}
    client = httpx.AsyncClient()
    vision = vision_from_env(client, env)
    assert [m.name for m in vision.models] == ["groq/qwen/qwen3.8-27b"]
    # The same name means the same token count and the same closed-until state.
    assert vision.models[0].name in [m.name for m in from_env(client, env).models]
    assert vision_from_env(client, {**env, "GROQ_VISION_MODEL": "x/y"}).models[0].name == "groq/x/y"


def test_a_switch_keeps_the_retry_after_and_when_it_came():
    clock = Clock()
    a, b = Fake("a", "rate_minute", retry_after=23.0), Fake("b")
    turn = Router([a, b], clock=clock).for_turn()
    clock.t += 4.0
    assert text(run(turn)) == "b"
    assert turn.switches == [{"from": "a", "reason": "rate_minute", "retry_after": 23.0, "at": 4.0}]


def test_a_wait_that_was_taken_is_kept_too():
    slept, sleep = sleeper()
    turn = Router([Busy("a", 7.0), Fake("b")], sleep=sleep).for_turn()
    run(turn)
    assert turn.waits == [{"model": "a", "seconds": 7.0, "at": 0.0}]
