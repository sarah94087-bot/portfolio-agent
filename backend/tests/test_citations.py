"""The streaming citation filter. The property: the output does not depend on how the text is
split into tokens. Every sample is fed whole, split at every point, one character at a time,
and in many random splits, and all of them must give the same events."""

import asyncio
import random

import pytest

from portfolio_agent.agent.citations import MAX_MARKER, CitationFilter

ALLOWED = frozenset({"a#all", "b#all", "skills#python"})

SAMPLES = [
    "She built it [[a#all]]. Then the rest [[b#all]].",
    "x [[made-up#all]] y",
    "Both [[a#all, b#all]] and again [[a#all]].",
    "היא בנתה את זה [[skills#python]] בעצמה.",
    "use [[ x{y} ]] and ]] and a [ b ] c [",
    "[[[a#all]]",
    "cut short [[a#al",
    "[[a#all]][[b#all]]",
    "a [[" + "x" * (MAX_MARKER + 5) + "]] b",
    "[[]] empty",
    "no citations here at all",
    "",
]


def run(pieces, allowed=ALLOWED):
    events = []

    async def emit(event, data):
        events.append((event, data))

    async def go():
        f = CitationFilter()
        for piece in pieces:
            await f.feed(piece, allowed, emit)
        await f.flush(emit)
        return f

    f = asyncio.run(go())
    return merged(events), f


def merged(events):
    """Adjacent tokens joined, so outputs can be compared whatever the token sizes."""
    out = []
    for event, data in events:
        if event == "token" and out and out[-1][0] == "t":
            out[-1] = ("t", out[-1][1] + data["text"])
        elif event == "token":
            out.append(("t", data["text"]))
        else:
            out.append(("c", data["chunk_id"], data["index"]))
    return out


def splits(text, rng):
    yield [text]
    yield list(text)
    for i in range(len(text) + 1):
        yield [text[:i], text[i:]]
    for _ in range(200):
        cuts = sorted(rng.sample(range(len(text) + 1), min(len(text) + 1, rng.randint(1, 8))))
        yield [text[i:j] for i, j in zip([0, *cuts], [*cuts, len(text)], strict=True)]


@pytest.mark.parametrize("text", SAMPLES)
def test_the_output_does_not_depend_on_the_split(text):
    expected, f0 = run([text])
    rng = random.Random(text)
    for pieces in splits(text, rng):
        got, f = run(pieces)
        assert got == expected, pieces
        assert f.dropped == f0.dropped, pieces


@pytest.mark.parametrize("text", SAMPLES)
def test_only_retrieved_ids_are_cited_and_no_valid_marker_reaches_the_text(text):
    out, _ = run([text])
    assert all(e[1] in ALLOWED for e in out if e[0] == "c")
    for cid in ALLOWED:
        assert all(f"[[{cid}]]" not in e[1] for e in out if e[0] == "t")


def test_a_valid_citation_replaces_its_marker_with_an_event():
    out, f = run(["She built it [[a#all]]. Then [[b#all]]."])
    assert out == [("t", "She built it "), ("c", "a#all", 1), ("t", ". Then "),
                   ("c", "b#all", 2), ("t", ".")]
    assert f.numbers == {"a#all": 1, "b#all": 2} and f.dropped == []


def test_an_id_that_was_not_retrieved_is_dropped_and_recorded():
    out, f = run(["x [[made-up#all]] y"])
    assert out == [("t", "x  y")] and f.dropped == ["made-up#all"]


def test_a_repeated_source_keeps_its_number_and_a_marker_may_hold_several():
    out, _ = run(["Both [[a#all, b#all]] and again [[a#all]]."])
    assert [e for e in out if e[0] == "c"] == [("c", "a#all", 1), ("c", "b#all", 2),
                                                ("c", "a#all", 1)]


def test_what_is_not_a_citation_passes_as_text():
    text = "use [[ x{y} ]] and ]] and a [ b ] c ["
    out, f = run([text])
    assert out == [("t", text)] and f.dropped == []
    long = "a [[" + "x" * (MAX_MARKER + 5) + "]] b"
    assert run([long])[0] == [("t", long)]


def test_a_marker_cut_short_at_the_end_is_dropped():
    out, f = run(["cut short [[a#al"])
    assert out == [("t", "cut short ")] and f.dropped == ["a#al"]


def test_validity_uses_the_chunks_allowed_when_the_marker_closes():
    events = []

    async def emit(event, data):
        events.append((event, data))

    async def go():
        f = CitationFilter()
        await f.feed("see [[new#", frozenset(), emit)
        await f.feed("all]]", frozenset({"new#all"}), emit)
        await f.flush(emit)

    asyncio.run(go())
    assert merged(events) == [("t", "see "), ("c", "new#all", 1)]


def test_an_extra_bracket_before_a_valid_marker_stays_text_and_the_marker_is_cited():
    out, _ = run(["[[[a#all]]"])
    assert out == [("t", "["), ("c", "a#all", 1)]
