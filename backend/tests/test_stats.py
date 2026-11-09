"""The numbers behind /stats: the arithmetic and the privacy gate run everywhere, and the tests
against a database only when TEST_DATABASE_URL is set."""

import json
import os
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import psycopg
import pytest
from fastapi.testclient import TestClient

from portfolio_agent import chat, daily_metrics, migrate, stats
from portfolio_agent.daily_metrics import Answer, aggregate, percentile
from portfolio_agent.main import app

DB_URL = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL not set")
NOW = datetime(2026, 11, 9, 2, 23, tzinfo=UTC)
AT = NOW - timedelta(days=1)
DAY = date(2026, 11, 8)


def timed(total=1000, ttft=200, cold=False, **meta):
    return Answer(AT, "m1", {"stats": {"total_ms": total, "ttft_ms": ttft, "cold": cold}, **meta})


# Percentiles


def test_a_percentile_matches_percentile_cont():
    assert percentile([1, 2, 3, 4], 0.5) == 2.5
    assert percentile([10, 20, 30, 40, 50], 0.95) == pytest.approx(48)


def test_a_percentile_of_one_value_or_none():
    assert percentile([7], 0.95) == 7
    assert percentile([], 0.5) is None


def test_a_percentile_does_not_depend_on_the_order():
    assert percentile([3, 1, 2], 0.5) == 2


# What is measured


def test_response_times_leave_out_the_cache_and_job_matches():
    measures = aggregate([
        timed(total=1000), timed(total=3000),
        Answer(AT, "m1", {"cached": True}),
        Answer(AT, "m1", {"direct": True, "card": {"kind": "job_match"}}),
    ])
    assert measures["total_ms_p50"] == (2000, 2)


def test_first_token_is_split_by_warm_and_cold():
    measures = aggregate([timed(ttft=100), timed(ttft=300), timed(ttft=5000, cold=True)])
    assert measures["ttft_ms_warm_p50"] == (200, 2)
    assert measures["ttft_ms_cold_p50"] == (5000, 1)


def test_an_answer_with_no_first_token_counts_for_total_time_only():
    measures = aggregate([timed(ttft=None)])
    assert measures["total_ms_p50"] == (1000, 1)
    assert measures["ttft_ms_warm_p50"] == (None, 0)


def test_a_backup_model_counts_by_a_switch_or_a_closed_first_model():
    measures = aggregate([
        Answer(AT, "m1", {"switches": [{"from": "a", "reason": "rate_day"}]}),
        Answer(AT, "m2", {"stats": {"backup": True}}),
        Answer(AT, "m1", {"switches": []}),
        Answer(AT, "m1", {}),
    ])
    assert measures["fallback_rate"] == (0.5, 4)


def test_a_cached_answer_is_not_a_model_answering():
    measures = aggregate([Answer(AT, "m1", {"cached": True}), Answer(AT, "m1", {})])
    assert measures["cache_rate"] == (0.5, 2)
    assert measures["fallback_rate"] == (0.0, 1)
    assert measures["model_share:m1"] == (1.0, 1)


def test_unanswered_means_it_searched_and_cited_nothing():
    measures = aggregate([
        Answer(AT, "m1", {"cited": {}}, searched=True),
        Answer(AT, "m1", {"cited": {"x#all": 1}}, searched=True),
        Answer(AT, "m1", {"cited": ["x#all"], "cached": True}, searched=True),
        Answer(AT, "m1", {"cited": {}}),  # a greeting: nothing was looked up
        Answer(AT, "m1", {"cited": {}, "blocked": "canary"}, searched=True),
        Answer(AT, "m1", {"cited": {}, "card": {"kind": "job_match"}}, searched=True),
    ])
    assert measures["unanswered_rate"] == (pytest.approx(1 / 3), 3)


def test_removed_citations_count_per_answer():
    measures = aggregate([
        Answer(AT, "m1", {"dropped": ["a", "b"]}),
        Answer(AT, "m1", {"dropped": []}),
        Answer(AT, "m1", {"direct": True, "dropped": ["c"]}),
    ])
    assert measures["citation_removed_rate"] == (0.5, 2)


def test_satisfaction_is_up_out_of_rated():
    measures = aggregate([Answer(AT, rating="up"), Answer(AT, rating="down"), Answer(AT)])
    assert measures["satisfaction_rate"] == (0.5, 2)


def test_model_shares_add_up():
    measures = aggregate([Answer(AT, "a"), Answer(AT, "a"), Answer(AT, "a"), Answer(AT, "b")])
    assert measures["model_share:a"] == (0.75, 4)
    assert measures["model_share:b"] == (0.25, 4)


def test_nothing_observed_has_no_value():
    measures = aggregate([])
    assert measures["fallback_rate"] == (None, 0)
    assert measures["total_ms_p95"] == (None, 0)


def backup_after(models, current, switches=()):
    router = SimpleNamespace(models=[SimpleNamespace(name=m) for m in models])
    return chat._on_backup(SimpleNamespace(router=router, current=current), list(switches))


def test_the_first_model_answering_is_not_a_backup():
    assert backup_after(["a", "b"], "a") is False


def test_a_closed_first_model_leaves_no_switch_and_still_counts():
    assert backup_after(["a", "b"], "b") is True


def test_a_switch_counts_even_when_the_first_model_finished():
    assert backup_after(["a", "b"], "a", [{"from": "b", "reason": "invalid_tool"}]) is True


def test_a_provider_without_a_router_is_no_backup():
    assert chat._on_backup(object(), []) is False


def test_only_the_first_turn_of_an_instance_is_cold(monkeypatch):
    monkeypatch.setattr(chat, "_instance_is_new", True)
    assert [chat._first_turn(), chat._first_turn()] == [True, False]


# The privacy gate


def view(metric, value, size, window=7):
    return stats.public_view(DAY, [(window, metric, value, size)])["windows"][str(window)]


def test_below_the_threshold_nothing_is_shown():
    assert view("fallback_rate", 0.2, 29)["fallback_rate"] is None
    assert view("total_ms_p50", 1000, 29)["total_ms_p50"] is None


def test_at_the_threshold_it_is_shown():
    assert view("fallback_rate", 0.2, 30)["fallback_rate"] == 20


def test_each_window_has_its_own_threshold():
    body = stats.public_view(DAY, [(7, "cache_rate", 0.3, 10), (30, "cache_rate", 0.3, 40)])
    assert body["windows"]["7"]["cache_rate"] is None
    assert body["windows"]["30"]["cache_rate"] == 30


@pytest.mark.parametrize(("rate", "shown"), [
    (0, 0), (0.024, 0), (0.025, 5), (0.074, 5), (0.125, 15), (0.175, 20), (0.976, 100), (1, 100),
])
def test_rates_round_to_the_nearest_five(rate, shown):
    assert stats.percent(rate) == shown


def test_times_round_to_100_ms():
    assert stats.milliseconds(1449) == 1400
    assert stats.milliseconds(1450) == 1500


def test_no_sample_size_reaches_the_response():
    rows = [(7, "fallback_rate", 0.2, 12345), (7, "model_share:a", 1.0, 12345)]
    body = stats.public_view(DAY, rows)
    text = json.dumps(body)
    assert "12345" not in text and "sample" not in text


def test_an_unknown_metric_stays_private():
    assert "secret_rate" not in view("secret_rate", 0.5, 100)


def test_model_shares_need_the_threshold_and_a_visible_share():
    rows = [(7, "model_share:b", 0.2, 40), (7, "model_share:a", 0.79, 40),
            (7, "model_share:c", 0.01, 40), (30, "model_share:a", 1.0, 5)]
    body = stats.public_view(DAY, rows)
    assert body["windows"]["7"]["models"] == [{"model": "a", "share": 80},
                                              {"model": "b", "share": 20}]
    assert body["windows"]["30"]["models"] == []


def test_before_the_first_run_every_measure_is_empty():
    body = stats.public_view(None, [])
    assert body["updated"] is None
    assert set(body["windows"]) == {"7", "30"}
    assert all(v in (None, []) for w in body["windows"].values() for v in w.values())


def test_the_endpoint_without_a_database_is_503_and_not_cached(monkeypatch):
    monkeypatch.setattr(chat, "DEPS", chat.Deps(database_url=lambda: None))
    response = TestClient(app).get("/api/stats")
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"


# Against a database


@pytest.fixture
def clean(monkeypatch):
    migrate.run(DB_URL)
    monkeypatch.setattr(chat, "DEPS", chat.Deps(database_url=lambda: DB_URL))
    with psycopg.connect(DB_URL, autocommit=True) as c:  # closed: PGlite takes one client at a time
        c.execute("delete from daily_metrics")
        c.execute("delete from conversations")
        c.execute("delete from trace_deletions")


@pytest.fixture
def conn(clean):
    with psycopg.connect(DB_URL, autocommit=True) as c:
        yield c


def answer(conn, at, meta=None, model="m1", tool=None, rating=None, challenge=False):
    cid = conn.execute("insert into conversations default values returning id").fetchone()[0]
    mid = conn.execute(
        "insert into messages (conversation_id, role, content, model, meta, created_at)"
        " values (%s, 'assistant', 'private text', %s, %s, %s) returning id",
        (cid, model, json.dumps(meta or {}), at)).fetchone()[0]
    if tool:
        conn.execute("insert into steps (message_id, step_id, kind, name)"
                     " values (%s, 's', 'tool', %s)", (mid, tool))
    if rating:
        conn.execute("insert into feedback (message_id, rating, challenge) values (%s, %s, %s)",
                     (mid, rating, challenge))
    return mid


def stored(conn, metric, window):
    return conn.execute(
        "select value, sample_size from daily_metrics where day = %s and metric = %s"
        " and window_days = %s", (DAY, metric, window)).fetchone()


@needs_db
def test_windows_are_whole_utc_days_ending_yesterday(conn):
    midnight = datetime(2026, 11, 9, tzinfo=UTC)
    answer(conn, midnight)  # today: not a whole day yet
    answer(conn, midnight - timedelta(seconds=1))
    answer(conn, midnight - timedelta(days=7))  # first moment of the 7 days
    answer(conn, midnight - timedelta(days=7, seconds=1))  # only in the 30
    answer(conn, midnight - timedelta(days=30))
    answer(conn, midnight - timedelta(days=30, seconds=1))  # in neither
    assert daily_metrics.compute(conn, NOW) == DAY
    assert stored(conn, "fallback_rate", 7)[1] == 2
    assert stored(conn, "fallback_rate", 30)[1] == 4


@needs_db
def test_steps_and_feedback_reach_the_measures(conn):
    answer(conn, AT, {"cited": {}}, tool="search_portfolio", rating="up")
    answer(conn, AT, {"cited": {"a#all": 1}}, tool="search_portfolio", rating="down")
    answer(conn, AT, {}, tool="get_project", rating="down", challenge=True)
    daily_metrics.compute(conn, NOW)
    assert stored(conn, "unanswered_rate", 7) == (0.5, 2)
    assert stored(conn, "satisfaction_rate", 7) == (0.5, 2)


@needs_db
def test_a_second_run_replaces_the_day(conn):
    answer(conn, AT, model="old")
    daily_metrics.compute(conn, NOW)
    conn.execute("delete from conversations")
    answer(conn, AT, model="new")
    daily_metrics.compute(conn, NOW)
    assert stored(conn, "model_share:old", 7) is None
    assert stored(conn, "model_share:new", 7) == (1.0, 1)


@needs_db
def test_a_quiet_week_still_writes_a_row_for_the_day(conn):
    daily_metrics.compute(conn, NOW)
    assert stored(conn, "fallback_rate", 7) == (None, 0)
    assert stats.latest(conn)["updated"] == DAY.isoformat()


@needs_db
def test_the_rows_outlive_the_conversations(conn):
    answer(conn, AT)
    daily_metrics.compute(conn, NOW)
    conn.execute("delete from conversations")
    assert stored(conn, "fallback_rate", 7) == (0.0, 1)


@needs_db
def test_the_endpoint_reads_the_latest_day_and_is_cached_for_5_minutes(clean):
    with psycopg.connect(DB_URL, autocommit=True) as conn:
        conn.execute("insert into daily_metrics values (%s, 'cache_rate', 7, 0.1, 12345)",
                     (DAY - timedelta(days=1),))
        conn.execute("insert into daily_metrics values (%s, 'cache_rate', 7, 0.4, 12345)", (DAY,))
    response = TestClient(app).get("/api/stats")
    assert response.status_code == 200
    assert response.headers["cache-control"] == stats.CACHE
    body = response.json()
    assert body["updated"] == DAY.isoformat()
    assert body["windows"]["7"]["cache_rate"] == 40
    assert "12345" not in json.dumps(body)


@needs_db
def test_the_table_holds_no_text_from_a_conversation(conn):
    mid = answer(conn, AT, {"cited": {}}, tool="search_portfolio")
    daily_metrics.compute(conn, NOW)
    rows = conn.execute("select * from daily_metrics").fetchall()
    assert rows
    assert "private text" not in str(rows) and str(mid) not in str(rows)
