"""A job match through POST /api/chat, the real pipeline and database with a scripted model.
Runs only when TEST_DATABASE_URL is set (CI, or local)."""

import json

import psycopg
from fastapi.testclient import TestClient
from test_chat import BROWSER, DB_URL, TRACES, NeverCalled, kb, pytestmark, use  # noqa: F401

from portfolio_agent.guards.quotas import Limits
from portfolio_agent.main import app
from portfolio_agent.providers.base import Finish, TextDelta, ToolCall

USAGE = {"input_tokens": 1000, "output_tokens": 100}
POSTING = "Backend Engineer. Must have Python. Must have Go. " * 8
EVIDENCE = "git-mcp-server#all"


def call(name, args):
    return [ToolCall("c", name, json.dumps(args, ensure_ascii=False)), Finish("m1", USAGE)]


def extracted():
    return call("save_requirements", {"role_title": "Backend Engineer", "requirements": [
        {"text": "Python", "kind": "must", "category": "technical",
         "query": "MCP server human approval"},
        {"text": "Go", "kind": "must", "category": "technical", "query": "Go language"},
    ]})


def rated():
    return call("save_ratings", {"ratings": [
        {"id": "r1", "strength": "strong", "evidence": [EVIDENCE], "rationale": "Built in Python."},
        {"id": "r2", "strength": "none", "evidence": [], "rationale": ""},
    ]})


def closing():
    return [TextDelta("Python is covered, and Go is the gap."), Finish("m1", USAGE)]


class Model:
    def __init__(self, *rounds):
        self.rounds = list(rounds or (extracted(), rated(), closing()))
        self.calls = []

    async def stream(self, messages, tools, **options):
        self.calls.append([dict(m) for m in messages])
        for event in self.rounds.pop(0):
            yield event


def post_job(key, message=POSTING, lang="en", **extra):
    response = BROWSER["client"].post("/api/chat", json={
        "message": message, "idempotency_key": key, "mode": "job", "lang": lang, **extra})
    assert response.status_code == 200
    return parse(response.text)


def parse(body):
    events = []
    for frame in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in frame.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def of(events, kind):
    return next(d for e, d in events if e == kind)


def counters(scope):
    with psycopg.connect(DB_URL) as conn:
        return conn.execute("select coalesce(sum(count), 0) from quota_counters where scope = %s",
                            (scope,)).fetchone()[0]


def test_the_report_comes_as_a_card_with_its_sources_and_markdown(use):  # noqa: F811
    model = Model()
    use(model)
    events = post_job("job-full-0001")
    kinds = [e for e, _ in events]
    assert "error" not in kinds and kinds[0] == "meta"
    assert kinds[-3:] == ["sources", "usage", "done"]
    assert "token" not in kinds
    card = of(events, "card")
    assert card["kind"] == "job_match"
    data = card["data"]
    assert data["overall"] == "partial" and data["gaps"] == ["Go"] and "score" not in data
    assert data["requirements"][0]["evidence"] == [EVIDENCE]
    sources = of(events, "sources")["sources"]
    assert [s["chunk_id"] for s in sources] == [EVIDENCE]
    meta = of(events, "meta")
    assert f"?report={meta['message_id']}" in card["markdown"]
    assert sources[0]["record_title"] in card["markdown"].replace("\\", "")
    usage = of(events, "usage")
    assert usage["input_tokens"] == 3000 and usage["job_match"] is True

    with psycopg.connect(DB_URL) as conn:
        rows = conn.execute(
            "select role, content, meta from messages where conversation_id = %s"
            " order by created_at", (meta["conversation_id"],)).fetchall()
    assert rows[1][1] == data["summary"]
    assert rows[1][2]["card"]["data"] == data and "markdown" not in rows[1][2]["card"]


def test_only_the_extraction_call_reads_the_posting(use):  # noqa: F811
    model = Model()
    use(model)
    post_job("job-reads-001")
    assert POSTING[:30] in str(model.calls[0])
    assert POSTING[:30] not in str(model.calls[1:])


def test_a_job_counts_as_three_messages(use):  # noqa: F811
    use(Model())
    before = counters("visitor")
    post_job("job-count-001")
    assert counters("visitor") - before == 3


def test_a_job_past_the_minute_limit_is_refused_before_any_model_call(use):  # noqa: F811
    use(Model(), NeverCalled(), limits=Limits(visitor_minute=5), frozen=True)
    assert "error" not in [e for e, _ in post_job("job-minute-01")]
    error = of(post_job("job-minute-02", message=POSTING + "x"), "error")
    assert error["code"] == "rate_limited" and error["limit"] == "minute"


def test_the_posting_limit_is_8000_characters(use):  # noqa: F811
    use(NeverCalled())
    assert of(post_job("job-toolong1", message="x" * 8001), "error")["code"] == "input_too_long"


def test_a_normal_question_keeps_its_1000_limit(use):  # noqa: F811
    use(NeverCalled())
    response = BROWSER["client"].post("/api/chat", json={
        "message": "x" * 1001, "idempotency_key": "job-question1"})
    assert of(parse(response.text), "error")["code"] == "input_too_long"


def test_a_later_turn_sees_the_report_but_not_the_posting(use):  # noqa: F811
    model = Model(extracted(), rated(), closing(), [TextDelta("Sure."), Finish("m1", USAGE)])
    use(model, model)
    first = post_job("job-history-1")
    BROWSER["client"].post("/api/chat", json={
        "message": "why is Go missing?", "idempotency_key": "job-history-2",
        "conversation_id": of(first, "meta")["conversation_id"]})
    follow_up = str(model.calls[-1])
    assert "Must have Python" not in follow_up
    assert "pasted a job posting" in follow_up and "Go is the gap" in follow_up


def test_a_resent_job_replays_the_card_without_a_model(use):  # noqa: F811
    use(Model(), NeverCalled())
    first = post_job("job-replay-01")
    again = post_job("job-replay-01")
    assert of(again, "meta")["replay"] is True
    assert of(again, "card")["data"] == of(first, "card")["data"]
    assert "token" not in [e for e, _ in again]


def test_the_same_posting_comes_from_the_cache_and_still_counts(use):  # noqa: F811
    use(Model(), NeverCalled())
    first = post_job("job-cache-001")
    before = counters("visitor")
    second = post_job("job-cache-002")
    assert of(second, "meta")["cached"] is True
    assert of(second, "card")["data"] == of(first, "card")["data"]
    assert of(second, "usage")["cached"] is True
    assert counters("visitor") - before == 3
    assert of(second, "meta")["message_id"] in of(second, "card")["markdown"]


def test_the_cache_is_per_language(use):  # noqa: F811
    use(Model(), Model())
    post_job("job-cachelang1", lang="en")
    assert "cached" not in of(post_job("job-cachelang2", lang="he"), "meta")


def test_text_with_no_requirements_says_so(use):  # noqa: F811
    use(Model(call("save_requirements", {"role_title": "", "requirements": []})))
    events = post_job("job-empty-001", message="hello there", lang="he")
    assert "לא נמצאו דרישות" in "".join(d["text"] for e, d in events if e == "token")
    assert "card" not in [e for e, _ in events]


def test_the_trace_gets_the_postings_size_not_its_text(use):  # noqa: F811
    use(Model())
    TRACES.sent.clear()
    post_job("job-trace-001")
    assert TRACES.sent and POSTING[:30] not in json.dumps(TRACES.sent[-1], ensure_ascii=False)


def test_the_link_in_the_report_opens_only_for_its_owner(use):  # noqa: F811
    use(Model())
    meta = of(post_job("job-link-0001"), "meta")
    url = f"/api/job-match/{meta['message_id']}?lang=he"
    mine = BROWSER["client"].get(url)
    assert mine.status_code == 200
    body = mine.json()
    assert body["conversation_id"] == meta["conversation_id"]
    assert body["card"]["data"]["gaps"] == ["Go"] and body["posting_chars"] == len(POSTING)
    assert "דוח התאמה למשרה" in body["card"]["markdown"]
    assert body["sources"][0]["chunk_id"] == EVIDENCE
    assert TestClient(app).get(url).status_code == 404


def test_a_posting_pasted_as_a_question_uses_the_tool_and_counts_three(use):  # noqa: F811
    tool = ToolCall("t", "match_job", json.dumps({"job_description": POSTING}))
    model = Model([tool, Finish("m1", USAGE)], extracted(), rated(), closing(),
                  [TextDelta("The report is above."), Finish("m1", USAGE)])
    use(model)
    before = counters("visitor")
    response = BROWSER["client"].post("/api/chat", json={
        "message": f"Does she fit? {POSTING}", "idempotency_key": "job-tool-0001"})
    events = parse(response.text)
    assert "error" not in [e for e, _ in events]
    assert of(events, "card")["data"]["gaps"] == ["Go"]
    assert "The report is above." in "".join(d["text"] for e, d in events if e == "token")
    assert counters("visitor") - before == 3
    assert of(events, "usage")["input_tokens"] == 5000
    assert [s["chunk_id"] for s in of(events, "sources")["sources"]] == [EVIDENCE]


# --- A posting from a screenshot (ADR-0022) ---

import base64  # noqa: E402

from test_job_read import PNG  # noqa: E402

SHOT = "data:image/png;base64," + base64.b64encode(PNG).decode()


def vision(text):
    return Model([TextDelta(text), Finish("v1", {"input_tokens": 2100, "output_tokens": 300})])


def post_image(key, image=SHOT, **extra):
    response = BROWSER["client"].post("/api/chat", json={
        "image": image, "idempotency_key": key, "mode": "job", "lang": "en", **extra})
    return response, (parse(response.text) if response.status_code == 200 else None)


def test_a_screenshot_is_read_then_matched_like_a_pasted_posting(use):  # noqa: F811
    reader, model = vision(POSTING), Model()
    use(model, vision=reader)
    _, events = post_image("shot-0001")
    names = [d.get("name") for e, d in events if e == "step"]
    assert names.index("job.read") < names.index("job.extract")
    assert [e for e, _ in events].count("meta") == 1
    assert of(events, "card")["data"]["role_title"] == "Backend Engineer"
    # Only the vision model saw the picture; the usual models got the text it read.
    assert "image_url" in json.dumps(reader.calls[0])
    assert "image_url" not in json.dumps(model.calls)
    assert "Must have Python" in model.calls[0][1]["content"]
    assert counters("image") == 1 and counters("visitor") == 4
    with psycopg.connect(DB_URL) as conn:
        saved = conn.execute("select content, meta from messages where role = 'user'"
                             " order by created_at desc limit 1").fetchone()
    assert saved[0] == "[job posting image]" and saved[1] == {"kind": "job_posting"}
    assert "base64" not in json.dumps(of(events, "usage"))


def test_a_screenshot_of_a_posting_pasted_before_answers_from_the_cache(use):  # noqa: F811
    first, second = Model(), Model()
    use(first, second, vision=vision(POSTING))
    post_job("paste-0001", message=POSTING)
    _, events = post_image("shot-0002")
    assert second.calls == []  # the text the picture gave is the text pasted: same key
    assert [e for e, _ in events].count("meta") == 1
    assert of(events, "card")["data"]["role_title"] == "Backend Engineer"
    assert "job.read" in [d.get("name") for e, d in events if e == "step"]


def test_a_picture_without_a_posting_costs_no_matching_tokens(use):  # noqa: F811
    model = Model()
    use(model, vision=vision("NONE"))
    _, events = post_image("shot-0003")
    assert not any(e == "card" for e, _ in events)
    assert "No job posting was found" in "".join(d["text"] for e, d in events if e == "token")
    assert model.calls == []


def test_a_picture_that_cannot_be_read_says_so_and_asks_for_the_text(use):  # noqa: F811
    class Down:
        async def stream(self, messages, tools, **options):
            from portfolio_agent.providers.openai_compat import ProviderError
            raise ProviderError("unavailable", "HTTP 503")
            yield  # pragma: no cover

    use(Model(), vision=Down())
    _, events = post_image("shot-0004", lang="he")
    error = of(events, "error")
    assert error["code"] == "provider_unavailable" and "להדביק" in error["message"]


def test_a_file_that_is_not_an_image_is_refused_before_anything_is_counted(use):  # noqa: F811
    use(Model(), vision=NeverCalled())
    _, events = post_image("shot-0005", image="data:image/png;base64,"
                           + base64.b64encode(b"<html>" + b"x" * 64).decode())
    assert of(events, "error")["code"] == "bad_image"
    assert counters("visitor") == 0 and counters("image") == 0


def test_a_visitor_reads_only_so_many_screenshots_a_day(use):  # noqa: F811
    use(Model(), vision=vision(POSTING), limits=Limits(image_day=1, visitor_day=30))
    post_image("shot-0006")
    use(Model(), vision=vision(POSTING), limits=Limits(image_day=1, visitor_day=30))
    _, events = post_image("shot-0007")
    assert of(events, "error")["limit"] == "image_day"
    assert counters("image") == 1  # the refused one rolled back


def test_an_image_with_a_text_is_a_bad_request(use):  # noqa: F811
    use(Model(), vision=NeverCalled())
    response = BROWSER["client"].post("/api/chat", json={
        "image": SHOT, "message": "x", "idempotency_key": "shot-0008", "mode": "job"})
    assert response.status_code == 422
