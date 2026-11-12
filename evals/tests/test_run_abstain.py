from portfolio_agent.retrieval.lexical import Hit

from retrieval.run_abstain import at_cut, auc, best, cut_keeping_all


def test_auc_is_one_when_every_positive_is_higher_and_half_on_ties():
    assert auc([0.9, 0.8], [0.1, 0.2]) == 1.0
    assert auc([0.5], [0.5]) == 0.5
    assert auc([0.1], [0.9]) == 0.0


def test_best_ignores_missing_scores_and_is_zero_when_nothing_matched():
    hits = [Hit("a", "r", (), "", {"bm25": None}), Hit("b", "r", (), "", {"bm25": 2.0})]
    assert best(hits, "bm25") == 2.0
    assert best([], "bm25") == 0.0


def test_the_cut_from_dev_keeps_every_positive_and_reports_what_it_catches():
    rows = [
        {"id": "p1", "answerable": True, "vector": 0.80},
        {"id": "p2", "answerable": True, "vector": 0.75},
        {"id": "n1", "answerable": False, "vector": 0.70},
        {"id": "n2", "answerable": False, "vector": 0.78},
    ]
    cut = cut_keeping_all([r["vector"] for r in rows if r["answerable"]])
    out = at_cut(rows, "vector", cut)
    assert out["positives_lost"] == []
    assert out["negatives_caught"] == ["n1"]
