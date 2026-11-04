"""R1 and the upsert, against Postgres. Runs only when TEST_DATABASE_URL is set (CI, or local
docker compose). Each test works on its own temp table cloned from chunks."""

import os
from dataclasses import replace

import psycopg
import pytest

from portfolio_agent import migrate
from portfolio_agent.ingest import chunk, load, upsert
from portfolio_agent.retrieval.lexical import search

DB_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture
def conn():
    migrate.run(DB_URL)
    with psycopg.connect(DB_URL, autocommit=True) as c:
        c.execute("create temp table t (like chunks including all)")
        yield c
        c.execute("drop table t")


@pytest.fixture(scope="module")
def c1():
    return chunk(load(), "C1")


def ids(hits):
    return [h.id for h in hits]


def test_upsert_writes_only_what_changed_and_removes_what_is_gone(conn, c1):
    assert upsert(conn, c1, "t", "abc1234") == {
        "inserted": len(c1), "updated": 0, "deleted": 0, "unchanged": 0,
    }
    assert upsert(conn, c1, "t")["unchanged"] == len(c1)
    edited = [replace(c1[0], text=c1[0].text + " More."), *c1[1:-1]]
    assert upsert(conn, edited, "t") == {
        "inserted": 0, "updated": 1, "deleted": 1, "unchanged": len(c1) - 2,
    }
    assert conn.execute("select count(*) from t").fetchone()[0] == len(c1) - 1


def test_skill_evidence_is_stored_for_the_agent_but_not_searched(conn, c1):
    upsert(conn, c1, "t")
    skill = next(c for c in c1 if c.record_id == "skills" and c.evidence)
    text, norm = conn.execute("select text, norm from t where id = %s", (skill.id,)).fetchone()
    assert "Evidence: " in text
    assert skill.evidence[0] not in norm


def test_upsert_stores_normalized_text_and_a_tsvector(conn, c1):
    upsert(conn, c1, "t")
    norm, aliases, tsv = conn.execute(
        "select norm, aliases, tsv::text from t where id = 'human-gated-translation#problem'"
    ).fetchone()
    assert norm == norm.lower()
    assert "תרגומ מכונה" in aliases  # final mem became a regular mem
    assert "'bilingual'" in tsv


def test_r1_finds_the_record_for_an_english_question(conn, c1):
    upsert(conn, c1, "t")
    hits = search(conn, "How does a human approve machine translation output?", table="t")
    assert hits[0].record_id == "human-gated-translation"
    assert set(hits[0].scores) == {"bm25", "trigram", "rrf"}


def test_r1_matches_hebrew_aliases_with_a_prefix_and_a_final_letter(conn, c1):
    upsert(conn, c1, "t")
    # בצנרת and התרגום only share trigrams with the aliases צנרת תרגום; ם is a final letter.
    hits = search(conn, "מה היה בצנרת התרגום?", table="t")
    assert "human-gated-translation" in [h.record_id for h in hits[:3]]


def test_stopwords_alone_find_nothing(conn, c1):
    upsert(conn, c1, "t")
    assert search(conn, "what did she do", table="t") == []
    assert search(conn, "", table="t") == []


def test_a_rare_word_outranks_a_common_one(conn, c1):
    # 'mobilenetv3' appears in a few chunks, 'sarah' in most of them: BM25 weighs them apart.
    upsert(conn, c1, "t")
    hits = search(conn, "Sarah MobileNetV3", table="t")
    has_rare = ["mobilenetv3" in h.text.lower() for h in hits]
    assert has_rare[0]
    # Every chunk with the rare word ranks above every chunk with only the common one.
    assert has_rare == sorted(has_rare, reverse=True)


def test_r1_returns_at_most_k_and_is_deterministic(conn, c1):
    upsert(conn, c1, "t")
    first = search(conn, "PostgreSQL row level security policies", k=5, table="t")
    assert len(first) == 5
    assert ids(first) == ids(search(conn, "PostgreSQL row level security policies", k=5, table="t"))


def test_r1_works_on_every_strategy(conn):
    docs = load()
    for strategy in ("C1", "C2", "C3", "C4"):
        conn.execute("truncate t")
        upsert(conn, chunk(docs, strategy), "t")
        # k = 5, what search_portfolio returns (docs/04-retrieval-design.md, section 8). The
        # VAST record also says 'weed detection on CPU', and skill chunks name their evidence
        # records by id, so 'skills#minio' matches too. Whether that costs recall is for D1.
        hits = search(conn, "weed detection on CPU", k=5, table="t")
        assert "weed-detection-pipeline" in [h.record_id for h in hits], strategy
