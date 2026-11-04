from portfolio_agent.retrieval.lexical import Hit
from portfolio_agent.retrieval.rerank import apply_order, candidates_block, truncate


def hit(cid: str, text: str = "text") -> Hit:
    return Hit(cid, cid.split("#")[0], ("s",), text, {"rrf": 0.1})


def test_truncate_cuts_at_the_token_limit_and_says_so():
    assert truncate("one two three", 5) == "one two three"
    assert truncate("one two three four", 2) == "one two …"
    assert truncate("a, b", 2) == "a, …"  # punctuation is a token, as in ingest


def test_candidates_block_shows_every_id_with_the_start_of_its_text():
    block = candidates_block([hit("a#all", "alpha beta gamma"), hit("b#all", "delta")], 2)
    assert block == "[a#all]\nalpha beta …\n\n[b#all]\ndelta"


def test_apply_order_follows_the_model_and_keeps_what_it_left_out():
    hits = [hit("a#1"), hit("b#1"), hit("c#1"), hit("d#1")]
    out = apply_order(hits, ["c#1", "x#9", "a#1", "c#1"])
    assert [h.id for h in out] == ["c#1", "a#1", "b#1", "d#1"]
    assert [h.scores["rerank"] for h in out] == [1, 2, 3, 4]
    assert out[0].scores["rrf"] == 0.1
    assert [h.id for h in apply_order(hits, [])] == ["a#1", "b#1", "c#1", "d#1"]
