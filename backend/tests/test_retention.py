"""The daily retention job. The database tests run only when TEST_DATABASE_URL is set."""

import base64
import json
import logging
import os
import uuid
from datetime import UTC, date, datetime, timedelta

import httpx
import psycopg
import pytest

from portfolio_agent import migrate, retention, tracing
from portfolio_agent.db import conversations

DB_URL = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL not set")
NOW = datetime(2026, 11, 8, 2, 23, tzinfo=UTC)
TODAY = NOW.date()
ACCESS = tracing.LangfuseAccess("https://lf.test", "secret-auth")


@pytest.fixture
def conn():
    migrate.run(DB_URL)
    with psycopg.connect(DB_URL, autocommit=True) as c:
        c.execute("delete from trace_deletions")  # other tests delete conversations too
        yield c


def conversation(conn, age: timedelta, visitor_id=None):
    return conn.execute(
        "insert into conversations (visitor_id, created_at) values (%s, %s) returning id",
        (visitor_id, NOW - age)).fetchone()[0]


def message(conn, cid, role="assistant", at=NOW - timedelta(days=40)):
    return conn.execute(
        "insert into messages (conversation_id, role, content, created_at)"
        " values (%s, %s, 'text', %s) returning id", (cid, role, at)).fetchone()[0]


def queued(conn):
    return {row[0] for row in conn.execute("select trace_id from trace_deletions")}


def enqueue(conn, trace, at=NOW - timedelta(days=1)):
    conn.execute("insert into trace_deletions (trace_id, traced_at) values (%s, %s)", (trace, at))
    return trace


def exists(conn, table, column, value):
    return conn.execute(f"select 1 from {table} where {column} = %s", (value,)).fetchone() \
        is not None


def counter(conn, scope, day: date):
    key = uuid.uuid4().hex
    conn.execute("insert into quota_counters (scope, key, day, count) values (%s, %s, %s, 1)",
                 (scope, key, day))
    return key


def langfuse(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def always(status, calls):
    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"message": "ok"})
    return handler


@needs_db
def test_a_conversation_past_30_days_goes_with_everything_under_it(conn):
    cid = conversation(conn, timedelta(days=30, seconds=1))
    answer = message(conn, cid)
    conn.execute("insert into steps (message_id, step_id, kind) values (%s, 's1', 'llm')",
                 (answer,))
    conn.execute("insert into feedback (message_id, rating) values (%s, 'up')", (answer,))

    assert retention.purge(conn, NOW)["conversations"] >= 1

    assert not exists(conn, "conversations", "id", cid)
    assert not exists(conn, "messages", "id", answer)
    assert not exists(conn, "steps", "message_id", answer)
    assert not exists(conn, "feedback", "message_id", answer)


@needs_db
def test_a_conversation_within_30_days_stays(conn):
    cid = conversation(conn, timedelta(days=29, hours=23))
    answer = message(conn, cid, at=NOW)
    retention.purge(conn, NOW)
    assert exists(conn, "conversations", "id", cid)
    assert exists(conn, "messages", "id", answer)
    assert answer not in queued(conn)


@needs_db
def test_salts_and_ip_hashes_go_after_2_days_and_other_counters_stay(conn):
    for day in (TODAY - timedelta(days=1), TODAY - timedelta(days=2)):
        conn.execute("insert into ip_salts (day, salt) values (%s, 'x') on conflict do nothing",
                     (day,))
    yesterday_ip = counter(conn, "ip", TODAY - timedelta(days=1))
    old_ip = counter(conn, "ip", TODAY - timedelta(days=2))
    old_visitor = counter(conn, "visitor", TODAY - timedelta(days=2))

    retention.purge(conn, NOW)

    assert exists(conn, "ip_salts", "day", TODAY - timedelta(days=1))
    assert not exists(conn, "ip_salts", "day", TODAY - timedelta(days=2))
    assert exists(conn, "quota_counters", "key", yesterday_ip)
    assert not exists(conn, "quota_counters", "key", old_ip)
    assert exists(conn, "quota_counters", "key", old_visitor)


@needs_db
def test_counters_go_after_7_days(conn):
    kept = counter(conn, "visitor", TODAY - timedelta(days=6))
    gone = counter(conn, "provider_tokens", TODAY - timedelta(days=7))
    retention.purge(conn, NOW)
    assert exists(conn, "quota_counters", "key", kept)
    assert not exists(conn, "quota_counters", "key", gone)


@needs_db
def test_only_expired_cache_entries_go(conn):
    live, expired = uuid.uuid4().hex, uuid.uuid4().hex
    for key, expires in ((live, NOW + timedelta(seconds=1)), (expired, NOW)):
        conn.execute("insert into response_cache (key_hash, response, expires_at)"
                     " values (%s, '{}', %s)", (key, expires))
    retention.purge(conn, NOW)
    assert exists(conn, "response_cache", "key_hash", live)
    assert not exists(conn, "response_cache", "key_hash", expired)


@needs_db
def test_the_job_queues_the_traces_of_answers_and_not_of_questions(conn):
    cid = conversation(conn, timedelta(days=31))
    question, answer = message(conn, cid, "user"), message(conn, cid)
    retention.purge(conn, NOW)
    assert answer in queued(conn) and question not in queued(conn)


@needs_db
def test_the_delete_button_queues_the_trace_too(conn):
    vid = uuid.uuid4().hex
    cid = conversation(conn, timedelta(hours=1), vid)
    answer = message(conn, cid, at=NOW - timedelta(hours=1))
    assert conversations.delete_conversation(conn, cid, vid)
    assert answer in queued(conn)


@needs_db
def test_without_migration_0009_nothing_is_deleted(conn):
    cid = conversation(conn, timedelta(days=31))
    with conn.transaction(force_rollback=True):
        conn.execute("drop trigger messages_trace_deletion on messages")
        conn.execute("drop table trace_deletions")
        with pytest.raises(psycopg.errors.UndefinedTable):
            retention.purge(conn, NOW)
        assert exists(conn, "conversations", "id", cid)
    conn.execute("delete from conversations where id = %s", (cid,))


@needs_db
def test_traces_are_deleted_by_id_and_leave_the_queue(conn):
    cid = conversation(conn, timedelta(days=31))
    answer = message(conn, cid)
    retention.purge(conn, NOW)
    calls = []
    with langfuse(always(200, calls)) as client:
        done, ok = retention.delete_traces(conn, client, ACCESS, NOW)
    assert (done, ok) == (1, True) and queued(conn) == set()
    assert calls[0].method == "DELETE"
    assert str(calls[0].url) == "https://lf.test/api/public/traces"
    assert calls[0].headers["authorization"] == "Basic secret-auth"
    assert json.loads(calls[0].content) == {"traceIds": [answer.hex]}


def test_the_trace_id_sent_is_the_one_the_export_used():
    message_id = uuid.uuid4()
    body = tracing.build(tracing.Recorder(), tracing.Turn("q", "a", "c", str(message_id), []),
                         "local")
    assert body["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["traceId"] == message_id.hex


@needs_db
@pytest.mark.parametrize("status", [401, 429, 500])
def test_a_refused_delete_keeps_the_queue_and_stops(conn, status):
    before = {enqueue(conn, uuid.uuid4()) for _ in range(2)}
    calls = []
    with langfuse(always(status, calls)) as client:
        assert retention.delete_traces(conn, client, ACCESS, NOW) == (0, False)
    assert queued(conn) == before and len(calls) == 1


@needs_db
def test_a_network_failure_keeps_the_queue(conn):
    trace = enqueue(conn, uuid.uuid4())

    def down(request):
        raise httpx.ConnectError("no route", request=request)

    with langfuse(down) as client:
        assert retention.delete_traces(conn, client, ACCESS, NOW) == (0, False)
    assert queued(conn) == {trace}


@needs_db
def test_a_trace_from_the_last_hour_waits_for_the_next_run(conn):
    fresh = enqueue(conn, uuid.uuid4(), NOW - timedelta(minutes=5))
    calls = []
    with langfuse(always(200, calls)) as client:
        assert retention.delete_traces(conn, client, ACCESS, NOW) == (0, True)
    assert calls == [] and queued(conn) == {fresh}


@needs_db
def test_deletes_are_batched_to_spare_the_daily_limit(conn, monkeypatch):
    monkeypatch.setattr(retention, "TRACE_BATCH", 2)
    monkeypatch.setattr(retention, "MAX_TRACE_BATCHES", 2)
    for _ in range(5):
        enqueue(conn, uuid.uuid4())
    calls = []
    with langfuse(always(200, calls)) as client:
        assert retention.delete_traces(conn, client, ACCESS, NOW) == (4, True)
    assert [len(json.loads(c.content)["traceIds"]) for c in calls] == [2, 2]
    assert len(queued(conn)) == 1  # the next run takes the rest


@needs_db
def test_main_without_keys_purges_and_keeps_the_queue(monkeypatch, capsys):
    migrate.run(DB_URL)
    with psycopg.connect(DB_URL, autocommit=True) as c:  # closed: PGlite takes one client at a time
        trace = enqueue(c, uuid.uuid4())
    monkeypatch.setenv("DATABASE_URL_DIRECT", DB_URL)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")
    assert retention.main() == 0
    with psycopg.connect(DB_URL, autocommit=True) as c:
        assert trace in queued(c)
    out = capsys.readouterr().out
    assert "no Langfuse keys" in out and str(trace) not in out and trace.hex not in out


def test_main_needs_a_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL_DIRECT", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert retention.main() == 2


def test_request_addresses_stay_out_of_the_public_logs(monkeypatch):
    levels = []
    monkeypatch.setattr(retention.logging, "basicConfig", lambda level: levels.append(level))
    monkeypatch.delenv("DATABASE_URL_DIRECT", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    retention.main()
    assert levels[0] > logging.INFO  # httpx logs each request at INFO


def test_langfuse_access_needs_both_keys_and_keeps_only_the_origin():
    assert tracing.langfuse_access({"LANGFUSE_PUBLIC_KEY": "pk"}) is None
    access = tracing.langfuse_access({
        "LANGFUSE_PUBLIC_KEY": "pk", "LANGFUSE_SECRET_KEY": "sk",
        "LANGFUSE_HOST": "https://eu.lf.test/project/abc"})
    assert access.origin == "https://eu.lf.test"
    assert base64.b64decode(access.auth) == b"pk:sk"


def sweep_server(pages, deleted, get_status=200, delete_status=200, gets=None):
    """A fake Langfuse: `pages` are the bodies of successive reads."""
    pages = list(pages)

    def handler(request):
        if request.method == "GET":
            if gets is not None:
                gets.append(request)
            if get_status != 200:
                return httpx.Response(get_status)
            return httpx.Response(200, json=pages.pop(0))
        deleted.append(json.loads(request.content)["traceIds"])
        return httpx.Response(delete_status, json={"message": "ok"})
    return handler


def page(*trace_ids, cursor=None):
    return {"data": [{"id": "o", "traceId": t} for t in trace_ids],
            "meta": {"cursor": cursor} if cursor else {}}


def test_the_sweep_window_stays_inside_the_30_days_langfuse_can_read():
    assert retention.SWEEP_NEWEST < retention.SWEEP_OLDEST < retention.CONVERSATIONS
    assert timedelta(days=1) < retention.SWEEP_OLDEST - retention.SWEEP_NEWEST  # a missed run


def test_the_sweep_follows_cursors_and_keeps_one_window():
    deleted, gets = [], []
    pages = [page("a", "b", cursor="c1"), page(cursor="c2"), page("b", None, "c")]
    with langfuse(sweep_server(pages, deleted, gets=gets)) as client:
        assert retention.sweep_old_traces(client, ACCESS, NOW) == (3, True)
    assert deleted == [["a", "b", "c"]]
    assert [r.url.params.get("cursor") for r in gets] == [None, "c1", "c2"]
    for request in gets:
        assert request.url.path == "/api/public/v2/observations"
        assert request.url.params["fromStartTime"] == "2026-10-09T14:23:00Z"
        assert request.url.params["toStartTime"] == "2026-10-12T02:23:00Z"
        assert request.url.params["fields"] == "core"


def test_the_sweep_sends_nothing_to_delete_when_it_finds_nothing():
    deleted = []
    with langfuse(sweep_server([page()], deleted)) as client:
        assert retention.sweep_old_traces(client, ACCESS, NOW) == (0, True)
    assert deleted == []


def test_the_sweep_batches_and_stops_at_its_share_of_the_daily_limit(monkeypatch):
    monkeypatch.setattr(retention, "TRACE_BATCH", 2)
    monkeypatch.setattr(retention, "MAX_SWEEP_BATCHES", 2)
    deleted = []
    with langfuse(sweep_server([page("a", "b", "c", "d", "e")], deleted)) as client:
        assert retention.sweep_old_traces(client, ACCESS, NOW) == (4, True)
    assert deleted == [["a", "b"], ["c", "d"]]


def test_the_sweep_stops_at_the_page_limit(monkeypatch):
    monkeypatch.setattr(retention, "MAX_SWEEP_PAGES", 2)
    deleted, gets = [], []
    pages = [page("a", cursor="c1"), page("b", cursor="c2"), page("never")]
    with langfuse(sweep_server(pages, deleted, gets=gets)) as client:
        assert retention.sweep_old_traces(client, ACCESS, NOW) == (2, True)
    assert len(gets) == 2 and deleted == [["a", "b"]]


@pytest.mark.parametrize("status", [401, 429, 500])
def test_a_refused_read_deletes_nothing(status):
    deleted = []
    with langfuse(sweep_server([], deleted, get_status=status)) as client:
        assert retention.sweep_old_traces(client, ACCESS, NOW) == (0, False)
    assert deleted == []


@pytest.mark.parametrize("body", [{}, {"data": [{}]}, {"data": None, "meta": {}}, []])
def test_an_unexpected_read_deletes_nothing(body):
    deleted = []
    with langfuse(sweep_server([body], deleted)) as client:
        assert retention.sweep_old_traces(client, ACCESS, NOW) == (0, False)
    assert deleted == []


def test_a_refused_sweep_delete_is_a_failure():
    deleted = []
    with langfuse(sweep_server([page("a")], deleted, delete_status=500)) as client:
        assert retention.sweep_old_traces(client, ACCESS, NOW) == (0, False)


def run_main_with_keys(monkeypatch, handler):
    client = langfuse(handler)  # before the patch below: it replaces httpx.Client itself
    monkeypatch.setenv("DATABASE_URL_DIRECT", DB_URL)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    monkeypatch.setattr(retention.httpx, "Client", lambda: client)
    return retention.main()


def one_queued_trace():
    """Alone in the queue, and nothing left for main's purge to add to it. Closed afterwards:
    PGlite takes one client at a time."""
    migrate.run(DB_URL)
    with psycopg.connect(DB_URL, autocommit=True) as c:
        c.execute("delete from conversations")
        c.execute("delete from trace_deletions")
        return enqueue(c, uuid.uuid4(), datetime.now(UTC) - timedelta(days=1))


@needs_db
def test_main_runs_the_queue_and_then_the_sweep(monkeypatch, capsys):
    trace = one_queued_trace()
    deleted = []
    assert run_main_with_keys(monkeypatch, sweep_server([page("old")], deleted)) == 0
    assert deleted == [[trace.hex], ["old"]]
    out = capsys.readouterr().out
    assert "old traces accepted for deletion: 1" in out and trace.hex not in out


@needs_db
def test_main_skips_the_sweep_after_a_failed_delete_and_fails(monkeypatch):
    one_queued_trace()
    gets = []
    handler = sweep_server([page("old")], [], delete_status=500, gets=gets)
    assert run_main_with_keys(monkeypatch, handler) == 1
    assert gets == []
