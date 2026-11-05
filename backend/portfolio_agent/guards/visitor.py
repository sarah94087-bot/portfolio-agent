"""Who is asking, without accounts (docs/05-architecture.md, section 6; docs/09, section 6).

- The visitor id is a random value in one functional cookie, signed with HMAC, so a visitor
  cannot pick someone else's id to reset a quota or open another person's conversation. The
  cookie lives 30 days and is renewed on use. No tracking, so no consent banner (docs/09).
- The IP is never stored. Only an HMAC of it with a random salt of the day, and the salt is
  deleted after 2 days, so a stored hash cannot be turned back into an address.
"""

import base64
import hashlib
import hmac
import os
import secrets
from datetime import date
from functools import cache

import psycopg

COOKIE = "pa_vid"
MAX_AGE = 30 * 24 * 3600
ENV_VAR = "VISITOR_HMAC_SECRET"


@cache
def _secret() -> bytes:
    # Without the secret (local runs), a random one per process: cookies end at a restart.
    return (os.environ.get(ENV_VAR) or secrets.token_hex(32)).encode()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _sign(visitor_id: str, secret: bytes) -> str:
    return _b64(hmac.new(secret, visitor_id.encode(), hashlib.sha256).digest()[:16])


def new_cookie(secret: bytes | None = None) -> tuple[str, str]:
    """A new visitor id and the cookie value that carries it."""
    visitor_id = _b64(secrets.token_bytes(16))
    return visitor_id, f"{visitor_id}.{_sign(visitor_id, secret or _secret())}"


def read_cookie(value: str | None, secret: bytes | None = None) -> str | None:
    """The visitor id when the cookie is ours and intact, else None."""
    if not value or value.count(".") != 1:
        return None
    visitor_id, sig = value.split(".")
    expected = _sign(visitor_id, secret or _secret())
    return visitor_id if hmac.compare_digest(sig, expected) else None


def client_ip(headers: dict[str, str], fallback: str | None) -> str:
    """Vercel puts the client's address in x-real-ip, and first in x-forwarded-for."""
    if headers.get("x-real-ip"):
        return headers["x-real-ip"].strip()
    forwarded = headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or fallback or "unknown"


def daily_salt(conn: psycopg.Connection, day: date) -> bytes:
    conn.execute(
        "insert into ip_salts (day, salt) values (%s, %s) on conflict (day) do nothing",
        (day, secrets.token_bytes(32)),
    )
    return bytes(conn.execute("select salt from ip_salts where day = %s", (day,)).fetchone()[0])


def ip_hash(conn: psycopg.Connection, ip: str, day: date) -> str:
    return hmac.new(daily_salt(conn, day), ip.encode(), hashlib.sha256).hexdigest()[:32]
