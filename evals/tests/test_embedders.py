import json
import os

import numpy as np
import pytest

from retrieval.embedders import CANDIDATES, Cached, unit
from retrieval.harness import D1Item
from retrieval.run_stage1 import config_name, retriever_label, stage1

DB_URL = os.environ.get("TEST_DATABASE_URL")


class Fake:
    """Embeds by counting a few words, so tests know which chunk is nearest."""

    name = "test/fake"
    dim = 4
    WORDS = ("translation", "latency", "postgres", "machine")

    def __init__(self):
        self.calls = []

    def embed(self, texts, kind):
        self.calls.append((kind, list(texts)))
        rows = np.array(
            [[t.lower().count(w) + 1e-3 for w in self.WORDS] for t in texts], dtype=np.float32
        )
        return unit(rows).tolist()


def test_unit_rows_have_length_one():
    rows = unit(np.array([[3.0, 4.0], [0.0, 2.0]]))
    assert np.allclose(np.linalg.norm(rows, axis=1), 1)


def test_cache_embeds_each_text_once_per_kind(tmp_path):
    inner = Fake()
    cached = Cached(inner, tmp_path)
    first = cached.embed(["a translation", "a translation", "latency"], "passage")
    assert inner.calls == [("passage", ["a translation", "latency"])]
    assert first[0] == first[1]
    cached.embed(["latency"], "passage")
    cached.embed(["latency"], "query")  # a query is embedded apart from a passage
    assert len(inner.calls) == 2
    again = Cached(Fake(), tmp_path)  # read back from disk
    assert again.embed(["latency"], "passage") == [first[2]]
    assert again.inner.calls == []
    assert json.loads(cached.path.read_text(encoding="utf-8"))


def test_every_candidate_is_named_and_labels_are_stable():
    assert set(CANDIDATES) == {"e5-small", "e5-base", "minilm", "bge-m3", "qwen3", "gemini"}
    assert retriever_label() == "R1"
    assert retriever_label(Fake()) == "R2-fake"
    assert config_name("C4", "R2-fake") == "stage1-C4-R2-fake-Q0"


@pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL not set")
def test_stage1_with_r2_embeds_chunks_as_passages_and_questions_as_queries():
    items = [D1Item(
        id="d1-001", question="How does a human approve machine translation output?",
        lang="en", category="single_hop", expected_behavior="answer",
        gold_chunks=["human-gated-translation#problem"], split="dev",
    )]
    fake = Fake()
    out = stage1(DB_URL, items, strategies=["C4"], embedder=fake)
    r = out["results"]["C4"]
    assert r["retriever"] == "R2-fake" and r["n"] == 1
    kinds = [k for k, _ in fake.calls]
    assert kinds == ["passage", "query"]
    assert fake.calls[1][1] == [items[0].question]
    assert r["items"][0]["retrieved"], "R2 returned nothing"


def test_post_reports_each_429_wait_apart_from_the_call(monkeypatch):
    import httpx

    from retrieval import embedders

    slept = []
    monkeypatch.setattr(embedders.time, "sleep", slept.append)
    answers = iter([httpx.Response(429, headers={"retry-after": "3"}), httpx.Response(200)])
    client = httpx.Client(transport=httpx.MockTransport(lambda request: next(answers)))
    waits: list[float] = []
    assert embedders.post(client, "https://example.test", waits=waits).status_code == 200
    assert slept == [3.0] and len(waits) == 1
