"""Stage 1 of the retrieval experiments: which chunking works best (docs/04-retrieval-design.md,
section 4). Every strategy C1-C4 is loaded into its own temp table cloned from `chunks`, searched
with R1 and the visitor's question as is (Q0), and scored on D1's dev split only.

R2 is not here yet: no embeddings model is chosen (ADR-0009), so this answers the question for
lexical search only.

Run from evals/, against a local Postgres with the migrations (PGlite or docker compose):
    DATABASE_URL=postgresql://... ../backend/.venv/Scripts/python -m retrieval.run_stage1
"""

import json
import os
import sys
from collections.abc import Sequence
from dataclasses import asdict
from itertools import combinations
from pathlib import Path

import psycopg
from portfolio_agent import migrate
from portfolio_agent.ingest import Doc, chunk, load, upsert
from portfolio_agent.retrieval.lexical import search

from retrieval.harness import D1Item, compare, load_d1, run, write_results

D1_PATH = Path(__file__).resolve().parent.parent / "datasets" / "d1.yaml"
STRATEGIES = ("C1", "C2", "C3", "C4")
# Fewest parts first (docs/04, section 5): a whole record; one chunk per heading; the same with a
# context header; fixed windows, which add a size, an overlap and a section-coverage rule.
SIMPLEST_FIRST = ("C4", "C1", "C2", "C3")
GROUPS = ("all", "he", "en", "cross_lingual")
METRIC = "recall@5"
HEBREW_THRESHOLD = 0.85  # Recall@5 for he and cross_lingual (docs/03, section 6)
SPLIT = "dev"  # test runs once, in stage 5, on the final configuration


def config_name(strategy: str) -> str:
    return f"stage1-{strategy}-R1-Q0"


def run_strategy(
    conn: psycopg.Connection, docs: list[Doc], items: Sequence[D1Item], strategy: str
) -> dict:
    """One strategy in its own temp table, dropped afterwards (PGlite shares one session)."""
    table = f"stage1_{strategy.lower()}"
    conn.execute(f"drop table if exists {table}")
    conn.execute(f"create temp table {table} (like chunks including all)")
    try:
        chunks = chunk(docs, strategy)
        upsert(conn, chunks, table)
        result = run(items, lambda q, k: search(conn, q, k, table), split=SPLIT)
        return {"strategy": strategy, "chunks": len(chunks), **result}
    finally:
        conn.execute(f"drop table {table}")


def pairwise(results: dict[str, dict], metric: str = METRIC) -> list[dict]:
    """b minus a for every pair of strategies, in every group, paired by question."""
    rows = []
    for a, b in combinations(results, 2):
        for group in GROUPS:
            if group not in results[a]["groups"]:
                continue  # no question of this kind in the split
            d = compare(results[a], results[b], metric, group)
            rows.append({
                "a": a, "b": b, "group": group, "metric": metric,
                **asdict(d), "significant": d.significant,
            })
    return rows


def passes_hebrew(result: dict) -> bool:
    groups = result["groups"]
    return all(
        g in groups and groups[g][METRIC]["mean"] >= HEBREW_THRESHOLD
        for g in ("he", "cross_lingual")
    )


def decide(results: dict[str, dict], simplest_first: Sequence[str] = SIMPLEST_FIRST) -> dict:
    """The simplest strategy that is not significantly worse than the best (docs/04, section 5).

    The best is the highest overall Recall@5 among strategies that pass the Hebrew threshold;
    if none passes, the highest overall, and the decision says so.
    """
    def overall(s: str) -> float:
        return results[s]["groups"]["all"][METRIC]["mean"]

    passing = [s for s in results if passes_hebrew(results[s])]
    pool = passing or list(results)
    best = max(pool, key=lambda s: (overall(s), -simplest_first.index(s)))
    verdicts = {}
    for s in simplest_first:
        if s not in results:
            continue
        if s == best:
            verdicts[s] = {"mean": 0.0, "low": 0.0, "high": 0.0, "worse": False}
            continue
        d = compare(results[best], results[s], METRIC, "all")
        verdicts[s] = {**asdict(d), "worse": d.significant and d.mean < 0}
    chosen = next(s for s in simplest_first if s in verdicts and not verdicts[s]["worse"])
    return {
        "best": best, "best_passes_hebrew": bool(passing), "chosen": chosen,
        "versus_best": verdicts, "simplest_first": list(simplest_first),
    }


def stage1(
    db_url: str, items: Sequence[D1Item], docs: list[Doc] | None = None,
    strategies: Sequence[str] = STRATEGIES,
) -> dict:
    migrate.run(db_url)
    docs = load() if docs is None else docs
    with psycopg.connect(db_url, autocommit=True) as conn:
        results = {s: run_strategy(conn, docs, items, s) for s in strategies}
    return {
        "results": results,
        "comparisons": pairwise(results),
        "decision": decide(results),
    }


def table(results: dict[str, dict]) -> str:
    """Markdown: Recall@5 per group as mean [low, high], then MRR, nDCG@5 and p50 latency."""
    head = "| | chunks | " + " | ".join(f"R@5 {g}" for g in GROUPS) + " | MRR | nDCG@5 | p50 ms |"
    lines = [head, "|---" * (len(GROUPS) + 5) + "|"]
    for s, r in results.items():
        cells = []
        for g in GROUPS:
            m = r["groups"][g][METRIC]
            cells.append(f"{m['mean']:.2f} [{m['low']:.2f}, {m['high']:.2f}] (n={m['n']})")
        a = r["groups"]["all"]
        lines.append(
            f"| {s} | {r['chunks']} | " + " | ".join(cells)
            + f" | {a['mrr']['mean']:.2f} | {a['ndcg@5']['mean']:.2f}"
            + f" | {r['latency_ms']['p50']:.0f} |"
        )
    return "\n".join(lines)


def main() -> int:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL is required (a local Postgres; see the module docstring)",
              file=sys.stderr)
        return 2
    out = stage1(db_url, load_d1(D1_PATH))
    for s, r in out["results"].items():
        print(write_results(r, config_name(s)))
    comparisons = write_results(
        {"comparisons": out["comparisons"], "decision": out["decision"]}, "stage1-comparisons"
    )
    print(comparisons)
    print(table(out["results"]))
    print(json.dumps(out["decision"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
