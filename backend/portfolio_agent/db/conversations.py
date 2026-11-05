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


def find_answer(conn: psycopg.Connection, idempotency_key: str) -> StoredAnswer | None:
    row = conn.execute(
        "select id, conversation_id, content, model, usage, meta from messages"
        " where role = 'assistant' and idempotency_key = %s",
        (idempotency_key,),
    ).fetchone()
    return StoredAnswer(*row) if row else None


def open_conversation(
    conn: psycopg.Connection, conversation_id: UUID | None, company_slug: str | None = None
) -> UUID:
    """The conversation to continue, or a new one when none is given or it is gone (expired
    after 30 days, say): the visitor then starts over instead of getting an error."""
    if conversation_id is not None:
        row = conn.execute("select id from conversations where id = %s",
                           (conversation_id,)).fetchone()
        if row:
            return row[0]
    return conn.execute(
        "insert into conversations (company_slug) values (%s) returning id", (company_slug,)
    ).fetchone()[0]


def history(conn: psycopg.Connection, conversation_id: UUID,
            turns: int = HISTORY_TURNS) -> list[dict[str, str]]:
    rows = conn.execute(
        "select role, content from messages where conversation_id = %s"
        " order by created_at desc, role asc limit %s",
        (conversation_id, turns * 2),
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


def save_user(conn: psycopg.Connection, conversation_id: UUID, content: str) -> UUID:
    return conn.execute(
        "insert into messages (conversation_id, role, content) values (%s, 'user', %s)"
        " returning id",
        (conversation_id, content),
    ).fetchone()[0]


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
