"""Stage 4 of the retrieval experiments: is reranking worth its time and quota
(docs/04-retrieval-design.md, section 4)? Fixed: C4 (ADR-0010), R3 (ADR-0011) with
multilingual-e5-small (ADR-0012), Q1 with the name removed (ADR-0013), D1 dev only.

- R3: as chosen, the first 5.
- R4: Groq reorders R3's first 10, each cut to 150 tokens (portfolio_agent/retrieval/rerank.py).
  The model sees the visitor's question and the search query, and must call a tool whose only
  argument is the order, with the candidate ids as an enum.

The reranker is not deterministic, so stage 4 has up to 3 runs, under a stopping rule set
before the first one (the experiment report, stage 4): if run 1 is not significantly better
than R3 overall, runs 2 and 3 are not made. Each answer is saved as it comes, in
evals/datasets/rerank/, so a run that hits the token ceiling resumes on the next day.

Run from evals/, after retrieval.rewrite q1, against a local Postgres with the migrations:
    DATABASE_URL=postgresql://... ../backend/.venv/Scripts/python -m retrieval.run_stage4 [run]
    ... -m retrieval.run_stage4 1 --pilot 5   # calls for the first 5 questions only, no score
"""

import json
import os
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import httpx
import psycopg
from portfolio_agent import migrate
from portfolio_agent.ingest import Doc, chunk, load, upsert
from portfolio_agent.retrieval import hybrid, vector
from portfolio_agent.retrieval.lexical import Hit
from portfolio_agent.retrieval.query import name_pattern, owner_names, strip_names
from portfolio_agent.retrieval.rerank import (
    BAD_REQUEST_TRIES,
    CANDIDATE_TOKENS,
    RERANK_CANDIDATES,
    SYSTEM,
    apply_order,
    prompt,
    rank_tool,
)

from retrieval.embedders import Embedder, env, post
from retrieval.harness import D1Item, load_d1, run, write_results
from retrieval.rewrite import GROQ_URL, load_queries
from retrieval.run_stage1 import D1_PATH, SPLIT, decide, pairwise, table

ROOT = Path(__file__).resolve().parents[2]
RERANK_DIR = ROOT / "evals" / "datasets" / "rerank"
STRATEGY = "C4"
MODEL = "e5-small"
SIMPLEST_FIRST = ("R3", "R4")
TABLE = "stage4_chunks"
MAX_TOKENS = int(os.environ.get("RERANK_MAX_TOKENS", "60000"))  # per invocation (docs/10, §3)

# (question, query, candidates) -> (ranking, tokens, ms spent waiting on 429)
Ranker = Callable[[str, str, Sequence[Hit]], tuple[list[str], int, int]]


def groq_ranker(client: httpx.Client) -> Ranker:
    headers = {"Authorization": f"Bearer {env('GROQ_API_KEY_EVALS')}"}
    model = env("GROQ_MODEL")

    def rank(question: str, query: str, hits: Sequence[Hit]) -> tuple[list[str], int, int]:
        ids = [h.id for h in hits]
        body = {
            "model": model, "tools": [rank_tool(ids)],
            "tool_choice": {"type": "function", "function": {"name": "rank_passages"}},
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": prompt(question, query, hits)}],
        }
        waits: list[float] = []
        for attempt in range(BAD_REQUEST_TRIES):
            try:
                data = post(client, GROQ_URL, waits=waits, headers=headers, json=body).json()
                break
            except httpx.HTTPStatusError as e:
                if e.response.status_code != 400:
                    raise
                if attempt == BAD_REQUEST_TRIES - 1:  # R3's order, as the site does
                    return [], 0, round(sum(waits) * 1000)
        calls = data["choices"][0]["message"].get("tool_calls") or []
        ranking = json.loads(calls[0]["function"]["arguments"])["ranking"] if calls else []
        return ([str(c) for c in ranking], data.get("usage", {}).get("total_tokens", 0),
                round(sum(waits) * 1000))
    return rank


def path_for(run_no: int, split: str = SPLIT) -> Path:
    return RERANK_DIR / f"d1-{split}-r4-run{run_no}.json"


def stage4(
    db_url: str, items: Sequence[D1Item], embedder: Embedder, q1: Mapping[str, dict],
    ranker: Ranker, saved_path: Path, model: str = "", docs: list[Doc] | None = None,
    pilot: int | None = None, max_tokens: int = MAX_TOKENS,
) -> dict:
    """Saved rankings are reused; missing ones are asked for until max_tokens is spent.

    Returns the scores only when every question has a ranking; otherwise how many are left.
    """
    migrate.run(db_url)
    docs = load() if docs is None else docs
    pattern = name_pattern(owner_names(d.record for d in docs))
    queries = {i: strip_names(q["query"], pattern) for i, q in q1.items()}
    if saved_path.exists():
        saved = json.loads(saved_path.read_text(encoding="utf-8"))
    else:
        saved = {"model": model, "date": time.strftime("%Y-%m-%d"), "system": SYSTEM,
                 "candidates": RERANK_CANDIDATES, "candidate_tokens": CANDIDATE_TOKENS,
                 "tokens": 0, "calls": 0, "rankings": {}}
    scored = [i for i in items if i.split == SPLIT and i.expected_behavior == "answer"]
    todo = scored[:pilot] if pilot else scored
    spent = 0
    with psycopg.connect(db_url, autocommit=True) as conn:
        conn.execute(f"drop table if exists {TABLE}")
        conn.execute(f"create temp table {TABLE} (like chunks including all)")
        try:
            chunks = chunk(docs, STRATEGY)
            upsert(conn, chunks, TABLE)
            vector.add_embedding_column(conn, TABLE, embedder.dim)
            vecs = embedder.embed([c.content for c in chunks], "passage")
            vector.store_embeddings(conn, TABLE, dict(zip([c.id for c in chunks], vecs,
                                                          strict=True)))
            r3: dict[str, list[Hit]] = {}
            r4: dict[str, list[Hit]] = {}
            for item in todo:
                q = queries[item.id]
                hits = hybrid.search(conn, q, embedder.embed([q], "query")[0],
                                     RERANK_CANDIDATES, TABLE)
                ids = [h.id for h in hits]
                got = saved["rankings"].get(item.id)
                if got is None or got["candidates"] != ids:
                    if spent >= max_tokens:
                        continue
                    start = time.perf_counter()
                    ranking, used, wait_ms = ranker(item.question, q, hits)
                    ms = round((time.perf_counter() - start) * 1000) - wait_ms
                    spent += used
                    saved["tokens"] += used
                    saved["calls"] += 1
                    got = {"candidates": ids, "ranking": ranking, "tokens": used, "ms": ms,
                           "wait_ms": wait_ms, "fallback": not ranking}
                    saved["rankings"][item.id] = got
                    saved_path.parent.mkdir(parents=True, exist_ok=True)
                    saved_path.write_text(json.dumps(saved, ensure_ascii=False, indent=2)
                                          + "\n", encoding="utf-8")
                r3[q], r4[q] = hits, apply_order(hits, got["ranking"])
        finally:
            conn.execute(f"drop table {TABLE}")
    missing = [i.id for i in todo if queries[i.id] not in r4]
    status = {"calls": saved["calls"], "tokens": saved["tokens"], "spent_now": spent,
              "fallbacks": sum(bool(r.get("fallback")) for r in saved["rankings"].values()),
              "missing": missing}
    if pilot or missing:
        return {"status": status}
    use = {i: queries[i] for i in queries}

    def scored_run(lists: dict[str, list[Hit]]) -> dict:
        return {"strategy": STRATEGY, "chunks": len(chunks),
                **run(items, lambda qq, k: lists[qq][:k], split=SPLIT, queries=use)}

    results = {"R3": scored_run(r3), "R4": scored_run(r4)}
    return {"status": status, "results": results, "comparisons": pairwise(results),
            "decision": decide(results, SIMPLEST_FIRST)}


def main() -> int:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL is required (a local Postgres; see the module docstring)",
              file=sys.stderr)
        return 2
    from retrieval.embedders import CANDIDATES, Cached, load_env

    args = sys.argv[1:]
    pilot = int(args[args.index("--pilot") + 1]) if "--pilot" in args else None
    run_no = int(args[0]) if args and args[0].isdigit() else 1
    load_env()
    embedder = Cached(CANDIDATES[MODEL]())
    with httpx.Client(timeout=120) as client:
        out = stage4(db_url, load_d1(D1_PATH), embedder, load_queries("q1"),
                     groq_ranker(client), path_for(run_no), env("GROQ_MODEL"), pilot=pilot)
    print(json.dumps(out["status"]))
    if "results" not in out:
        return 0
    label = f"R3-{embedder.name.split('/')[-1]}"
    for r, result in out["results"].items():
        name = f"stage4-{STRATEGY}-{label}-Q1-{r}" + (f"-run{run_no}" if r == "R4" else "")
        print(write_results({**result, "retriever": r}, name))
    print(write_results({"comparisons": out["comparisons"], "decision": out["decision"]},
                        f"stage4-{STRATEGY}-{label}-Q1-run{run_no}-comparisons"))
    print(table(out["results"]))
    print(json.dumps(out["decision"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
