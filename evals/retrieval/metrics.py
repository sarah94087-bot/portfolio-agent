"""Retrieval metrics per question: Recall@k, MRR and nDCG@k (docs/03-evaluation-methodology.md, 3).

Gold chunks are C1 ids. A retrieved chunk is given as the C1 ids it covers, so a C3 window
or a C4 record finds a gold section when it contains it. Each gold chunk counts once, at the
first rank that holds it.
"""

import math
from collections.abc import Sequence


def first_hits(ranked: Sequence[Sequence[str]], gold: set[str]) -> dict[str, int]:
    """1-based rank at which each gold chunk first appears. ranked[i] is what chunk i covers."""
    hits: dict[str, int] = {}
    for rank, covered in enumerate(ranked, start=1):
        for g in gold.intersection(covered):
            hits.setdefault(g, rank)
    return hits


def recall_at(hits: dict[str, int], n_gold: int, k: int) -> float:
    return sum(1 for r in hits.values() if r <= k) / n_gold


def reciprocal_rank(hits: dict[str, int]) -> float:
    return 1 / min(hits.values()) if hits else 0.0


def ndcg_at(hits: dict[str, int], n_gold: int, k: int) -> float:
    """Binary relevance. The ideal puts one gold chunk at each of the first ranks.

    A C4 record can hold two gold sections at rank 1, which beats that ideal, so the score is
    capped at 1.
    """
    dcg = sum(1 / math.log2(r + 1) for r in hits.values() if r <= k)
    idcg = sum(1 / math.log2(i + 1) for i in range(1, min(n_gold, k) + 1))
    return min(1.0, dcg / idcg)
