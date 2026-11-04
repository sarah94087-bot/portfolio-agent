"""R3: R1 and R2 fused with Reciprocal Rank Fusion, k = 60 (docs/04-retrieval-design.md, axis B).

The two rankings are fused as two lists, so lexical and vector search weigh the same. R1 is
itself a fusion of BM25 and trigrams, but here it counts as one ranking: R3 is "R1 and R2",
not three equal voices of which two are lexical. Each side brings its top CANDIDATES, as in the
search_portfolio contract (docs/04, section 8).
"""

from collections.abc import Sequence

import psycopg

from portfolio_agent.retrieval import lexical, vector
from portfolio_agent.retrieval.lexical import CANDIDATES, RRF_K, Hit


def rrf(rankings: Sequence[Sequence[str]], k: int = RRF_K) -> list[tuple[str, float]]:
    """Ids by the sum of 1 / (k + rank) over the rankings they appear in, best first.

    Ties go by id, so the order is the same on every run.
    """
    fused: dict[str, float] = {}
    for ranked in rankings:
        for rank, cid in enumerate(ranked, start=1):
            fused[cid] = fused.get(cid, 0.0) + 1 / (k + rank)
    return sorted(fused.items(), key=lambda item: (-item[1], item[0]))


def search(
    conn: psycopg.Connection, query: str, query_vector: Sequence[float], k: int = 10,
    table: str = "chunks",
) -> list[Hit]:
    """The k chunks with the best fused rank. The caller embeds the query, as for R2."""
    lex = lexical.search(conn, query, CANDIDATES, table)
    vec = vector.search(conn, query_vector, CANDIDATES, table)
    fused = rrf([[h.id for h in lex], [h.id for h in vec]])[:k]
    by_id = {h.id: h for h in vec} | {h.id: h for h in lex}
    lex_scores = {h.id: h.scores["rrf"] for h in lex}
    vec_scores = {h.id: h.scores["vector"] for h in vec}
    return [
        Hit(
            cid, by_id[cid].record_id, by_id[cid].sections, by_id[cid].text,
            {"lexical": lex_scores.get(cid), "vector": vec_scores.get(cid), "rrf": score},
        )
        for cid, score in fused
    ]
