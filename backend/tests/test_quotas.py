"""Limits in quota_counters. Runs only when TEST_DATABASE_URL is set (CI, or local)."""

import os
import uuid
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from portfolio_agent import migrate
from portfolio_agent.guards import visitor
from portfolio_agent.guards.quotas import Denied, Limits, ProviderQuota, admit, bump

DB_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL not set")
NOW = datetime(2026, 11, 5, 12, 30, 15, tzinfo=UTC)


@pytest.fixture
def conn():
    migrate.run(DB_URL)
    with psycopg.connect(DB_URL, autocommit=True) as c:
        yield c


def conversation(conn, visitor_id):
    return conn.execute("insert into conversations (visitor_id) values (%s) returning id",
                        (visitor_id,)).fetchone()[0]


DEFAULT = Limits()


def ask(conn, vid, cid, now=NOW, limits=DEFAULT, ip=None):
    admit(conn, visitor_id=vid, ip_hash=ip or f"ip-{uuid.uuid4().hex}", conversation_id=cid,
          now=now, limits=limits)


def count(conn, scope, key):
    row = conn.execute("select count from quota_counters where scope = %s and key = %s"
                       " and day = %s", (scope, key, NOW.date())).fetchone()
    return row[0] if row else 0


def test_bump_adds_and_returns_the_new_count(conn):
    key = uuid.uuid4().hex
    assert bump(conn, "t", key, NOW.date()) == 1
    assert bump(conn, "t", key, NOW.date(), 3) == 4
    assert bump(conn, "t", key, NOW.date() + timedelta(days=1)) == 1  # a new day


def test_the_seventh_message_in_a_minute_is_refused_and_the_next_minute_is_open(conn):
    vid = uuid.uuid4().hex
    cid = conversation(conn, vid)
    for _ in range(6):
        ask(conn, vid, cid)
    with pytest.raises(Denied) as e:
        ask(conn, vid, cid)
    assert e.value.limit == "minute" and e.value.retry_after == 45 and e.value.retryable
    ask(conn, vid, cid, now=NOW + timedelta(minutes=1))


def test_a_refused_message_counts_nothing(conn):
    vid = uuid.uuid4().hex
    cid = conversation(conn, vid)
    limits = Limits(visitor_day=2)
    ask(conn, vid, cid, limits=limits)
    ask(conn, vid, cid, limits=limits)
    with pytest.raises(Denied) as e:
        ask(conn, vid, cid, limits=limits)
    assert e.value.limit == "visitor_day"
    assert e.value.retry_after == 11 * 3600 + 29 * 60 + 45 + 1  # until UTC midnight
    assert count(conn, "visitor", vid) == 2
    assert count(conn, "visitor_minute", f"{vid}:1230") == 2  # rolled back with the day


def test_one_address_is_limited_across_visitors(conn):
    ip = "ip-" + uuid.uuid4().hex
    limits = Limits(ip_day=3)
    for _ in range(3):
        vid = uuid.uuid4().hex
        ask(conn, vid, conversation(conn, vid), limits=limits, ip=ip)
    vid = uuid.uuid4().hex
    with pytest.raises(Denied) as e:
        ask(conn, vid, conversation(conn, vid), limits=limits, ip=ip)
    assert e.value.limit == "ip_day"
    assert count(conn, "visitor", vid) == 0


def test_a_full_conversation_is_refused_without_retry(conn):
    vid = uuid.uuid4().hex
    cid = conversation(conn, vid)
    for _ in range(3):
        conn.execute("insert into messages (conversation_id, role, content)"
                     " values (%s, 'user', 'q')", (cid,))
    with pytest.raises(Denied) as e:
        ask(conn, vid, cid, limits=Limits(conversation=3))
    assert e.value.limit == "conversation" and not e.value.retryable


def test_the_ip_hash_is_stable_within_a_day_and_changes_the_next(conn):
    day = NOW.date() + timedelta(days=uuid.uuid4().int % 10_000 + 1)  # a day no other run used
    h1 = visitor.ip_hash(conn, "1.2.3.4", day)
    assert visitor.ip_hash(conn, "1.2.3.4", day) == h1
    assert visitor.ip_hash(conn, "1.2.3.5", day) != h1
    assert visitor.ip_hash(conn, "1.2.3.4", day + timedelta(days=1)) != h1
    assert "1.2.3.4" not in h1


def test_a_model_is_closed_by_a_day_429_or_by_the_visitor_share_of_its_tokens(conn):
    now = NOW + timedelta(days=uuid.uuid4().int % 10_000 + 1)
    quota = ProviderQuota(conn, now, Limits(model_day_tokens=1000))
    m1, m2, m3 = (f"m-{uuid.uuid4().hex}" for _ in range(3))
    quota.close(m1, now.timestamp() + 600)
    quota.close(m1, now.timestamp() + 60)  # an earlier time never shortens the pause
    quota.spend(m2, 500)
    quota.spend(m2, 300)  # 800 = 80% of 1000
    quota.spend(m3, 799)
    closed = quota.closed()
    assert closed[m1] == (now.timestamp() + 600, "rate_day")
    assert closed[m2][0] > now.timestamp() and m3 not in closed
    later = ProviderQuota(conn, now + timedelta(minutes=11), quota.limits)
    assert m1 not in later.closed() and m2 in later.closed()
