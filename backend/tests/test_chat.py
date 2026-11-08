"""POST /api/chat end to end: the real loop, tools, filters and database, with a scripted model.
Runs only when TEST_DATABASE_URL is set (CI, or local)."""

import json
import os
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from portfolio_agent import chat, migrate
from portfolio_agent.agent.guard import CV_POINTER
from portfolio_agent.guards import visitor
from portfolio_agent.guards.quotas import Limits
from portfolio_agent.ingest import chunk, load, upsert
from portfolio_agent.main import app
from portfolio_agent.providers.base import Finish, TextDelta, ToolCall
from portfolio_agent.providers.router import AllModelsFailed

DB_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL not set")
TABLE = "chat_kb"


class Scripted:
    def __init__(self, *rounds):
        self.rounds = list(rounds)
        self.calls = []

    async def stream(self, messages, tools):
        self.calls.append([dict(m) for m in messages])
        for event in self.rounds.pop(0):
            if isinstance(event, Exception):
                raise event
            yield event


class NeverCalled:
    async def stream(self, messages, tools):
        raise AssertionError("the model must not be called")
        yield  # pragma: no cover


@pytest.fixture(scope="module")
def kb():
    docs = load()
    migrate.run(DB_URL)
    with psycopg.connect(DB_URL, autocommit=True) as conn:
        conn.execute(f"drop table if exists {TABLE}")
        conn.execute(f"create table {TABLE} (like chunks including all)")
        upsert(conn, chunk(docs, "C4"), TABLE)
    yield docs
    with psycopg.connect(DB_URL, autocommit=True) as conn:
        conn.execute(f"drop table {TABLE}")


@pytest.fixture
def use(kb, monkeypatch):
    """Point the endpoint at the test database and a provider made per request."""
    providers = []

    def install(*factories, enabled=True, limits=None):
        providers.extend(factories)
        monkeypatch.setattr(chat, "DEPS", chat.Deps(
            database_url=lambda: DB_URL, provider=lambda quota: providers.pop(0),
            embedder=lambda: None, ranker=lambda: None, docs=lambda: kb,
            agent_enabled=lambda: enabled,
            limits=lambda: limits or Limits(), tracer=lambda: TRACES, table=TABLE,
        ))
        BROWSER["client"] = TestClient(app)  # one visitor per test, keeping its cookie
        with psycopg.connect(DB_URL, autocommit=True) as conn:
            conn.execute("delete from response_cache")  # no test answers from another's
    return install


BROWSER = {}


class Traces:
    """Stands in for the Langfuse exporter: keeps what would have been sent."""

    environment = "test"

    def __init__(self):
        self.sent = []

    async def send(self, body, client):
        self.sent.append(body)
        return True


TRACES = Traces()


def post(body, client=None):
    client = client or BROWSER["client"]
    response = client.post("/api/chat", json=body)
    if response.status_code != 200:
        return response.status_code, []
    events = []
    for frame in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in frame.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return 200, events


def text(events):
    return "".join(d["text"] for e, d in events if e == "token")


def search(query):
    return ToolCall("c1", "search_portfolio", json.dumps({"query": query}))


ANSWER = ("She built an MCP server where every write needs human approval [[git-mcp-server#all]]"
          " [[made-up#all]]. Call 050-1234567 to ask more about this project, any time.")


def test_a_full_turn_streams_in_order_and_saves_what_the_visitor_saw(use):
    model = Scripted([search("human approval MCP server"), Finish("m1", {"input_tokens": 9})],
                     [TextDelta(ANSWER[:40]), TextDelta(ANSWER[40:]), Finish("m1")])
    use(model)
    status, events = post({"message": "האם היא בנתה שרת MCP?", "idempotency_key": "key-full-1"})
    assert status == 200
    kinds = [e for e, _ in events]
    assert kinds[0] == "meta" and kinds[-3:] == ["sources", "usage", "done"]
    assert "error" not in kinds
    meta = events[0][1]
    assert [d for e, d in events if e == "citation"] == [
        {"chunk_id": "git-mcp-server#all", "index": 1, "v": 1}]
    shown = text(events)
    assert "[[" not in shown and "1234567" not in shown and CV_POINTER["en"] in shown
    sources = next(d for e, d in events if e == "sources")["sources"]
    assert [s["chunk_id"] for s in sources] == ["git-mcp-server#all"]
    assert sources[0]["record_title"].startswith("grounded-git-mcp")
    assert "commit" in sources[0]
    usage = next(d for e, d in events if e == "usage")
    assert usage["dropped"] == 1 and usage["redacted"] == 1  # made-up#all, the phone
    assert 0 <= usage["setup_ms"] <= usage["total_ms"]

    with psycopg.connect(DB_URL) as conn:
        rows = conn.execute(
            "select role, content, meta, prompt_version from messages"
            " where conversation_id = %s order by created_at", (meta["conversation_id"],),
        ).fetchall()
        steps = conn.execute(
            "select kind, name, args, result_summary from steps where message_id = %s"
            " order by id", (meta["message_id"],),
        ).fetchall()
    assert [r[0] for r in rows] == ["user", "assistant"]
    stored = rows[1][1]
    assert "[[git-mcp-server#all]]" in stored and "made-up" not in stored
    assert "1234567" not in stored
    assert rows[1][2]["dropped"] == ["made-up#all"] and rows[1][2]["redacted"] == 1
    assert "git-mcp-server#all" in rows[1][2]["allowed_chunks"]
    assert rows[1][3] == "system.v1"
    tool = next(s for s in steps if s[0] == "tool_result")
    assert tool[2] == {"query": "human approval MCP server"}  # args from the start of the step
    assert tool[3]["method"] == "R1"  # summary from its end


def test_a_resent_message_is_replayed_without_calling_the_model(use):
    model = Scripted([search("MCP"), Finish("m1")],
                     [TextDelta("It is here [[git-mcp-server#all]]."), Finish("m1")])
    use(model, NeverCalled())
    _, first = post({"message": "MCP?", "idempotency_key": "key-replay-1"})
    _, again = post({"message": "MCP?", "idempotency_key": "key-replay-1"})
    assert text(again) == text(first) == "It is here ."
    assert [d for e, d in again if e == "citation"] == [d for e, d in first if e == "citation"]
    assert again[0][1]["replay"] is True
    assert again[0][1]["message_id"] == first[0][1]["message_id"]
    assert next(d for e, d in again if e == "usage")["output_tokens"] == 0


def test_a_question_resent_after_a_drop_is_saved_once_and_counted_once(use):
    # The stream breaks after the question was saved and before the answer was (US-10.5).
    retried = Scripted([TextDelta("Hi."), Finish("m", {})])
    use(Scripted([TextDelta("She built"), RuntimeError("connection cut")]), retried,
        limits=Limits(conversation=1))  # a second count of the question would refuse the retry
    _, cut = post({"message": "MCP?", "idempotency_key": "key-drop-1"})
    assert cut[-2][1]["code"] == "internal"
    cid = cut[0][1]["conversation_id"]
    _, again = post({"message": "MCP?", "idempotency_key": "key-drop-1"})
    assert again[0][1]["conversation_id"] == cid and text(again) == "Hi."
    assert [m["content"] for m in retried.calls[0] if m["role"] == "user"] == ["MCP?"]
    with psycopg.connect(DB_URL) as conn:
        roles = [r for (r,) in conn.execute(
            "select role from messages where conversation_id = %s order by created_at", (cid,))]
    assert roles == ["user", "assistant"]


def test_record_titles_come_in_the_page_s_language_also_on_a_replay(use):
    use(Scripted([search("human approval MCP server"), Finish("m1")],
                 [TextDelta("Yes [[git-mcp-server#all]]."), Finish("m1")]))
    body = {"message": "MCP?", "idempotency_key": "key-lang-1", "lang": "he"}
    _, events = post(body)
    title = next(d for e, d in events if e == "sources")["sources"][0]["record_title"]
    assert title.startswith("grounded-git-mcp: שרת MCP")
    _, replayed = post({**body, "lang": "en"})  # the same message, read on the English page
    title = next(d for e, d in replayed if e == "sources")["sources"][0]["record_title"]
    assert title.startswith("grounded-git-mcp: a local Git MCP server")
    assert post({**body, "idempotency_key": "key-lang-2", "lang": "fr"})[0] == 422


def test_the_next_turn_sees_the_history_and_may_cite_what_was_retrieved_before(use):
    first = Scripted([search("MCP"), Finish("m")],
                     [TextDelta("Yes [[git-mcp-server#all]]."), Finish("m")])
    second = Scripted([TextDelta("As I said [[git-mcp-server#all]]."), Finish("m")])
    use(first, second)
    _, e1 = post({"message": "MCP?", "idempotency_key": "key-hist-1"})
    cid = e1[0][1]["conversation_id"]
    _, e2 = post({"message": "ועוד?", "conversation_id": cid, "idempotency_key": "key-hist-2"})
    assert e2[0][1]["conversation_id"] == cid
    sent = second.calls[0]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "user"]
    assert sent[2]["content"] == "Yes [[git-mcp-server#all]]."  # markers kept for the model
    assert [d["chunk_id"] for e, d in e2 if e == "citation"] == ["git-mcp-server#all"]


def test_too_long_a_message_is_refused_before_anything_runs(use):
    use(NeverCalled())
    _, events = post({"message": "x" * 1001, "idempotency_key": "key-long-1"})
    assert [e for e, _ in events] == ["error", "done"]
    assert events[0][1]["code"] == "input_too_long" and events[0][1]["retryable"] is False


def test_when_every_model_is_out_of_quota_the_error_says_so(use):
    use(Scripted([AllModelsFailed("quota_exhausted", [])]))
    _, events = post({"message": "hi", "idempotency_key": "key-quota-1"})
    assert events[0][0] == "meta"
    error = next(d for e, d in events if e == "error")
    assert error["code"] == "quota_exhausted" and error["retryable"] is True
    assert events[-1][0] == "done"


def test_the_kill_switch_stops_the_agent(use):
    use(NeverCalled(), enabled=False)
    _, events = post({"message": "hi", "idempotency_key": "key-off-1"})
    assert events[0][1]["code"] == "provider_unavailable"


def test_a_malformed_request_is_rejected(use):
    use()
    assert post({"message": "hi", "idempotency_key": "bad key!"})[0] == 422
    assert post({"message": "", "idempotency_key": "key-empty-1"})[0] == 422


def answer(model="m1", usage=None):
    return Scripted([TextDelta("Hi."), Finish(model, usage or {})])


def test_a_visitor_gets_a_signed_cookie_kept_for_30_days_and_its_id_on_the_conversation(use):
    use(answer())
    response = BROWSER["client"].post("/api/chat",
                                      json={"message": "hi", "idempotency_key": "key-cookie-1"})
    header = response.headers["set-cookie"]
    assert header.startswith(f"{visitor.COOKIE}=") and "HttpOnly" in header
    assert "Max-Age=2592000" in header and "SameSite=lax" in header
    vid = visitor.read_cookie(response.cookies[visitor.COOKIE])
    cid = next(json.loads(f.split("data: ", 1)[1]) for f in response.text.split("\n\n")
               if f.startswith("event: meta"))["conversation_id"]
    with psycopg.connect(DB_URL) as conn:
        assert conn.execute("select visitor_id from conversations where id = %s",
                            (cid,)).fetchone()[0] == vid


def test_another_visitor_cannot_continue_or_replay_a_conversation(use):
    use(Scripted([TextDelta("Mine."), Finish("m")]), answer(), answer())
    _, mine = post({"message": "hi", "idempotency_key": "key-owner-1"})
    cid = mine[0][1]["conversation_id"]
    stranger = TestClient(app)  # no cookie: another visitor
    _, theirs = post({"message": "and?", "conversation_id": cid,
                      "idempotency_key": "key-owner-2"}, stranger)
    assert theirs[0][1]["conversation_id"] != cid  # a new conversation, not mine
    _, replayed = post({"message": "something else", "idempotency_key": "key-owner-1"}, stranger)
    assert "replay" not in replayed[0][1] and text(replayed) == "Hi."


def test_a_forged_cookie_is_replaced_by_a_new_visitor(use):
    use(answer())
    forged = TestClient(app, cookies={visitor.COOKIE: "someone-else.AAAAAAAAAAAAAAAAAAAAAA"})
    response = forged.post("/api/chat", json={"message": "hi", "idempotency_key": "key-forge-1"})
    assert visitor.read_cookie(response.cookies[visitor.COOKIE]) not in (None, "someone-else")


def test_past_the_minute_limit_the_error_is_rate_limited_and_nothing_is_saved(use):
    use(answer(), answer(), NeverCalled(), limits=Limits(visitor_minute=2))
    post({"message": "one", "idempotency_key": "key-rate-1"})
    post({"message": "two", "idempotency_key": "key-rate-2"})
    _, events = post({"message": "three", "idempotency_key": "key-rate-3"})
    assert [e for e, _ in events] == ["error", "done"]
    error = events[0][1]
    assert error["code"] == "rate_limited" and error["limit"] == "minute"
    assert error["retryable"] is True and 0 < error["retry_after"] <= 60
    with psycopg.connect(DB_URL) as conn:
        assert conn.execute("select count(*) from messages where content = 'three'"
                            ).fetchone()[0] == 0
    _, again = post({"message": "one", "idempotency_key": "key-rate-1"})
    assert again[0][1]["replay"] is True  # a resent message is free, even past the limit


def test_the_turn_s_tokens_are_counted_against_its_model(use):
    model = f"m-{uuid.uuid4().hex}"
    use(answer(model, {"input_tokens": 120, "output_tokens": 30}))
    post({"message": "hi", "idempotency_key": "key-spend-1"})
    with psycopg.connect(DB_URL) as conn:
        assert conn.execute("select count from quota_counters where scope = 'provider_tokens'"
                            " and key = %s", (model,)).fetchone()[0] == 150


def test_the_tokens_go_under_the_router_s_name_for_the_model(use):
    """The router closes a model by its own name, so a shorter one would never close it."""
    model = f"m-{uuid.uuid4().hex}"
    provider = answer(model, {"input_tokens": 100, "output_tokens": 50})
    provider.current = f"groq/{model}"
    use(provider)
    post({"message": "hi", "idempotency_key": "key-spend-2"})
    with psycopg.connect(DB_URL) as conn:
        assert conn.execute("select count from quota_counters where scope = 'provider_tokens'"
                            " and key = %s", (f"groq/{model}",)).fetchone()[0] == 150


def test_the_same_first_question_is_answered_from_the_cache_with_its_trace(use):
    model = Scripted([search("human approval MCP server"), Finish("m1")],
                     [TextDelta("Yes [[git-mcp-server#all]]."), Finish("m1")])
    later = Scripted([TextDelta("As said [[git-mcp-server#all]]."), Finish("m1")])
    use(model, later)  # a hit takes no provider at all
    _, first = post({"message": "Did she build an MCP server?", "idempotency_key": "key-cache-1"})
    other = TestClient(app)  # another visitor, a new conversation, the question written loosely
    _, hit = post({"message": "  did she build an MCP   server ", "idempotency_key": "key-cache-2"},
                  other)
    meta = hit[0][1]
    assert meta["cached"] is True and meta["cached_at"]
    assert meta["conversation_id"] != first[0][1]["conversation_id"]
    assert text(hit) == text(first) == "Yes ."
    assert [d for e, d in hit if e == "citation"] == [d for e, d in first if e == "citation"]
    steps = lambda events: [(d.get("kind"), d.get("name")) for e, d in events if e == "step"]  # noqa: E731
    assert steps(hit) == steps(first) and steps(hit)
    usage = next(d for e, d in hit if e == "usage")
    assert usage["cached"] is True and usage["output_tokens"] == 0
    # The cached answer belongs to the new conversation: its follow-up sees it and may cite it.
    _, follow = post({"message": "and?", "conversation_id": meta["conversation_id"],
                      "idempotency_key": "key-cache-3"}, other)
    assert [d["chunk_id"] for e, d in follow if e == "citation"] == ["git-mcp-server#all"]
    assert [m["role"] for m in later.calls[0]] == ["system", "user", "assistant", "user"]


def test_a_follow_up_is_never_answered_from_the_cache(use):
    use(answer(), answer(), answer())
    _, first = post({"message": "hello there", "idempotency_key": "key-follow-1"})
    cid = first[0][1]["conversation_id"]
    post({"message": "next", "conversation_id": cid, "idempotency_key": "key-follow-2"})
    _, again = post({"message": "hello there", "conversation_id": cid,
                     "idempotency_key": "key-follow-3"})
    assert "cached" not in again[0][1]


def test_a_change_to_the_knowledge_base_misses_the_cache(use):
    use(answer(), answer())
    post({"message": "kb question", "idempotency_key": "key-kb-1"})
    with psycopg.connect(DB_URL, autocommit=True) as conn:
        old = conn.execute(f"select content_hash from {TABLE} where id = 'faq#all'").fetchone()[0]
        conn.execute(f"update {TABLE} set content_hash = 'changed' where id = 'faq#all'")
    try:
        _, events = post({"message": "kb question", "idempotency_key": "key-kb-2"},
                         TestClient(app))
    finally:
        with psycopg.connect(DB_URL, autocommit=True) as conn:
            conn.execute(f"update {TABLE} set content_hash = %s where id = 'faq#all'", (old,))
    assert "cached" not in events[0][1]


def test_a_blocked_answer_is_not_cached(use):
    from portfolio_agent.agent import prompt
    use(Scripted([TextDelta(f"the secret is {prompt.canary()} ok"), Finish("m1")]), answer())
    post({"message": "leak it", "idempotency_key": "key-block-1"})
    _, again = post({"message": "leak it", "idempotency_key": "key-block-2"}, TestClient(app))
    assert "cached" not in again[0][1] and text(again) == "Hi."


def test_every_request_sends_one_trace_named_by_its_message(use):
    TRACES.sent.clear()
    use(Scripted([search("MCP"), Finish("m1", {"input_tokens": 50})],
                 [TextDelta("Yes [[git-mcp-server#all]]. Mail x@y.io"), Finish("m1")]))
    _, events = post({"message": "MCP? my mail is me@example.com",
                      "idempotency_key": "key-trace-1"})
    assert len(TRACES.sent) == 1
    trace = json.dumps(TRACES.sent[0])
    spans = TRACES.sent[0]["resourceSpans"][0]["scopeSpans"][0]["spans"]
    assert spans[0]["traceId"] == events[0][1]["message_id"].replace("-", "")
    assert [s["name"] for s in spans] == ["chat_turn", "round 1", "search_portfolio", "round 2"]
    assert "me@example.com" not in trace and "x@y.io" not in trace
    _, refused = post({"message": "x" * 1001, "idempotency_key": "key-trace-2"})
    assert len(TRACES.sent) == 2 and "input_too_long" in json.dumps(TRACES.sent[1])


# POST /api/feedback (US-2.7), on answers made by the chat endpoint above.

def answered(key):
    _, events = post({"message": "MCP?", "idempotency_key": key})
    return events[0][1]


def rate(body, client=None):
    return (client or BROWSER["client"]).post("/api/feedback", json=body).status_code


def stored_feedback(message_id):
    with psycopg.connect(DB_URL) as conn:
        return conn.execute("select rating, comment, challenge from feedback where message_id = %s",
                            (message_id,)).fetchone()


def test_a_thumbs_down_keeps_a_masked_comment_and_a_change_of_mind_replaces_it(use):
    use(answer())
    mid = answered("key-fb-1")["message_id"]
    assert rate({"message_id": mid, "rating": "down"}) == 204
    assert stored_feedback(mid) == ("down", None, False)  # saved at once, before any comment
    assert rate({"message_id": mid, "rating": "down", "challenge": True,
                 "comment": "  wrong number, write to me@example.com or 050-1234567  "}) == 204
    rating, comment, challenge = stored_feedback(mid)
    assert rating == "down" and challenge is True
    assert "example.com" not in comment and "1234567" not in comment
    assert comment.startswith("wrong number") and not comment.endswith(" ")
    assert rate({"message_id": mid, "rating": "up", "comment": "ignored",
                 "challenge": True}) == 204
    assert stored_feedback(mid) == ("up", None, False)


def test_only_the_visitor_who_got_the_answer_may_rate_it(use):
    use(answer(), answer())
    meta = answered("key-fb-2")
    assert rate({"message_id": meta["message_id"], "rating": "down"}, TestClient(app)) == 404
    stranger = TestClient(app)  # a visitor with a cookie of their own
    post({"message": "hello", "idempotency_key": "key-fb-2b"}, stranger)
    assert rate({"message_id": meta["message_id"], "rating": "down"}, stranger) == 404
    assert rate({"message_id": str(uuid.uuid4()), "rating": "down"}) == 404
    with psycopg.connect(DB_URL) as conn:
        question = conn.execute(
            "select id from messages where conversation_id = %s and role = 'user'",
            (meta["conversation_id"],)).fetchone()[0]
    assert rate({"message_id": str(question), "rating": "down"}) == 404  # not an answer
    assert stored_feedback(meta["message_id"]) is None


def test_feedback_is_limited_per_visitor_and_checked_for_length(use):
    use(answer(), limits=Limits(feedback_day=2))
    mid = answered("key-fb-3")["message_id"]
    assert rate({"message_id": mid, "rating": "down", "comment": "x" * 301}) == 422
    assert rate({"message_id": mid, "rating": "down", "comment": "x" * 300}) == 204
    assert rate({"message_id": mid, "rating": "up"}) == 204
    assert rate({"message_id": mid, "rating": "down"}) == 429
    assert stored_feedback(mid)[0] == "up"


def test_feedback_goes_with_its_conversation(use):
    use(answer())
    meta = answered("key-fb-4")
    assert rate({"message_id": meta["message_id"], "rating": "up"}) == 204
    with psycopg.connect(DB_URL, autocommit=True) as conn:
        conn.execute("delete from conversations where id = %s", (meta["conversation_id"],))
    assert stored_feedback(meta["message_id"]) is None


# DELETE /api/conversations/{id} (US-12.4).

def counts(conversation_id, message_id):
    with psycopg.connect(DB_URL) as conn:
        return tuple(conn.execute(q, (p,)).fetchone()[0] for q, p in [
            ("select count(*) from conversations where id = %s", conversation_id),
            ("select count(*) from messages where conversation_id = %s", conversation_id),
            ("select count(*) from steps where message_id = %s", message_id),
            ("select count(*) from feedback where message_id = %s", message_id),
        ])


def test_a_visitor_deletes_their_conversation_with_its_messages_steps_and_feedback(use):
    use(Scripted([search("MCP"), Finish("m1")],
                 [TextDelta("Yes [[git-mcp-server#all]]."), Finish("m1")]),
        answer())
    meta = answered("key-del-1")
    cid, mid = meta["conversation_id"], meta["message_id"]
    assert rate({"message_id": mid, "rating": "down", "comment": "x"}) == 204
    assert counts(cid, mid) == (1, 2, 3, 1)

    stranger = TestClient(app)
    post({"message": "hello", "idempotency_key": "key-del-1b"}, stranger)
    assert stranger.delete(f"/api/conversations/{cid}").status_code == 404
    assert TestClient(app).delete(f"/api/conversations/{cid}").status_code == 404  # no cookie
    assert counts(cid, mid) == (1, 2, 3, 1)

    assert BROWSER["client"].delete(f"/api/conversations/{cid}").status_code == 204
    assert counts(cid, mid) == (0, 0, 0, 0)
    assert BROWSER["client"].delete(f"/api/conversations/{cid}").status_code == 404  # gone


def test_a_message_to_a_deleted_conversation_starts_a_new_one(use):
    use(answer(), answer())
    cid = answered("key-del-2")["conversation_id"]
    assert BROWSER["client"].delete(f"/api/conversations/{cid}").status_code == 204
    _, events = post({"message": "again", "idempotency_key": "key-del-3", "conversation_id": cid})
    assert events[0][1]["conversation_id"] != cid and text(events) == "Hi."
