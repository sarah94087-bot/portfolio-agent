"""The production embeddings model: multilingual-e5-small, quantized ONNX, in process (ADR-0012).

The same computation as OnnxEmbedder in evals/retrieval/embedders.py, which produced the M3
results: `query: ` and `passage: ` prefixes, 512 tokens, mean pooling over the attention mask,
unit vectors. The index and the queries must use the same files, so the files are pinned by
SHA-256: a different export or quantization fails to load instead of silently changing the
results. Changing them means re-embedding every chunk (ADR-0012, consequences).

One difference from the evals code, on purpose (ADR-0015): each text goes through the model
alone. The quantized model scales a batch as a whole, so in a batch a text's vector depends on
the texts beside it, and the index would depend on how a load happened to group them.

Where the check runs (Sarah, 2026-11-05): at build and at ingest, not on every cold start,
where it costs 0.3 to 0.5 s on top of a 1.3 s load. The Vercel build downloads the files into
BUNDLED_DIR and checks them as they arrive (bundle.py), so from_env loads those
with check=False. A folder given by EMBEDDING_MODEL_DIR is still checked.

The model files are not in the repo (130 MB). EMBEDDING_MODEL_DIR, or BUNDLED_DIR on Vercel, is
a folder with onnx/model_quantized.onnx and tokenizer.json. numpy, onnxruntime and tokenizers
are imported when the model loads, so code that never embeds does not pay for them.
"""

import hashlib
import os
import time
from collections.abc import Sequence
from functools import cache
from pathlib import Path

NAME = "multilingual-e5-small"
DIM = 384
MAX_LENGTH = 512
QUERY_PREFIX, PASSAGE_PREFIX = "query: ", "passage: "
# The files every M3 result was measured with (hashed on 2026-11-05).
FILES = {
    "onnx/model_quantized.onnx": "f80102d3f2a1229f387d3c81909990d8945513e347b0eab049f7de3c6f98c193",
    "tokenizer.json": "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39",
}
ENV_VAR = "EMBEDDING_MODEL_DIR"
BUNDLED_DIR = Path(__file__).resolve().parent / "model"


class ModelFilesError(Exception):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def verify(model_dir: Path) -> None:
    for rel, expected in FILES.items():
        path = model_dir / rel
        if not path.exists():
            raise ModelFilesError(f"{rel} is missing in {model_dir}")
        if sha256(path) != expected:
            raise ModelFilesError(f"{rel} is not the pinned file (SHA-256 differs)")


def model_dir_from_env() -> Path | None:
    value = os.environ.get(ENV_VAR)
    if value:
        return Path(value)
    return BUNDLED_DIR if (BUNDLED_DIR / "tokenizer.json").exists() else None


class E5Embedder:
    def __init__(self, model_dir: Path, threads: int = 1, check: bool = True):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        started = time.perf_counter()
        if check:
            verify(model_dir)
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = threads  # a Vercel Hobby function has one vCPU
        self.session = ort.InferenceSession(
            str(model_dir / "onnx" / "model_quantized.onnx"), opts,
            providers=["CPUExecutionProvider"],
        )
        self.tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        self.tokenizer.enable_truncation(MAX_LENGTH)
        self.inputs = {i.name for i in self.session.get_inputs()}
        self.load_ms = round((time.perf_counter() - started) * 1000)

    def embed_query(self, text: str) -> list[float]:
        return self._embed([QUERY_PREFIX + text])[0]

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embed([PASSAGE_PREFIX + t for t in texts])

    def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        import numpy as np

        out: list[list[float]] = []
        for text in texts:  # one at a time, so a vector depends only on its text (ADR-0015)
            enc = self.tokenizer.encode(text)
            ids = np.array([enc.ids], dtype=np.int64)
            mask = np.array([enc.attention_mask], dtype=np.int64)
            feed = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in self.inputs:
                feed["token_type_ids"] = np.zeros_like(ids)
            hidden = self.session.run(None, feed)[0]
            m = mask[:, :, None].astype(np.float32)
            pooled = (hidden * m).sum(axis=1) / np.clip(m.sum(axis=1), 1e-9, None)
            norms = np.clip(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12, None)
            out += (pooled / norms).tolist()
        return out


@cache
def from_env() -> E5Embedder | None:
    """The model once per process. None when there are no files, and the search then runs R1
    alone and says so in the trace (tools/portfolio.py)."""
    model_dir = model_dir_from_env()
    return E5Embedder(model_dir, check=model_dir != BUNDLED_DIR) if model_dir else None
