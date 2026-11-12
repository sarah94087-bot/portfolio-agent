"""Can retrieval alone tell that the portfolio has no answer?

Today a question with no answer in the portfolio ("Did she work at Google?") is caught only by
the answer model, and only measured on the answers (D1 `refuse_no_info`, judged). Retrieval has
no threshold: R3 always returns its top 10, however far they are from the question. This
measures whether a score of the search separates the two kinds of question, before anything
is built on it:

- positives: D1 questions that expect an answer (they have gold chunks);
- negatives: `refuse_no_info` and `redirect_off_topic`, which have none.

For each question it records the best score of each side of R3 (the top vector cosine, the top
BM25 and the top trigram score), the AUC of each score, and for the vector cosine the cut that
loses no dev positive, then what that same cut does on test. The question is searched as the
visitor wrote it (Q0): the negatives have no saved Q1 query, and the comparison has to be the
same for both kinds. Follow-ups (`history`) are left out, since their question alone does not
say what it asks. No language model is called.

Run from evals/, against a local Postgres with the migrations (PGlite or docker compose):
    DATABASE_URL=postgresql://... EMBEDDING_MODEL_DIR=... \
        ../backend/.venv/Scripts/python -m retrieval.run_abstain
"""

import json
import os
import sys
from collections.abc import Callable, Sequence

import psycopg
from portfolio_agent import migrate
from portfolio_agent.ingest import chunk, load, upsert
from portfolio_agent.retrieval import embedder as e5
from portfolio_agent.retrieval import lexical, vector

from retrieval.harness import D1Item, load_d1, write_results
from retrieval.run_stage1 import D1_PATH

STRATEGY = "C4"  # ADR-0010
TABLE = "abstain_chunks"
SIGNALS = ("vector", "bm25", "trigram")


def auc(pos: Sequence[float], neg: Sequence[float]) -> float:
    """The chance that a random positive scores above a random negative; ties count half."""
    if not pos or not neg:
        return float("nan")
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def best(hits: Sequence[lexical.Hit], key: str) -> float:
    """The highest score of `key` among the hits; 0 when no hit has one (nothing matched)."""
    values = [h.scores.get(key) for h in hits]
    return max((v for v in values if v is not None), default=0.0)


def cut_keeping_all(pos: Sequence[float]) -> float:
    """The highest cut that keeps every positive: a question passes when its score >= cut."""
    return min(pos)


def at_cut(rows: Sequence[dict], signal: str, cut: float) -> dict:
    pos = [r for r in rows if r["answerable"]]
    neg = [r for r in rows if not r["answerable"]]
    return {
        "cut": cut,
        "positives_lost": [r["id"] for r in pos if r[signal] < cut],
        "negatives_caught": [r["id"] for r in neg if r[signal] < cut],
        "positives": len(pos), "negatives": len(neg),
    }


def measure(
    db_url: str, items: Sequence[D1Item], embed_query: Callable[[str], list[float]],
    embed_passages: Callable[[Sequence[str]], list[list[float]]],
) -> list[dict]:
    migrate.run(db_url)
    chunks = chunk(load(), STRATEGY)
    rows = []
    with psycopg.connect(db_url, autocommit=True) as conn:
        conn.execute(f"drop table if exists {TABLE}")
        conn.execute(f"create temp table {TABLE} (like chunks including all)")
        try:
            upsert(conn, chunks, TABLE)
            vector.add_embedding_column(conn, TABLE, len(embed_query("dimension")))
            vecs = embed_passages([c.content for c in chunks])
            vector.store_embeddings(conn, TABLE, {c.id: v for c, v in zip(chunks, vecs,
                                                                         strict=True)})
            for item in items:
                if item.history:
                    continue
                lex = lexical.search(conn, item.question, lexical.CANDIDATES, TABLE)
                vec = vector.search(conn, embed_query(item.question), lexical.CANDIDATES, TABLE)
                rows.append({
                    "id": item.id, "split": item.split, "lang": item.lang,
                    "category": item.category, "answerable": item.expected_behavior == "answer",
                    "vector": best(vec, "vector"), "bm25": best(lex, "bm25"),
                    "trigram": best(lex, "trigram"),
                    "top_vector_chunk": vec[0].id if vec else None,
                })
        finally:
            conn.execute(f"drop table {TABLE}")
    return rows


def summarize(rows: Sequence[dict]) -> dict:
    out: dict = {}
    for split in ("dev", "test"):
        part = [r for r in rows if r["split"] == split]
        pos = [r for r in part if r["answerable"]]
        neg = [r for r in part if not r["answerable"]]
        out[split] = {
            "positives": len(pos), "negatives": len(neg),
            "auc": {s: round(auc([r[s] for r in pos], [r[s] for r in neg]), 3)
                    for s in SIGNALS},
        }
    dev_pos = [r["vector"] for r in rows if r["split"] == "dev" and r["answerable"]]
    cut = cut_keeping_all(dev_pos)
    out["vector_cut_from_dev"] = {
        split: at_cut([r for r in rows if r["split"] == split], "vector", cut)
        for split in ("dev", "test")
    }
    return out


def main() -> int:
    db_url = os.environ.get("DATABASE_URL")
    model = e5.from_env()
    if not db_url or model is None:
        print("DATABASE_URL and EMBEDDING_MODEL_DIR are required (see the module docstring)",
              file=sys.stderr)
        return 2
    rows = measure(db_url, load_d1(D1_PATH), model.embed_query, model.embed_passages)
    summary = summarize(rows)
    print(write_results({"strategy": STRATEGY, "query": "Q0", "rows": rows,
                         "summary": summary}, f"abstain-{STRATEGY}-R3-e5-small-Q0"))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    for r in sorted(rows, key=lambda r: r["vector"]):
        mark = "+" if r["answerable"] else "-"
        print(f"{mark} {r['id']} {r['split']:4} {r['category']:14} vec={r['vector']:.3f} "
              f"bm25={r['bm25']:.2f} tri={r['trigram']:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
