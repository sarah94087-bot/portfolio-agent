"""Embeddings candidates for R2 (ADR-0009): open models run with ONNX in the process, Workers AI
on Cloudflare's free plan, and gemini-embedding-001 as a reference for experiments only.

Only the chosen model moves into the backend package. Every candidate embeds the query and the
chunks with the same model, as R2 requires, and returns unit vectors (cosine = dot product).
Keys come from the local .env (the evals keys) and are never printed.
"""

import hashlib
import json
import os
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "evals" / ".cache" / "embeddings"
MODELS_DIR = Path(os.environ.get("EMBEDDING_MODELS_DIR", ROOT / "evals" / ".cache" / "models"))

Kind = Literal["query", "passage"]


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: Sequence[str], kind: Kind) -> list[list[float]]: ...


def unit(rows: np.ndarray) -> np.ndarray:
    return rows / np.clip(np.linalg.norm(rows, axis=1, keepdims=True), 1e-12, None)


@dataclass
class OnnxEmbedder:
    """A sentence-transformers style model exported to ONNX: mean pooling over the mask."""

    name: str
    dim: int
    max_length: int
    query_prefix: str = ""
    passage_prefix: str = ""
    threads: int = 1  # a Vercel Hobby function has one vCPU
    load_ms: float = field(default=0.0, init=False)

    def __post_init__(self):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        path = MODELS_DIR / self.name
        start = time.perf_counter()
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = self.threads
        self.session = ort.InferenceSession(
            str(path / "onnx" / "model_quantized.onnx"), opts, providers=["CPUExecutionProvider"]
        )
        self.tokenizer = Tokenizer.from_file(str(path / "tokenizer.json"))
        self.tokenizer.enable_truncation(self.max_length)
        self.tokenizer.enable_padding()
        self.load_ms = (time.perf_counter() - start) * 1000
        self.inputs = {i.name for i in self.session.get_inputs()}

    def embed(self, texts: Sequence[str], kind: Kind) -> list[list[float]]:
        prefix = self.query_prefix if kind == "query" else self.passage_prefix
        out = []
        for i in range(0, len(texts), 16):
            enc = self.tokenizer.encode_batch([prefix + t for t in texts[i : i + 16]])
            ids = np.array([e.ids for e in enc], dtype=np.int64)
            mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
            feed = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in self.inputs:
                feed["token_type_ids"] = np.zeros_like(ids)
            hidden = self.session.run(None, feed)[0]
            m = mask[:, :, None].astype(np.float32)
            pooled = (hidden * m).sum(axis=1) / np.clip(m.sum(axis=1), 1e-9, None)
            out += unit(pooled).tolist()
        return out

    def truncated(self, texts: Sequence[str], kind: Kind) -> int:
        """How many texts are longer than max_length tokens, so the model sees only a part."""
        prefix = self.query_prefix if kind == "query" else self.passage_prefix
        self.tokenizer.no_truncation()
        n = sum(len(self.tokenizer.encode(prefix + t).ids) > self.max_length for t in texts)
        self.tokenizer.enable_truncation(self.max_length)
        return n


def load_env() -> None:
    """ROOT/.env into os.environ, without overriding what is set and without printing."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} is not set in .env")
    return value


@dataclass
class CloudflareEmbedder:
    """Workers AI over REST. The free plan gives 10,000 neurons a day, no payment method."""

    name: str  # e.g. "@cf/baai/bge-m3"
    dim: int
    query_prefix: str = ""
    batch: int = 50

    def embed(self, texts: Sequence[str], kind: Kind) -> list[list[float]]:
        account, token = env("CLOUDFLARE_ACCOUNT_ID"), env("CLOUDFLARE_API_TOKEN_EVALS")
        prefix = self.query_prefix if kind == "query" else ""
        url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{self.name}"
        out = []
        with httpx.Client(timeout=60) as client:
            for i in range(0, len(texts), self.batch):
                r = client.post(
                    url, headers={"Authorization": f"Bearer {token}"},
                    json={"text": [prefix + t for t in texts[i : i + self.batch]]},
                )
                r.raise_for_status()
                out += unit(np.array(r.json()["result"]["data"], dtype=np.float32)).tolist()
        return out


@dataclass
class GeminiEmbedder:
    """Reference only: the free Gemini API may not serve visitors (ADR-0009)."""

    name: str = "gemini-embedding-001"
    dim: int = 768
    batch: int = 50

    def embed(self, texts: Sequence[str], kind: Kind) -> list[list[float]]:
        key = env("GEMINI_API_KEY_EVALS")
        url = "https://generativelanguage.googleapis.com/v1beta/openai/embeddings"
        out = []
        with httpx.Client(timeout=60) as client:
            for i in range(0, len(texts), self.batch):
                r = client.post(
                    url, headers={"Authorization": f"Bearer {key}"},
                    json={"model": self.name, "input": list(texts[i : i + self.batch]),
                          "dimensions": self.dim},
                )
                r.raise_for_status()
                rows = [d["embedding"] for d in r.json()["data"]]
                out += unit(np.array(rows, dtype=np.float32)).tolist()
        return out


class Cached:
    """Embeds each text once per model and kind, on disk, so reruns cost no quota."""

    def __init__(self, inner: Embedder, cache_dir: Path = CACHE_DIR):
        self.inner, self.name, self.dim = inner, inner.name, inner.dim
        self.path = cache_dir / (inner.name.replace("/", "_").replace("@", "") + ".json")
        self.store: dict[str, list[float]] = (
            json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        )

    @staticmethod
    def key(text: str, kind: Kind) -> str:
        return hashlib.sha256(f"{kind}\n{text}".encode()).hexdigest()

    def embed(self, texts: Sequence[str], kind: Kind) -> list[list[float]]:
        missing = list(dict.fromkeys(t for t in texts if self.key(t, kind) not in self.store))
        if missing:
            for t, v in zip(missing, self.inner.embed(missing, kind), strict=True):
                self.store[self.key(t, kind)] = v
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.store), encoding="utf-8")
        return [self.store[self.key(t, kind)] for t in texts]


# The candidates (docs/experiments/retrieval-2026-11-04.md, embeddings). e5 needs its prefixes;
# paraphrase-multilingual-MiniLM was trained on 128 tokens; Qwen3 wants an instruction on queries.
QWEN_QUERY = (
    "Instruct: Given a question about a person's work, retrieve passages that answer it\nQuery: "
)
CANDIDATES = {
    "e5-small": lambda: OnnxEmbedder("multilingual-e5-small", 384, 512, "query: ", "passage: "),
    "e5-base": lambda: OnnxEmbedder("multilingual-e5-base", 768, 512, "query: ", "passage: "),
    "minilm": lambda: OnnxEmbedder("paraphrase-multilingual-MiniLM-L12-v2", 384, 128),
    "bge-m3": lambda: CloudflareEmbedder("@cf/baai/bge-m3", 1024),
    "qwen3": lambda: CloudflareEmbedder("@cf/qwen/qwen3-embedding-0.6b", 1024, QWEN_QUERY),
    "gemini": lambda: GeminiEmbedder(),
}
