"""Fetch the embeddings model files from a fixed source, checked against the pinned hashes.

    python -m portfolio_agent.retrieval.fetch_model [target dir | --bundle]

The target is the argument, or EMBEDDING_MODEL_DIR. --bundle is the Vercel build
(pyproject.toml, tool.vercel.scripts): the folder embedder.BUNDLED_DIR, beside the code. The
files come from one revision of one repository, so the same command gives the same bytes on a
laptop, in CI and in the build:

- Xenova/multilingual-e5-small at REVISION: the ONNX export of intfloat/multilingual-e5-small
  (MIT) for transformers.js, with its 8-bit quantized model. Its file listing on Hugging Face
  gives the same SHA-256 for both files as embedder.FILES, the files every M3 result was
  measured with (checked 2026-11-05).

A file already there with the right hash is not downloaded again. A download goes to a
`.part` file, is hashed while it streams, and is renamed into place only when the hash
matches, so a broken or changed download never replaces a good file and never loads.
"""

import hashlib
import os
import sys
from pathlib import Path

import httpx

from portfolio_agent.retrieval.embedder import (
    BUNDLED_DIR,
    ENV_VAR,
    FILES,
    ModelFilesError,
    sha256,
)

REPO = "Xenova/multilingual-e5-small"
REVISION = "761b726dd34fb83930e26aab4e9ac3899aa1fa78"
BASE = f"https://huggingface.co/{REPO}/resolve/{REVISION}"
TIMEOUT = httpx.Timeout(30.0, read=120.0)


def fetch(target: Path, client: httpx.Client | None = None, log=print) -> list[str]:
    """Makes `target` hold the pinned files. Returns the paths it downloaded."""
    own = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=TIMEOUT)
    fetched = []
    try:
        for rel, expected in FILES.items():
            path = target / rel
            if path.exists() and sha256(path) == expected:
                log(f"ok      {rel}")
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            part = path.with_name(path.name + ".part")
            h = hashlib.sha256()
            with client.stream("GET", f"{BASE}/{rel}") as r:
                r.raise_for_status()
                with part.open("wb") as f:
                    for block in r.iter_bytes(1 << 20):
                        h.update(block)
                        f.write(block)
            if h.hexdigest() != expected:
                part.unlink()
                raise ModelFilesError(f"{rel} from {REPO}@{REVISION[:8]} is not the pinned file")
            part.replace(path)
            fetched.append(rel)
            log(f"fetched {rel}")
    finally:
        if own:
            client.close()
    return fetched


def main(argv: list[str]) -> int:
    if argv[1:] == ["--bundle"]:
        print(f"bundling the model in {BUNDLED_DIR}")
        fetch(BUNDLED_DIR)
        return 0
    target = argv[1] if len(argv) > 1 else os.environ.get(ENV_VAR)
    if not target:
        print("usage: python -m portfolio_agent.retrieval.fetch_model <dir> | --bundle"
              f"  (or set {ENV_VAR})")
        return 2
    fetch(Path(target))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
