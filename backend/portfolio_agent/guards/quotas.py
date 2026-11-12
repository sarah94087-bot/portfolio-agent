"""Limits and quotas in quota_counters (docs/09-security-privacy.md, section 4).

Every count goes up with one atomic upsert that returns the new value, so two requests at
once cannot both take the last slot. The checks of one message run in one transaction: when
one limit says no, the counts it already raised roll back, so a refused message costs nothing.

Days are UTC days, the day Groq's quota resets on.

The provider side: tokens are counted per model, and a model whose visitor share of the day
is spent (80% of its quota, the rest left for CI) is closed until midnight, like a model that
returned a day 429. Both states live here, so they survive a cold start and every instance
sees them (docs/06-agent-design.md, section 4).
"""

import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import psycopg


@dataclass(frozen=True)
class Limits:
    message_chars: int = 1000
    visitor_day: int = 30
    visitor_minute: int = 6
    ip_day: int = 60
    conversation: int = 30
    feedback_day: int = 50  # ratings and comments per visitor; a change of mind counts too
    image_day: int = 3  # screenshots read per visitor a day; the model is the backup's (ADR-0022)
    model_day_tokens: int = 200_000  # Groq, per model per org (verified in M1)
    visitor_share: float = 0.8

    @property
    def model_visitor_tokens(self) -> int:
        return int(self.model_day_tokens * self.visitor_share)

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Limits":
        env = dict(os.environ) if env is None else env
        names = {"visitor_day": "LIMIT_VISITOR_DAY", "visitor_minute": "LIMIT_VISITOR_MINUTE",
                 "ip_day": "LIMIT_IP_DAY", "conversation": "LIMIT_CONVERSATION",
                 "feedback_day": "LIMIT_FEEDBACK_DAY", "image_day": "LIMIT_IMAGE_DAY",
                 "model_day_tokens": "MODEL_DAY_TOKENS"}
        return cls(**{field: int(env[var]) for field, var in names.items() if env.get(var)})


class Denied(Exception):
    """A limit said no. `code` and `retryable` go to the SSE error as they are."""

    def __init__(self, limit: str, message: str, retry_after: int | None):
        super().__init__(limit)
        self.code = "rate_limited"
        self.limit = limit  # minute | visitor_day | ip_day | conversation
        self.message = message
        self.retry_after = retry_after
        self.retryable = retry_after is not None


def bump(conn: psycopg.Connection, scope: str, key: str, day: date, n: int = 1) -> int:
    return conn.execute(
        "insert into quota_counters (scope, key, day, count) values (%s, %s, %s, %s)"
        " on conflict (scope, key, day) do update set count = quota_counters.count + excluded.count"
        " returning count",
        (scope, key, day, n),
    ).fetchone()[0]


def _to_midnight(now: datetime) -> int:
    midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), UTC)
    return int((midnight - now).total_seconds()) + 1


def admit(conn: psycopg.Connection, *, visitor_id: str, ip_hash: str, conversation_id: UUID,
          now: datetime, limits: Limits, cost: int = 1, resent: bool = False,
          image: bool = False) -> None:
    """Counts one message, or raises Denied and counts nothing. `cost` is 3 for a job match.
    `resent`: the question is already saved in the conversation (chat.py), so it is not a new
    one there; the visitor and IP limits still count it, as the model runs again."""
    asked = conn.execute(
        "select count(*) from messages where conversation_id = %s and role = 'user'",
        (conversation_id,),
    ).fetchone()[0] - resent
    if asked >= limits.conversation:
        raise Denied("conversation", "This conversation is full. Start a new one.", None)
    day = now.date()
    with conn.transaction():
        if bump(conn, "visitor_minute", f"{visitor_id}:{now:%H%M}", day, cost) \
                > limits.visitor_minute:
            raise Denied("minute", "Too many messages in a minute.", 60 - now.second)
        if bump(conn, "visitor", visitor_id, day, cost) > limits.visitor_day:
            raise Denied("visitor_day", "The daily message limit is reached.", _to_midnight(now))
        if bump(conn, "ip", ip_hash, day, cost) > limits.ip_day:
            raise Denied("ip_day", "The daily message limit is reached.", _to_midnight(now))
        if image and bump(conn, "image", visitor_id, day) > limits.image_day:
            raise Denied("image_day", "The daily screenshot limit is reached. Paste the text "
                         "instead.", _to_midnight(now))


@dataclass
class ProviderQuota:
    """The router's view of the database: which models are closed today, and the tokens spent.
    One per request, on the request's connection."""

    conn: psycopg.Connection
    now: datetime
    limits: Limits

    def closed(self) -> dict[str, tuple[float, str]]:
        """model name -> (closed until, as a Unix time; the reason)."""
        day = self.now.date()
        midnight = self.now.timestamp() + _to_midnight(self.now)
        rows = self.conn.execute(
            "select scope, key, count from quota_counters where day = %s"
            " and scope in ('provider_closed', 'provider_tokens')",
            (day,),
        ).fetchall()
        out: dict[str, tuple[float, str]] = {}
        for scope, key, count in rows:
            if scope == "provider_closed":
                until = float(count)
            elif count >= self.limits.model_visitor_tokens:
                until = midnight
            else:
                continue
            if until > self.now.timestamp() and until > out.get(key, (0.0, ""))[0]:
                out[key] = (until, "rate_day")
        return out

    def close(self, model: str, until: float) -> None:
        """A day 429: closed until `until` (Unix time), for every instance."""
        self.conn.execute(
            "insert into quota_counters (scope, key, day, count)"
            " values ('provider_closed', %s, %s, %s) on conflict (scope, key, day)"
            " do update set count = greatest(quota_counters.count, excluded.count)",
            (model, self.now.date(), int(until)),
        )

    def spend(self, model: str, tokens: int) -> None:
        if tokens > 0:
            bump(self.conn, "provider_tokens", model, self.now.date(), tokens)
