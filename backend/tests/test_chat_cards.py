"""Cards through POST /api/chat: the real loop and database with a scripted model.
Runs only when TEST_DATABASE_URL is set (CI, or local)."""

import json

import psycopg
from test_chat import DB_URL, NeverCalled, Scripted, kb, post, pytestmark, search, text, use  # noqa: F401

from portfolio_agent.providers.base import Finish, TextDelta, ToolCall

RECORD = "git-mcp-server"


def show(kind, record=RECORD, call_id="c2"):
    return ToolCall(call_id, "render_card", json.dumps({"record_id": record, "kind": kind}))


def rounds(*kinds):
    calls = [show(k, call_id=f"c{i + 2}") for i, k in enumerate(kinds)]
    return ([search("human approval MCP server"), Finish("m1")],
            [*calls, Finish("m1")],
            [TextDelta(f"She built it [[{RECORD}#all]]."), Finish("m1")])


def of(events, kind):
    return [d for e, d in events if e == kind]


def test_the_card_is_sent_before_the_answer_and_its_source_with_the_sources(use):  # noqa: F811
    use(Scripted(*rounds("project", "diagram")))
    status, events = post({"message": "MCP?", "idempotency_key": "card-full-1"})
    assert status == 200 and not of(events, "error")
    cards = of(events, "card")
    assert [c["kind"] for c in cards] == ["project", "diagram"]
    assert cards[0]["data"]["record_id"] == RECORD
    assert cards[1]["data"]["mermaid"].startswith("flowchart TB")
    names = [e for e, _ in events]
    assert names.index("card") < names.index("token")
    assert f"{RECORD}#all" in [s["chunk_id"] for s in of(events, "sources")[0]["sources"]]


def test_the_step_in_the_trace_says_the_record_and_how_it_was_built(use):  # noqa: F811
    use(Scripted(*rounds("diagram")))
    _, events = post({"message": "MCP?", "idempotency_key": "card-step-1"})
    step = next(s for s in of(events, "step")
                if s["name"] == "render_card" and s["status"] == "end")
    assert step["summary"]["built_from"] == "frontmatter"
    assert step["summary"]["record_id"] == RECORD and step["summary"]["edges"] > 0


def test_a_card_is_saved_apart_from_the_job_report_and_replayed_with_no_model(use):  # noqa: F811
    use(Scripted(*rounds("project")), NeverCalled())
    _, first = post({"message": "MCP?", "idempotency_key": "card-replay-1"})
    _, again = post({"message": "MCP?", "idempotency_key": "card-replay-1"})
    assert of(again, "card") == of(first, "card")
    assert text(again) == text(first)
    with psycopg.connect(DB_URL) as conn:
        meta = conn.execute("select meta from messages where id = %s",
                            (first[0][1]["message_id"],)).fetchone()[0]
    assert len(meta["cards"]) == 1 and "card" not in meta


def test_a_first_question_with_a_card_is_cached_with_it(use):  # noqa: F811
    use(Scripted(*rounds("project")), NeverCalled())
    _, first = post({"message": "MCP cached?", "idempotency_key": "card-cache-1"})
    _, second = post({"message": "MCP cached?", "idempotency_key": "card-cache-2"})
    assert of(second, "meta")[0]["cached"] is True
    assert [c["data"] for c in of(second, "card")] == [c["data"] for c in of(first, "card")]
    sources = [s["chunk_id"] for s in of(second, "sources")[0]["sources"]]
    assert f"{RECORD}#all" in sources


def test_a_later_turn_can_show_a_project_found_earlier_without_a_new_search(use):  # noqa: F811
    use(Scripted([search("human approval MCP server"), Finish("m1")],
                 [TextDelta("Found."), Finish("m1")]),
        Scripted([show("diagram"), Finish("m1")], [TextDelta("Here it is."), Finish("m1")]))
    _, first = post({"message": "MCP?", "idempotency_key": "card-later-1"})
    _, second = post({"message": "Show the diagram", "idempotency_key": "card-later-2",
                      "conversation_id": first[0][1]["conversation_id"]})
    assert [c["kind"] for c in of(second, "card")] == ["diagram"]


def test_a_card_for_a_project_not_found_is_refused_and_the_answer_goes_on(use):  # noqa: F811
    model = Scripted([show("project", record="this-agent"), Finish("m1")],  # nothing searched yet
                     [TextDelta("No card."), Finish("m1")])
    use(model)
    _, events = post({"message": "MCP only", "idempotency_key": "card-refused-1"})
    assert of(events, "card") == []
    step = next(s for s in of(events, "step")
                if s["name"] == "render_card" and s["status"] == "end")
    assert step["summary"]["error"] == "not_retrieved"
    assert text(events) == "No card." and not of(events, "error")
