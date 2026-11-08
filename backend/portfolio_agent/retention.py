"""The daily retention job (.github/workflows/retention.yml): python -m portfolio_agent.retention

Deletes what the privacy page promises to delete (docs/09-security-privacy.md, section 6):
- conversations older than 30 days, with their messages, steps and feedback (on delete cascade);
- IP salts and IP hashes older than 2 days;
- quota counters older than 7 days;
- expired entries of the response cache;
- then, when Langfuse keys are set, the traces of answers that are gone (migration 0009), and
  every trace about to turn 30 days old.

Dated rows count from the start of their UTC day, so a run never keeps one past its period
because of the hour it ran at. The database part is one transaction.

A trace is deleted by id, in bulk: the Hobby plan allows 50 delete requests a day, 1000 ids each.
An id leaves the queue only after Langfuse accepted it, so a failed call is retried the next day.
Without keys the queue is kept: Vercel may hold keys that GitHub does not, and traces already sent
would otherwise never be deleted.

The age sweep catches the traces the queue cannot: a turn that ended without a saved answer has
no row to queue. It reads a window a little under 30 days back, because the Hobby plan's read API
stops at 30 days: older traces can no longer be found. The window spans more than one day, so a
missed run loses nothing. A trace goes by age even if its conversation is a little younger.

The repository is public and so are its Actions logs: only counts are printed, never ids.
"""

import logging
import os
import sys
from datetime import UTC, datetime, timedelta

import httpx
import psycopg

from portfolio_agent import tracing

log = logging.getLogger(__name__)

CONVERSATIONS = timedelta(days=30)
IP_DATA = timedelta(days=2)
COUNTERS = timedelta(days=7)
TRACE_BATCH = 1000
MAX_TRACE_BATCHES = 40  # leaves room under the 50 a day for a run by hand
# Langfuse ingests a trace with some delay, and a delete that arrives first would miss it.
TRACE_SETTLE = timedelta(hours=1)
TIMEOUT = 30.0
SWEEP_OLDEST = timedelta(days=29, hours=12)
SWEEP_NEWEST = timedelta(days=27)
SWEEP_PAGE = 1000
MAX_SWEEP_PAGES = 20
MAX_SWEEP_BATCHES = 5  # with MAX_TRACE_BATCHES, under the 50 delete requests a day


def purge(conn: psycopg.Connection, now: datetime) -> dict[str, int]:
    """Deletes everything past its period, and returns how many rows of each kind. The last read
    fails on a database without migration 0009, undoing the deletes before their ids are lost."""
    ip_day = (now - IP_DATA).date()
    steps = {
        "conversations": ("delete from conversations where created_at < %s",
                          (now - CONVERSATIONS,)),
        "ip_salts": ("delete from ip_salts where day <= %s", (ip_day,)),
        "ip_hashes": ("delete from quota_counters where scope = 'ip' and day <= %s", (ip_day,)),
        "quota_counters": ("delete from quota_counters where day <= %s",
                           ((now - COUNTERS).date(),)),
        "response_cache": ("delete from response_cache where expires_at <= %s", (now,)),
    }
    with conn.transaction():
        counts = {name: conn.execute(query, args).rowcount for name, (query, args) in steps.items()}
        counts["traces_queued"] = conn.execute("select count(*) from trace_deletions").fetchone()[0]
    return counts


def _call(client: httpx.Client, access: tracing.LangfuseAccess, method: str, path: str,
          **kwargs) -> httpx.Response | None:
    """The response, or None after logging a failure. The error type and status only: the
    message may carry the request."""
    try:
        response = client.request(method, f"{access.origin}{path}", timeout=TIMEOUT,
                                  headers={"Authorization": f"Basic {access.auth}"}, **kwargs)
    except httpx.HTTPError as e:
        log.error("langfuse %s failed: %s", method, type(e).__name__)
        return None
    if response.status_code >= 300:
        log.error("langfuse %s failed: HTTP %s", method, response.status_code)
        return None
    return response


def delete_traces(conn: psycopg.Connection, client: httpx.Client, access: tracing.LangfuseAccess,
                  now: datetime) -> tuple[int, bool]:
    """(traces accepted for deletion, whether every call succeeded). The first failure stops the
    run: more calls would only spend the day's quota."""
    done = 0
    for _ in range(MAX_TRACE_BATCHES):
        ids = [row[0] for row in conn.execute(
            "select trace_id from trace_deletions where traced_at < %s"
            " order by traced_at limit %s", (now - TRACE_SETTLE, TRACE_BATCH),
        ).fetchall()]
        if not ids:
            break
        response = _call(client, access, "DELETE", "/api/public/traces",
                         json={"traceIds": [i.hex for i in ids]})  # the form a trace is sent under
        if response is None:
            return done, False
        conn.execute("delete from trace_deletions where trace_id = any(%s)", (ids,))
        done += len(ids)
    return done, True


def _old_trace_ids(client: httpx.Client, access: tracing.LangfuseAccess,
                   now: datetime) -> list[str] | None:
    """The ids of the traces in the window, or None when a page could not be read. The window
    stays fixed from page to page, and a page may be empty and still have a cursor."""
    window = {"fromStartTime": f"{now - SWEEP_OLDEST:%Y-%m-%dT%H:%M:%SZ}",
              "toStartTime": f"{now - SWEEP_NEWEST:%Y-%m-%dT%H:%M:%SZ}",
              "fields": "core", "limit": SWEEP_PAGE}
    found: set[str] = set()
    cursor = None
    for _ in range(MAX_SWEEP_PAGES):
        response = _call(client, access, "GET", "/api/public/v2/observations",
                         params={**window, **({"cursor": cursor} if cursor else {})})
        if response is None:
            return None
        try:
            page = response.json()
            found.update(row["traceId"] for row in page["data"] if row.get("traceId"))
            cursor = page["meta"].get("cursor")
        except (ValueError, KeyError, TypeError, AttributeError):
            log.error("langfuse GET failed: unexpected response")
            return None
        if not cursor:
            break
    return sorted(found)


def sweep_old_traces(client: httpx.Client, access: tracing.LangfuseAccess,
                     now: datetime) -> tuple[int, bool]:
    """(traces accepted for deletion, whether every call succeeded)."""
    ids = _old_trace_ids(client, access, now)
    if ids is None:
        return 0, False
    done = 0
    for start in range(0, min(len(ids), MAX_SWEEP_BATCHES * TRACE_BATCH), TRACE_BATCH):
        batch = ids[start:start + TRACE_BATCH]
        if _call(client, access, "DELETE", "/api/public/traces",
                 json={"traceIds": batch}) is None:
            return done, False
        done += len(batch)
    return done, True


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    url = os.environ.get("DATABASE_URL_DIRECT") or os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL_DIRECT or DATABASE_URL is required", file=sys.stderr)
        return 2
    now = datetime.now(UTC)
    with psycopg.connect(url, autocommit=True, connect_timeout=10) as conn:
        counts = purge(conn, now)
        print("deleted: " + ", ".join(f"{k} {v}" for k, v in counts.items()
                                      if k != "traces_queued"))
        access = tracing.langfuse_access()
        if access is None:
            print(f"no Langfuse keys: {counts['traces_queued']} traces stay queued")
            return 0
        with httpx.Client() as client:
            done, ok = delete_traces(conn, client, access, now)
            print(f"traces accepted for deletion: {done}")
            if ok:  # after a failure, more calls would only spend the day's quota
                swept, ok = sweep_old_traces(client, access, now)
                print(f"old traces accepted for deletion: {swept}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
