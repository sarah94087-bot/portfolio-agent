"""POST /api/chat end to end: the real loop, tools, filters and database, with a scripted model.
Runs only when TEST_DATABASE_URL is set (CI, or local)."""

import json
import os

import psycopg
import pytest
from fastapi.testclient import TestClient

from portfolio_agent import chat, migrate
from portfolio_agent.agent.guard import CV_POINTER
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

    def install(*factories, enabled=True):
        providers.extend(factories)
        monkeypatch.setattr(chat, "DEPS", chat.Deps(
            database_url=lambda: DB_URL, provider=lambda: providers.pop(0),
            embedder=lambda: None, docs=lambda: kb, agent_enabled=lambda: enabled, table=TABLE,
        ))
    return install


def post(body):
    with TestClient(app) as client:
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
