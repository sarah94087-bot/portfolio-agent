import math

import pytest

from retrieval.metrics import first_hits, ndcg_at, recall_at, reciprocal_rank

GOLD = {"rls#decisions", "rls#architecture"}


def test_each_gold_chunk_counts_once_at_its_first_rank():
    ranked = [["x#problem"], ["rls#decisions"], ["rls#decisions"], ["rls#architecture"]]
    assert first_hits(ranked, GOLD) == {"rls#decisions": 2, "rls#architecture": 4}


def test_a_chunk_that_covers_two_gold_sections_finds_both():
    ranked = [["rls#problem", "rls#architecture", "rls#decisions"]]
    assert first_hits(ranked, GOLD) == {"rls#architecture": 1, "rls#decisions": 1}


def test_recall_at_k_is_the_share_of_gold_chunks_in_the_top_k():
    hits = {"rls#decisions": 2, "rls#architecture": 4}
    assert recall_at(hits, 2, 3) == 0.5
    assert recall_at(hits, 2, 5) == 1.0
    assert recall_at({}, 2, 10) == 0.0


def test_reciprocal_rank_is_one_over_the_first_gold_rank():
    assert reciprocal_rank({"rls#decisions": 2, "rls#architecture": 4}) == 0.5
    assert reciprocal_rank({}) == 0.0


def test_ndcg_matches_a_hand_computation():
    # Gold at ranks 2 and 4: (1/log2(3) + 1/log2(5)) / (1/log2(2) + 1/log2(3))
    hits = {"rls#decisions": 2, "rls#architecture": 4}
    expected = (1 / math.log2(3) + 1 / math.log2(5)) / (1 + 1 / math.log2(3))
    assert ndcg_at(hits, 2, 5) == pytest.approx(expected)
    assert ndcg_at({"rls#decisions": 1, "rls#architecture": 2}, 2, 5) == pytest.approx(1.0)


def test_ndcg_ignores_ranks_past_k_and_is_capped_at_one():
    assert ndcg_at({"rls#decisions": 6}, 1, 5) == 0.0
    # A C4 record holding both gold sections at rank 1 beats the one-per-rank ideal.
    assert ndcg_at({"rls#decisions": 1, "rls#architecture": 1}, 2, 5) == 1.0
