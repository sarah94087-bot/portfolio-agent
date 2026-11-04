"""Stage 3 of the retrieval experiments: how much does Q1 help Hebrew (docs/04-retrieval-design.md,
section 4)? C4 (ADR-0010), R3 (ADR-0011) with multilingual-e5-small (ADR-0012), D1 dev only.

- Q0: the visitor's question as is.
- Q1: the query the agent wrote (retrieval/rewrite.py, saved once), with Sarah's name
  removed in code (portfolio_agent/retrieval/query.py, ADR-0013).
- Q2: Q1 and two alternative phrasings, the name removed from each. Each runs R3, and the
  three rankings are fused with RRF.
  The phrasings come from a model, so Q2 runs 3 times, and it is scored per question as the mean
  of the three runs. The decision order is Q0, Q1, Q2: no call, the same call, a longer call.

Run from evals/, after retrieval.rewrite, against a local Postgres with the migrations:
    DATABASE_URL=postgresql://... ../backend/.venv/Scripts/python -m retrieval.run_stage3
"""

import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence

import psycopg
from portfolio_agent import migrate
from portfolio_agent.ingest import Doc, chunk, load, upsert
from portfolio_agent.retrieval import hybrid, vector
from portfolio_agent.retrieval.lexical import CANDIDATES, Hit
from portfolio_agent.retrieval.query import name_pattern, owner_names, strip_names

from retrieval.embedders import Embedder
from retrieval.harness import GROUPS, METRICS, D1Item, load_d1, run, summarize, write_results
from retrieval.rewrite import load_queries
from retrieval.run_stage1 import D1_PATH, SPLIT, decide, pairwise, table

STRATEGY = "C4"  # ADR-0010
MODEL = "e5-small"  # ADR-0012
Q2_RUNS = (1, 2, 3)
SIMPLEST_FIRST = ("Q0", "Q1", "Q2")
TABLE = "stage3_chunks"


def multi_query(
    search: Callable[[str, int], list[Hit]], alternatives: Mapping[str, Sequence[str]],
) -> Callable[[str, int], list[Hit]]:
    """Q2: R3 for the query and each of its alternatives, the rankings fused with RRF."""
    def retrieve(query: str, k: int) -> list[Hit]:
        lists = [search(q, CANDIDATES) for q in (query, *alternatives[query])]
        by_id = {h.id: h for hits in reversed(lists) for h in hits}
        fused = hybrid.rrf([[h.id for h in hits] for hits in lists])[:k]
        return [Hit(cid, by_id[cid].record_id, by_id[cid].sections, by_id[cid].text,
                    {**by_id[cid].scores, "multi_rrf": score}) for cid, score in fused]
    return retrieve


def mean_of_runs(runs: Sequence[dict]) -> dict:
    """One result whose per-question scores are the mean over runs of the same questions."""
    ids = [r["id"] for r in runs[0]["items"]]
    if any([r["id"] for r in x["items"]] != ids for x in runs):
        raise ValueError("the runs did not score the same questions")
    rows = []
    for i, first in enumerate(runs[0]["items"]):
        row = {k: first[k] for k in ("id", "lang", "category")}
        row["query"] = [x["items"][i]["query"] for x in runs]
        for m in METRICS:
            row[m] = sum(x["items"][i][m] for x in runs) / len(runs)
        rows.append(row)
    groups = {}
    for name, keep in GROUPS.items():
        members = [r for r in rows if keep(r)]
        if members:
            groups[name] = {m: summarize([r[m] for r in members]) for m in METRICS}
    lat = [x["latency_ms"] for x in runs]
    return {
        "split": runs[0]["split"], "n": len(rows), "skipped": runs[0]["skipped"],
        "groups": groups, "items": rows, "runs": len(runs),
        "latency_ms": {p: sum(x[p] for x in lat) / len(lat) for p in ("p50", "p95")},
        "per_run_recall@5": [x["groups"]["all"]["recall@5"]["mean"] for x in runs],
    }


def stage3(
    db_url: str, items: Sequence[D1Item], embedder: Embedder, q1: Mapping[str, dict],
    q2_runs: Sequence[Mapping[str, dict]], docs: list[Doc] | None = None,
) -> dict:
    migrate.run(db_url)
    docs = load() if docs is None else docs
    pattern = name_pattern(owner_names(d.record for d in docs))

    def clean(saved: Mapping[str, dict]) -> dict[str, dict]:
        return {i: {"query": strip_names(q["query"], pattern),
                    "alternatives": [strip_names(a, pattern) for a in q["alternatives"]]}
                for i, q in saved.items()}

    q1, q2_runs = clean(q1), [clean(s) for s in q2_runs]
    with psycopg.connect(db_url, autocommit=True) as conn:
        conn.execute(f"drop table if exists {TABLE}")
        conn.execute(f"create temp table {TABLE} (like chunks including all)")
        try:
            chunks = chunk(docs, STRATEGY)
            upsert(conn, chunks, TABLE)
            vector.add_embedding_column(conn, TABLE, embedder.dim)
            vecs = embedder.embed([c.content for c in chunks], "passage")
            by_id = {c.id: v for c, v in zip(chunks, vecs, strict=True)}
            vector.store_embeddings(conn, TABLE, by_id)

            def r3(q: str, k: int) -> list[Hit]:
                return hybrid.search(conn, q, embedder.embed([q], "query")[0], k, TABLE)

            def scored(result: dict) -> dict:
                return {"strategy": STRATEGY, "chunks": len(chunks), **result}

            results = {
                "Q0": scored(run(items, r3, split=SPLIT)),
                "Q1": scored(run(items, r3, split=SPLIT,
                                 queries={i: q["query"] for i, q in q1.items()})),
            }
            q2 = []
            for saved in q2_runs:
                alternatives = {}
                for q in saved.values():
                    if alternatives.get(q["query"], q["alternatives"]) != q["alternatives"]:
                        raise ValueError(f"two questions share the query {q['query']!r}")
                    alternatives[q["query"]] = q["alternatives"]
                q2.append(run(items, multi_query(r3, alternatives), split=SPLIT,
                              queries={i: q["query"] for i, q in saved.items()}))
            results["Q2"] = scored(mean_of_runs(q2))
        finally:
            conn.execute(f"drop table {TABLE}")
    return {
        "results": results,
        "q2_runs": q2,
        "comparisons": pairwise(results),
        "decision": decide(results, SIMPLEST_FIRST),
    }


def main() -> int:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL is required (a local Postgres; see the module docstring)",
              file=sys.stderr)
        return 2
    from retrieval.embedders import CANDIDATES, Cached, load_env

    load_env()
    embedder = Cached(CANDIDATES[MODEL]())
    out = stage3(db_url, load_d1(D1_PATH), embedder, load_queries("q1"),
                 [load_queries("q2", r) for r in Q2_RUNS])
    label = f"R3-{embedder.name.split('/')[-1]}"
    for q, result in out["results"].items():
        print(write_results({**result, "retriever": label},
                            f"stage3-{STRATEGY}-{label}-{q}"))
    for r, result in zip(Q2_RUNS, out["q2_runs"], strict=True):
        print(write_results({**result, "retriever": label},
                            f"stage3-{STRATEGY}-{label}-Q2-run{r}"))
    name = f"stage3-{STRATEGY}-{label}-comparisons"
    print(write_results({"comparisons": out["comparisons"], "decision": out["decision"]}, name))
    print(table(out["results"]))
    print(json.dumps(out["decision"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
