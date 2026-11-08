import json

import httpx

from portfolio_agent.providers.openai_compat import ProviderError
from portfolio_agent.retrieval.lexical import Hit
from portfolio_agent.retrieval.rerank import (
    RERANK_CANDIDATES,
    RERANK_MODEL,
    SYSTEM,
    GroqRanker,
    Ranking,
    apply_order,
    candidates_block,
    from_env,
    rerank,
    truncate,
)


def hit(cid: str, text: str = "text") -> Hit:
    return Hit(cid, cid.split("#")[0], ("s",), text, {"rrf": 0.1})


def test_truncate_cuts_at_the_token_limit_and_says_so():
    assert truncate("one two three", 5) == "one two three"
    assert truncate("one two three four", 2) == "one two …"
    assert truncate("a, b", 2) == "a, …"  # punctuation is a token, as in ingest


def test_candidates_block_shows_every_id_with_the_start_of_its_text():
    block = candidates_block([hit("a#all", "alpha beta gamma"), hit("b#all", "delta")], 2)
    assert block == "[a#all]\nalpha beta …\n\n[b#all]\ndelta"


def test_apply_order_follows_the_model_and_keeps_what_it_left_out():
    hits = [hit("a#1"), hit("b#1"), hit("c#1"), hit("d#1")]
    out = apply_order(hits, ["c#1", "x#9", "a#1", "c#1"])
    assert [h.id for h in out] == ["c#1", "a#1", "b#1", "d#1"]
    assert [h.scores["rerank"] for h in out] == [1, 2, 3, 4]
    assert out[0].scores["rrf"] == 0.1
    assert [h.id for h in apply_order(hits, [])] == ["a#1", "b#1", "c#1", "d#1"]


def ok(ranking, tokens=2300):
    args = json.dumps({"ranking": ranking})
    return httpx.Response(200, json={
        "choices": [{"message": {"tool_calls": [{"function": {"arguments": args}}]}}],
        "usage": {"total_tokens": tokens},
    })


def groq(*responses):
    """A GroqRanker on a fake transport, and the bodies it sent."""
    sent, queue = [], list(responses)

    def handle(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        next_one = queue.pop(0)
        if isinstance(next_one, Exception):
            raise next_one
        return next_one
    return GroqRanker(httpx.Client(transport=httpx.MockTransport(handle)), "key"), sent


def test_the_call_is_the_one_stage_4_measured():
    ranker, sent = groq(ok(["b#1", "a#1"]))
    got = ranker.rank("שאלה?", "the query", [hit("a#1", "alpha"), hit("b#1", "beta")])
    assert got == Ranking(["b#1", "a#1"], 2300)
    body = sent[0]
    assert body["model"] == RERANK_MODEL and ranker.name == f"groq/{RERANK_MODEL}"
    assert body["messages"][0] == {"role": "system", "content": SYSTEM}
    assert body["messages"][1]["content"] == (
        "Visitor's question: שאלה?\nSearch query: the query\n\n"
        "Candidates:\n\n[a#1]\nalpha\n\n[b#1]\nbeta"
    )
    assert body["tool_choice"]["function"]["name"] == "rank_passages"
    items = body["tools"][0]["function"]["parameters"]["properties"]["ranking"]["items"]
    assert items["enum"] == ["a#1", "b#1"]
    assert "temperature" not in body and "max_tokens" not in body


def test_a_400_is_tried_once_more_and_then_raised():
    ranker, sent = groq(httpx.Response(400, text="bad tool call"), ok(["a#1"]))
    assert ranker.rank("q", "q", [hit("a#1")]).ids == ["a#1"]
    assert len(sent) == 2
    ranker, sent = groq(*[httpx.Response(400, text="bad tool call")] * 2)
    try:
        ranker.rank("q", "q", [hit("a#1")])
    except ProviderError as e:
        assert e.kind == "bad_request"
    else:
        raise AssertionError("expected ProviderError")
    assert len(sent) == 2


def test_a_timeout_is_unavailable_and_not_tried_again():
    ranker, sent = groq(httpx.ReadTimeout("slow"))
    try:
        ranker.rank("q", "q", [hit("a#1")])
    except ProviderError as e:
        assert e.kind == "unavailable"
    else:
        raise AssertionError("expected ProviderError")
    assert len(sent) == 1


def test_an_answer_that_cannot_be_read_is_an_empty_ranking_with_its_tokens():
    bad = httpx.Response(200, json={
        "choices": [{"message": {"tool_calls": [{"function": {"arguments": "{oops"}}]}}],
        "usage": {"total_tokens": 900},
    })
    ranker, _ = groq(bad)
    assert ranker.rank("q", "q", [hit("a#1")]) == Ranking([], 900)


def test_no_key_means_no_ranker():
    assert from_env(httpx.Client(), {}) is None
    assert from_env(httpx.Client(), {"GROQ_API_KEY": "k"}).name == f"groq/{RERANK_MODEL}"


class FakeQuota:
    def __init__(self, closed=()):
        self.shut = {m: (9e9, "rate_day") for m in closed}
        self.spent = []
        self.closes = []

    def closed(self):
        return self.shut

    def close(self, model, until):
        self.closes.append((model, until))

    def spend(self, model, tokens):
        self.spent.append((model, tokens))


class FakeRanker:
    name = "groq/m"

    def __init__(self, answer):
        self.answer = answer
        self.got = None

    def rank(self, question, query, hits):
        self.got = (question, query, [h.id for h in hits])
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


HITS = [hit(f"r{i}#all") for i in range(RERANK_CANDIDATES + 2)]


def ids(outcome):
    return [h.id for h in outcome.hits]


def test_the_first_candidates_are_reordered_and_the_rest_follow():
    ranker, quota = FakeRanker(Ranking(["r2#all", "r0#all"], 2300)), FakeQuota()
    out = rerank(HITS, "the question", "the query", ranker, quota)
    assert ranker.got[:2] == ("the question", "the query")
    assert len(ranker.got[2]) == RERANK_CANDIDATES
    assert ids(out)[:3] == ["r2#all", "r0#all", "r1#all"]
    assert ids(out)[-2:] == ["r10#all", "r11#all"]
    assert out.fallback is None and out.tokens == 2300
    assert quota.spent == [("groq/m", 2300)]


def test_a_closed_model_costs_no_call_and_keeps_r3_s_order():
    ranker, quota = FakeRanker(Ranking(["r2#all"], 1)), FakeQuota(closed=["groq/m"])
    out = rerank(HITS, "q", "q", ranker, quota)
    assert ranker.got is None and ids(out) == [h.id for h in HITS]
    assert out.fallback == "rate_day" and quota.spent == []


def test_a_day_429_closes_the_model_for_every_instance():
    ranker = FakeRanker(ProviderError("rate_day", "per day", retry_after=100.0))
    quota = FakeQuota()
    out = rerank(HITS, "q", "q", ranker, quota, wall=lambda: 1000.0)
    assert quota.closes == [("groq/m", 1100.0)]
    assert out.fallback == "rate_day" and ids(out) == [h.id for h in HITS]


def test_a_minute_429_or_an_outage_only_keeps_r3_s_order():
    for kind in ("rate_minute", "unavailable", "bad_request"):
        quota = FakeQuota()
        out = rerank(HITS, "q", "q", FakeRanker(ProviderError(kind, "x")), quota)
        assert out.fallback == kind and ids(out) == [h.id for h in HITS]
        assert quota.closes == []


def test_an_empty_ranking_keeps_r3_s_order_and_still_counts_its_tokens():
    quota = FakeQuota()
    out = rerank(HITS, "q", "q", FakeRanker(Ranking([], 900)), quota)
    assert out.fallback == "empty" and out.tokens == 900
    assert ids(out) == [h.id for h in HITS] and quota.spent == [("groq/m", 900)]
