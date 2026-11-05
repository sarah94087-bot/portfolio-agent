"""The response cache key, and expiry in the database (the latter needs TEST_DATABASE_URL)."""

import os
import uuid
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from portfolio_agent import migrate
from portfolio_agent.db import cache

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


def test_spacing_case_width_and_end_punctuation_do_not_change_the_key():
    k = cache.key("Did she build an MCP server?", "system.v1", "kb")
    for same in ["did she build an mcp server", "  Did   she build an MCP server?! ",
                 "Did she build an ＭＣＰ server."]:
        assert cache.key(same, "system.v1", "kb") == k


def test_words_prompt_and_knowledge_base_change_the_key():
    k = cache.key("Did she build an MCP server?", "system.v1", "kb")
    assert cache.key("Did she build a MCP server?", "system.v1", "kb") != k
    assert cache.key("Did she build an MCP server?", "system.v2", "kb") != k
    assert cache.key("Did she build an MCP server?", "system.v1", "kb2") != k


def test_hebrew_is_normalized_too():
    assert cache.key("האם היא בנתה שרת MCP?", "v", "kb") == cache.key(" האם  היא בנתה שרת MCP ",
                                                                          "v", "kb")


db = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set")


@db
def test_an_entry_expires_and_the_next_answer_replaces_it():
    url = os.environ["TEST_DATABASE_URL"]
    migrate.run(url)
    entry = lambda text: cache.Cached(text, [], "m", [], NOW.isoformat())  # noqa: E731
    k = uuid.uuid4().hex
    with psycopg.connect(url, autocommit=True) as conn:
        cache.put(conn, k, entry("first"), NOW)
        cache.put(conn, k, entry("second"), NOW + timedelta(hours=1))  # not expired: kept
        assert cache.get(conn, k, NOW + timedelta(days=1)).content == "first"
        assert cache.get(conn, k, NOW + cache.TTL) is None  # expired
        cache.put(conn, k, entry("third"), NOW + cache.TTL)
        assert cache.get(conn, k, NOW + cache.TTL + timedelta(hours=1)).content == "third"
