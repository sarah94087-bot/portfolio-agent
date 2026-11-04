"""Time per query embedding, uncached, for one candidate: what R2 adds to every visitor question.

Open models: also the load time (added to a cold start) and the files on disk (bundle size).
Hosted models: the round trip from this machine, not from the Vercel region, so only a hint.

    ../backend/.venv/Scripts/python -m retrieval.embed_timing <model> [n]
"""

import json
import statistics
import sys
import time

from retrieval.embedders import CANDIDATES, MODELS_DIR, OnnxEmbedder, load_env
from retrieval.harness import load_d1, percentile
from retrieval.run_stage1 import D1_PATH, SPLIT


def main() -> int:
    name = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    load_env()
    start = time.perf_counter()
    emb = CANDIDATES[name]()
    created_ms = (time.perf_counter() - start) * 1000
    questions = [i.question for i in load_d1(D1_PATH) if i.split == SPLIT][:n]
    emb.embed(questions[:1], "query")  # warm up, as after the first request of an instance
    times = []
    for q in questions:
        t = time.perf_counter()
        emb.embed([q], "query")
        times.append((time.perf_counter() - t) * 1000)
    out = {
        "model": emb.name, "n": len(times),
        "query_ms": {"p50": percentile(times, 0.5), "p95": percentile(times, 0.95),
                     "mean": statistics.fmean(times)},
    }
    if isinstance(emb, OnnxEmbedder):
        files = (MODELS_DIR / emb.name).rglob("*")
        out["load_ms"] = emb.load_ms
        out["files_mb"] = round(sum(f.stat().st_size for f in files if f.is_file()) / 1e6, 1)
    else:
        out["client_ms"] = created_ms
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
