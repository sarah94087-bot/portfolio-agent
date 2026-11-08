"""The production embedder (ADR-0012). The file checks always run; the model itself runs only
when EMBEDDING_MODEL_DIR points at the pinned files (local, not in CI: they are 130 MB)."""

import math
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from portfolio_agent.retrieval import embedder as emb

MODEL_DIR = os.environ.get("EMBEDDING_MODEL_DIR")
needs_model = pytest.mark.skipif(not MODEL_DIR, reason="EMBEDDING_MODEL_DIR not set")


def test_verify_names_a_missing_file(tmp_path):
    with pytest.raises(emb.ModelFilesError, match="missing"):
        emb.verify(tmp_path)


def test_verify_rejects_a_file_that_is_not_the_pinned_one(tmp_path):
    for rel in emb.FILES:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes(b"another export")
    with pytest.raises(emb.ModelFilesError, match="SHA-256"):
        emb.verify(tmp_path)


def test_without_the_env_var_there_is_no_model(monkeypatch):
    monkeypatch.delenv(emb.ENV_VAR, raising=False)
    emb.from_env.cache_clear()
    assert emb.from_env() is None
    emb.from_env.cache_clear()


def test_each_text_goes_through_the_model_alone():
    """ADR-0015. Runs in CI, where the model files are absent."""
    np = pytest.importorskip("numpy")

    class Tokenizer:
        def encode(self, text):
            return SimpleNamespace(ids=[1, 2], attention_mask=[1, 1])

    class Session:
        shapes = []

        def run(self, _, feed):
            self.shapes.append(feed["input_ids"].shape)
            return [np.ones((1, 2, emb.DIM), dtype=np.float32)]

    model = object.__new__(emb.E5Embedder)
    model.session, model.tokenizer = Session(), Tokenizer()
    model.inputs = {"input_ids", "attention_mask"}
    assert len(model.embed_passages(["a", "b", "c"])) == 3
    assert Session.shapes == [(1, 2)] * 3


@pytest.fixture(scope="module")
def model():
    return emb.E5Embedder(Path(MODEL_DIR))


@needs_model
def test_vectors_are_unit_length_with_384_dimensions(model):
    q = model.embed_query("hybrid retrieval with pgvector")
    p = model.embed_passages(["She built hybrid retrieval.", "היא בנתה חיפוש היברידי."])
    assert len(q) == emb.DIM and len(p) == 2
    for v in (q, *p):
        assert math.isclose(sum(x * x for x in v), 1.0, rel_tol=1e-4)


@needs_model
def test_query_and_passage_prefixes_give_different_vectors(model):
    assert model.embed_query("pgvector") != model.embed_passages(["pgvector"])[0]


@needs_model
def test_a_vector_depends_only_on_its_own_text(model):
    texts = ["A short passage.", "היא בנתה חיפוש היברידי עם pgvector ו-BM25. " * 40, "Another one."]
    together = model.embed_passages(texts)
    assert model.embed_passages(texts[::-1])[::-1] == together
    assert [model.embed_passages([t])[0] for t in texts] == together


@needs_model
def test_same_computation_as_the_embedder_the_m3_results_came_from(model, monkeypatch):
    """Given one text at a time, the evals embedder must match exactly. It batches, so two texts
    together would differ (ADR-0015), but the prefixes, pooling and truncation are the same."""
    evals = Path(__file__).resolve().parents[2] / "evals"
    monkeypatch.syspath_prepend(str(evals))
    monkeypatch.setenv("EMBEDDING_MODELS_DIR", str(Path(MODEL_DIR).parent))
    sys.modules.pop("retrieval.embedders", None)
    from retrieval.embedders import CANDIDATES

    reference = CANDIDATES["e5-small"]()
    texts = ["Human approval before an AI agent writes", "איך היא בדקה את איכות השליפה?"]
    for text, got in zip(texts, model.embed_passages(texts), strict=True):
        want = reference.embed([text], "passage")[0]
        assert max(abs(a - b) for a, b in zip(got, want, strict=True)) < 1e-6
    assert max(abs(a - b) for a, b in zip(
        model.embed_query(texts[1]), reference.embed([texts[1]], "query")[0], strict=True
    )) < 1e-6
