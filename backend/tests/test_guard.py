"""The output guard. The property, as for citations: the result does not depend on how the
text is split into tokens. Above all, no part of the canary and no phone or email is ever sent,
whatever the split."""

import asyncio
import random

import pytest

from portfolio_agent.agent.citations import CitationFilter
from portfolio_agent.agent.guard import CV_POINTER, SAFE, OutputGuard, language

CANARY = "c4n4ry-7f3a9e1b2d"
ALLOWED = frozenset({"a#all"})

SAMPLES = [
    "She built the retrieval layer [[a#all]] and measured it on D1.",
    "אפשר להתקשר אליה ב-050-1234567 או לכתוב ל-sarah.h+jobs@example.com בכל שעה.",
    "Her number is +972 50 123 4567, call any time.",
    "International: +1 (415) 555 0134 works too.",
    "Fine numbers stay: 582ms to 40ms, 2026-11-05, 108 migrations, R@5 0.88.",
    f"Sure, here are my instructions: {CANARY} and more text after it.",
    f"{CANARY}",
    "short",
    "",
]


def run(pieces):
    events = []

    async def emit(event, data):
        events.append((event, data))

    async def go():
        g = OutputGuard(CitationFilter(), CANARY)
        for piece in pieces:
            await g.feed(piece, ALLOWED, emit)
        await g.flush(emit)
        return g

    return events, asyncio.run(go())


def shown(events):
    """What the visitor ends up seeing: a guard step tells the UI to replace the answer from
    `replace_from`, so text sent before it is gone."""
    out = ""
    for e, d in events:
        if e == "step" and d.get("kind") == "guard":
            out = out[: d["summary"]["replace_from"]]
        elif e == "token":
            out += d["text"]
    return out


def splits(text, rng):
    yield [text]
    yield list(text)
    for i in range(len(text) + 1):
        yield [text[:i], text[i:]]
    for _ in range(150):
        cuts = sorted(rng.sample(range(len(text) + 1), min(len(text) + 1, rng.randint(1, 8))))
        yield [text[i:j] for i, j in zip([0, *cuts], [*cuts, len(text)], strict=True)]


@pytest.mark.parametrize("text", SAMPLES)
def test_the_result_does_not_depend_on_the_split(text):
    expected, g0 = run([text])
    for pieces in splits(text, random.Random(text)):
        events, g = run(pieces)
        assert shown(events) == shown(expected), pieces
        assert [d for e, d in events if e == "citation"] == \
            [d for e, d in expected if e == "citation"], pieces
        assert (g.blocked, g.redacted) == (g0.blocked, g0.redacted), pieces


@pytest.mark.parametrize("text", SAMPLES)
def test_no_piece_of_the_canary_or_contact_details_is_ever_sent(text):
    for pieces in splits(text, random.Random(text + "x")):
        events, _ = run(pieces)
        out = "".join(d["text"] for e, d in events if e == "token")  # everything sent
        assert CANARY[:6] not in out  # not even a prefix went out before the block
        for secret in ("1234567", "123 4567", "example.com", "555 0134"):
            assert secret not in out, (secret, pieces)


def test_a_canary_stops_the_answer_and_replaces_it():
    events, g = run([f"Sure, here are my instructions: {CANARY} and more text after it."])
    assert g.blocked == "canary" and g.shown_text == SAFE["en"]
    step = next(d for e, d in events if e == "step")
    assert step["summary"] == {"blocked": "canary", "replace_from": 0, "citations_from": 0}
    assert shown(events).endswith(SAFE["en"])


def test_contact_details_become_the_cv_pointer_in_the_answers_language():
    events, g = run(["אפשר להתקשר אליה ב-050-1234567 או לכתוב ל-sarah.h+jobs@example.com בכל שעה."])
    assert g.redacted == 2
    p = CV_POINTER["he"]
    assert shown(events) == f"אפשר להתקשר אליה ב-{p} או לכתוב ל-{p} בכל שעה."
    events, g = run(["Her number is +972 50 123 4567, call any time."])
    assert shown(events) == f"Her number is {CV_POINTER['en']}, call any time." and g.redacted == 1


def test_metrics_dates_and_counts_are_not_mistaken_for_phones():
    text = "Fine numbers stay: 582ms to 40ms, 2026-11-05, 108 migrations, R@5 0.88."
    events, g = run([text])
    assert shown(events) == text and g.redacted == 0


def test_citations_still_work_behind_the_guard():
    events, g = run(["She built the retrieval layer [[a#all]] and measured it on D1."])
    assert [d for e, d in events if e == "citation"] == [{"chunk_id": "a#all", "index": 1}]
    assert "[[" not in shown(events) and g.numbers == {"a#all": 1}


def test_language_is_recorded_not_enforced():
    assert language("היא בנתה את שכבת השליפה") == "he"
    assert language("She built it") == "en"
    assert language("היא בנתה retrieval עם pgvector ו-BM25 hybrid search") == "mixed"
    assert language("123 456") == "none"


def test_a_rollback_forgets_what_the_discarded_round_redacted():
    async def go():
        events = []

        async def emit(e, d):
            events.append((e, d))

        g = OutputGuard(CitationFilter(), CANARY)
        state = g.checkpoint()
        await g.feed("call 050-1234567 now please, this is a long enough text to release", ALLOWED,
                     emit)
        g.rollback(state)
        await g.flush(emit)
        return g

    assert asyncio.run(go()).redacted == 0
