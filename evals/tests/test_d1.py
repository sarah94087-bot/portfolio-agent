"""Checks on the real D1 golden set (evals/datasets/d1.yaml) against the real knowledge base.

Overlap: the share of a question's content words (normalized, stopwords removed) that also appear
in its gold chunks. A question that copies its record's wording measures string matching, not
retrieval (docs/03-evaluation-methodology.md). MAX_OVERLAP is set from the data: on the first draft
most English questions scored 0.0-0.5, and the two above 0.5 were reworded. Short skill questions
("Can she code in Java?") reach 0.5 because the skill name has to be in the question.
"""

import re
from collections import Counter
from pathlib import Path

import pytest
from portfolio_agent.ingest import chunk, load
from portfolio_agent.retrieval.lexical import STOPWORDS
from portfolio_agent.retrieval.normalize import normalize

from retrieval.harness import check_gold, load_d1

D1_PATH = Path(__file__).resolve().parents[1] / "datasets" / "d1.yaml"
MAX_OVERLAP = 0.5
_STOP = set(STOPWORDS)


def content_words(text: str) -> list[str]:
    return [w for w in re.findall(r"\w+", normalize(text)) if len(w) > 1 and w not in _STOP]


@pytest.fixture(scope="module")
def items():
    return load_d1(D1_PATH)


@pytest.fixture(scope="module")
def gold_text():
    text: dict[str, str] = {}
    for c in chunk(load(), "C1"):
        for s in c.sections:
            key = f"{c.record_id}#{s}"
            text[key] = f"{text.get(key, '')} {c.text}"
    return text


def overlap(question: str, gold: str) -> float:
    q = content_words(question)
    g = set(content_words(gold))
    return sum(w in g for w in q) / len(q) if q else 0.0


def test_size_and_categories(items):
    assert len(items) == 96
    counts = Counter(i.category for i in items)
    assert counts == {
        "single_hop": 23, "multi_hop": 18, "comparative": 6, "skill_level": 10,
        "overview_limit": 5, "unanswerable": 12, "off_topic": 5, "cross_lingual": 17,
    }


def test_follow_ups_have_history_in_both_languages_and_splits(items):
    follow_ups = [i for i in items if i.history]
    assert len(follow_ups) == 6
    assert all(i.category == "multi_hop" and all(h.strip() for h in i.history)
               for i in follow_ups)
    assert {i.lang for i in follow_ups} == {"he", "en"}
    assert {i.split for i in follow_ups} == {"dev", "test"}


def test_every_category_has_test_questions(items):
    for category in {i.category for i in items}:
        assert any(i.category == category and i.split == "test" for i in items), category


def test_gold_chunks_exist(items, gold_text):
    assert check_gold(items, set(gold_text)) == []


def test_cross_lingual_questions_are_hebrew(items):
    assert all(i.lang == "he" for i in items if i.category == "cross_lingual")


def test_questions_do_not_copy_their_records(items, gold_text):
    too_close = {
        i.id: round(overlap(i.question, " ".join(gold_text[g] for g in i.gold_chunks)), 2)
        for i in items if i.gold_chunks
    }
    assert {k: v for k, v in too_close.items() if v > MAX_OVERLAP} == {}
