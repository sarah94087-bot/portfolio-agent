"""Conversations in the database (migration 0004).

History follows docs/06-agent-design.md, section 5: the last 6 turns, as text only. Tool
results of earlier turns are not kept in the context; only the ids of the chunks they returned,
so a later answer may still cite a chunk retrieved before.
"""

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import psycopg
from psycopg import sql

HISTORY_TURNS = 6


@dataclass(frozen=True)
class StoredAnswer:
    id: UUID
    conversation_id: UUID
    content: str
    model: str | None
    usage: dict[str, Any]
    meta: dict[str, Any]


def find_answer(conn: psycopg.Connection, idempotency_key: str,
                visitor_id: str | None) -> StoredAnswer | None:
    """Only the visitor's own answers: a key someone else used replays nothing to you."""
    row = conn.execute(
        "select m.id, m.conversation_id, m.content, m.model, m.usage, m.meta"
        " from messages m join conversations c on c.id = m.conversation_id"
        " where m.role = 'assistant' and m.idempotency_key = %s"
        " and c.visitor_id is not distinct from %s",
        (idempotency_key, visitor_id),
    ).fetchone()
    return StoredAnswer(*row) if row else None


def open_conversation(
    conn: psycopg.Connection, conversation_id: UUID | None, company_slug: str | None = None,
    visitor_id: str | None = None,
) -> UUID:
    """The conversation to continue, or a new one when none is given, it is gone (expired
    after 30 days, say) or it is someone else's: the visitor then starts over instead of
    getting an error, and never sees another visitor's history."""
    if conversation_id is not None:
        row = conn.execute(
            "select id from conversations where id = %s and visitor_id is not distinct from %s",
            (conversation_id, visitor_id),
        ).fetchone()
        if row:
            return row[0]
    return conn.execute(
        "insert into conversations (company_slug, visitor_id) values (%s, %s) returning id",
        (company_slug, visitor_id),
    ).fetchone()[0]


@dataclass(frozen=True)
class PendingQuestion:
    message_id: UUID
    conversation_id: UUID


def find_question(conn: psycopg.Connection, idempotency_key: str,
                  visitor_id: str | None) -> PendingQuestion | None:
    """A question this visitor already sent under this key and that has no answer: the stream
    dropped before the answer was saved (US-10.5). Only the visitor's own, as find_answer."""
    row = conn.execute(
        "select m.id, m.conversation_id from messages m"
        " join conversations c on c.id = m.conversation_id"
        " where m.role = 'user' and m.idempotency_key = %s"
        " and c.visitor_id is not distinct from %s"
        " order by m.created_at desc limit 1",
        (idempotency_key, visitor_id),
    ).fetchone()
    return PendingQuestion(*row) if row else None


def history(conn: psycopg.Connection, conversation_id: UUID,
            turns: int = HISTORY_TURNS, exclude: UUID | None = None) -> list[dict[str, str]]:
    """The last turns, without `exclude`: a resent question, which the loop adds itself."""
    rows = conn.execute(
        "select role, content from messages where conversation_id = %s"
        " and id is distinct from %s"
        " order by created_at desc, role asc limit %s",
        (conversation_id, exclude, turns * 2),
    ).fetchall()
    messages = [{"role": r, "content": c} for r, c in reversed(rows)]
    while messages and messages[0]["role"] != "user":  # start on a question, not an answer
        messages.pop(0)
    return messages


def retrieved_chunks(conn: psycopg.Connection, conversation_id: UUID) -> frozenset[str]:
    rows = conn.execute(
        "select meta -> 'allowed_chunks' from messages"
        " where conversation_id = %s and role = 'assistant'",
        (conversation_id,),
    ).fetchall()
    return frozenset(cid for (ids,) in rows if ids for cid in ids)


def save_user(conn: psycopg.Connection, conversation_id: UUID, content: str,
              idempotency_key: str | None = None) -> UUID | None:
    """None when the same question is already saved in this conversation: the same message
    sent twice at once, and the other request saved it."""
    row = conn.execute(
        "insert into messages (conversation_id, role, content, idempotency_key)"
        " values (%s, 'user', %s, %s)"
        " on conflict (conversation_id, idempotency_key) where role = 'user' do nothing"
        " returning id",
        (conversation_id, content, idempotency_key),
    ).fetchone()
    return row[0] if row else None


def save_answer(
    conn: psycopg.Connection, *, message_id: UUID, conversation_id: UUID, content: str,
    model: str | None, prompt_version: str, usage: dict[str, Any], meta: dict[str, Any],
    idempotency_key: str, steps: list[dict[str, Any]],
) -> None:
    with conn.transaction():
        conn.execute(
            "insert into messages (id, conversation_id, role, content, model, prompt_version,"
            " usage, meta, idempotency_key) values (%s, %s, 'assistant', %s, %s, %s, %s, %s, %s)",
            (message_id, conversation_id, content, model, prompt_version, json.dumps(usage),
             json.dumps(meta, ensure_ascii=False), idempotency_key),
        )
        for s in merge_steps(steps):
            conn.execute(
                "insert into steps (message_id, step_id, kind, name, args, result_summary,"
                " duration_ms) values (%s, %s, %s, %s, %s, %s, %s)",
                (message_id, s.get("step_id"), s.get("kind"), s.get("name"),
                 json.dumps(s.get("args"), ensure_ascii=False),
                 json.dumps(s.get("summary"), ensure_ascii=False), s.get("duration_ms")),
            )


def merge_steps(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per step: its start (name, args) and its end (summary, duration) together. A
    restart stays a row of its own, since it records a switch of model."""
    merged: dict[tuple[str, bool], dict[str, Any]] = {}
    for e in events:
        key = (e.get("step_id"), e.get("status") == "restart")
        merged[key] = {**merged.get(key, {}), **{k: v for k, v in e.items() if v is not None}}
    return list(merged.values())


def chunk_sources(conn: psycopg.Connection, ids: list[str], table: str = "chunks") -> list[tuple]:
    """(id, record_id, text) of the cited chunks, in citation order, for the sources event."""
    rows = {r[0]: r for r in conn.execute(
        sql.SQL("select id, record_id, text from {} where id = any(%s)")
        .format(sql.Identifier(table)), (ids,),
    ).fetchall()}
    return [rows[i] for i in ids if i in rows]
