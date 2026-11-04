"""Stage 2 of the retrieval experiments: does hybrid justify itself (docs/04-retrieval-design.md,
section 4)? The chunking is fixed to C4 (ADR-0010) and the query to Q0. R1, R2 with one
embeddings candidate, and R3, their fusion, all search the same table and are scored on D1's
dev split only. The decision order is R1, R2, R3: fewer parts, no model, then one model, then both.

Run from evals/, against a local Postgres with the migrations (PGlite or docker compose):
    DATABASE_URL=postgresql://... ../backend/.venv/Scripts/python -m retrieval.run_stage2 <model>
"""

import json
import os
import sys
from collections.abc import Sequence

import psycopg
from portfolio_agent import migrate
from portfolio_agent.ingest import Doc, chunk, load, upsert
from portfolio_agent.retrieval import hybrid, lexical, vector

from retrieval.embedders import Embedder
from retrieval.harness import D1Item, load_d1, run, write_results
from retrieval.run_stage1 import D1_PATH, SPLIT, decide, pairwise, retriever_label, table

STRATEGY = "C4"  # ADR-0010
RETRIEVERS = ("R1", "R2", "R3")
SIMPLEST_FIRST = RETRIEVERS
TABLE = "stage2_chunks"


def labels(embedder: Embedder) -> dict[str, str]:
    """R1, R2-<model>, R3-<model>: the names in the result files."""
    model = retriever_label(embedder).removeprefix("R2-")
    return {"R1": "R1", "R2": f"R2-{model}", "R3": f"R3-{model}"}


def config_name(label: str, strategy: str = STRATEGY) -> str:
    return f"stage2-{strategy}-{label}-Q0"


def stage2(
    db_url: str, items: Sequence[D1Item], embedder: Embedder, docs: list[Doc] | None = None,
    strategy: str = STRATEGY,
) -> dict:
    migrate.run(db_url)
    docs = load() if docs is None else docs
    names = labels(embedder)
    with psycopg.connect(db_url, autocommit=True) as conn:
        conn.execute(f"drop table if exists {TABLE}")
        conn.execute(f"create temp table {TABLE} (like chunks including all)")
        try:
            chunks = chunk(docs, strategy)
            upsert(conn, chunks, TABLE)
            vector.add_embedding_column(conn, TABLE, embedder.dim)
            vecs = embedder.embed([c.content for c in chunks], "passage")
            by_id = {c.id: v for c, v in zip(chunks, vecs, strict=True)}
            vector.store_embeddings(conn, TABLE, by_id)

            def query_vector(q: str) -> list[float]:
                return embedder.embed([q], "query")[0]

            retrieve = {
                "R1": lambda q, k: lexical.search(conn, q, k, TABLE),
                "R2": lambda q, k: vector.search(conn, query_vector(q), k, TABLE),
                "R3": lambda q, k: hybrid.search(conn, q, query_vector(q), k, TABLE),
            }
            results = {
                r: {"strategy": strategy, "retriever": names[r], "chunks": len(chunks),
                    **run(items, retrieve[r], split=SPLIT)}
                for r in RETRIEVERS
            }
        finally:
            conn.execute(f"drop table {TABLE}")
    return {
        "results": results,
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

    if len(sys.argv) < 2 or sys.argv[1] not in CANDIDATES:
        print(f"usage: run_stage2 <model>, one of {sorted(CANDIDATES)}", file=sys.stderr)
        return 2
    load_env()
    embedder = Cached(CANDIDATES[sys.argv[1]]())
    out = stage2(db_url, load_d1(D1_PATH), embedder)
    names = labels(embedder)
    for r, result in out["results"].items():
        print(write_results(result, config_name(names[r])))
    name = f"stage2-{STRATEGY}-{names['R3']}-comparisons"
    print(write_results({"comparisons": out["comparisons"], "decision": out["decision"]}, name))
    print(table(out["results"]))
    print(json.dumps(out["decision"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
