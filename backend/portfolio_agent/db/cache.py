"""The response cache (docs/06-agent-design.md, section 7; migration 0006).

Only the first question of a conversation, since a follow-up depends on what came before; in
practice these are mostly the starter questions, which repeat the most. The key is the
normalized question, the prompt version, the knowledge base version and the language, so a
change to the portfolio or the prompt misses by itself, with nothing to clear.

The knowledge base version is a hash of every chunk's content hash, read from the table the
answer was searched in: an ingest that changes one chunk changes it, and one that changes
nothing leaves it alone, which a commit sha would not.

Only a clean answer is stored: no guard block, no model switch, no round cut short. A cached
answer replays the original trace and is marked as cached, so it never looks freshly made.
"""

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import psycopg
from psycopg import sql

from portfolio_agent.agent.guard import language

TTL = timedelta(days=7)
_SPACE = re.compile(r"\s+")
_EDGES = " \t\"'`?!.,:;׳״“”‘’()[]"


def normalize(question: str) -> str:
    """Case, width, spacing and end punctuation do not change the answer; words do."""
    text = unicodedata.normalize("NFKC", question).casefold()
    return _SPACE.sub(" ", text).strip(_EDGES)


def kb_version(conn: psycopg.Connection, table: str = "chunks") -> str:
    row = conn.execute(
        sql.SQL("select md5(coalesce(string_agg(id || ':' || content_hash, ',' order by id), ''))"
                " from {}").format(sql.Identifier(table))
    ).fetchone()
    return row[0]


def key(question: str, prompt_version: str, kb: str) -> str:
    q = normalize(question)
    parts = [q, prompt_version, kb, language(question)]
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()


@dataclass(frozen=True)
class Cached:
    content: str
    steps: list[dict[str, Any]]
    model: str | None
    allowed_chunks: list[str]
    created_at: str
    card: dict[str, Any] | None = None  # a job match report; `content` is then its summary
    cards: list[dict[str, Any]] | None = None  # project cards and diagrams


def get(conn: psycopg.Connection, key_hash: str, now: datetime) -> Cached | None:
    row = conn.execute(
        "update response_cache set hits = hits + 1 where key_hash = %s and expires_at > %s"
        " returning response",
        (key_hash, now),
    ).fetchone()
    return Cached(**row[0]) if row else None


def put(conn: psycopg.Connection, key_hash: str, entry: Cached, now: datetime) -> None:
    """The first answer wins until it expires; then the next one takes its place."""
    conn.execute(
        "insert into response_cache (key_hash, response, created_at, expires_at)"
        " values (%s, %s, %s, %s) on conflict (key_hash) do update"
        " set response = excluded.response, hits = 0, created_at = excluded.created_at,"
        " expires_at = excluded.expires_at where response_cache.expires_at <= excluded.created_at",
        (key_hash, json.dumps(entry.__dict__, ensure_ascii=False), now, now + TTL),
    )
