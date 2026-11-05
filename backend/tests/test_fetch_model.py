"""The model fetch, with a fake Hugging Face: pinned hashes decide what is kept."""

import hashlib

import httpx
import pytest

from portfolio_agent.retrieval import embedder, fetch_model

GOOD = {"onnx/model_quantized.onnx": b"model bytes", "tokenizer.json": b'{"tok": 1}'}


@pytest.fixture
def pinned(monkeypatch):
    monkeypatch.setattr(fetch_model, "FILES",
                        {rel: hashlib.sha256(data).hexdigest() for rel, data in GOOD.items()})


def hub(files, seen):
    def handler(request):
        rel = request.url.path.split(f"/resolve/{fetch_model.REVISION}/", 1)[1]
        seen.append(rel)
        return httpx.Response(200, content=files[rel])
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_the_files_come_from_the_pinned_revision_and_land_in_place(tmp_path, pinned):
    seen = []
    assert fetch_model.fetch(tmp_path, hub(GOOD, seen), log=lambda _: None) == list(GOOD)
    assert seen == list(GOOD)
    for rel, data in GOOD.items():
        assert (tmp_path / rel).read_bytes() == data


def test_a_file_with_the_right_hash_is_not_downloaded_again(tmp_path, pinned):
    fetch_model.fetch(tmp_path, hub(GOOD, []), log=lambda _: None)
    seen = []
    assert fetch_model.fetch(tmp_path, hub(GOOD, seen), log=lambda _: None) == []
    assert seen == []


def test_a_changed_download_never_replaces_or_leaves_a_file(tmp_path, pinned):
    bad = {**GOOD, "tokenizer.json": b"someone else's tokenizer"}
    with pytest.raises(embedder.ModelFilesError):
        fetch_model.fetch(tmp_path, hub(bad, []), log=lambda _: None)
    assert not (tmp_path / "tokenizer.json").exists()
    assert not list(tmp_path.rglob("*.part"))


def test_the_source_is_pinned_to_one_revision():
    assert len(fetch_model.REVISION) == 40 and fetch_model.REVISION in fetch_model.BASE
    assert fetch_model.FILES is embedder.FILES
