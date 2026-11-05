"""Feedback on an answer (migration 0008)."""

from uuid import UUID

import psycopg


def save(conn: psycopg.Connection, *, message_id: UUID, visitor_id: str, rating: str,
         comment: str | None, challenge: bool) -> bool:
    """Saves or replaces the rating of one answer. False when the message is not an answer
    in one of this visitor's conversations: nobody rates another visitor's answers."""
    row = conn.execute(
        "insert into feedback (message_id, rating, comment, challenge)"
        " select m.id, %s, %s, %s from messages m"
        " join conversations c on c.id = m.conversation_id"
        " where m.id = %s and m.role = 'assistant' and c.visitor_id = %s"
        " on conflict (message_id) do update set rating = excluded.rating,"
        " comment = excluded.comment, challenge = excluded.challenge, updated_at = now()"
        " returning message_id",
        (rating, comment, challenge, message_id, visitor_id),
    ).fetchone()
    return row is not None
