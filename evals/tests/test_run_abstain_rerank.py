import json

from retrieval.run_abstain_rerank import best_grade, grade_tool, parse_grades, summarize


def answer(grades) -> dict:
    args = json.dumps({"grades": grades})
    return {"choices": [{"message": {"tool_calls": [{"function": {"arguments": args}}]}}]}


def test_the_tool_offers_only_the_candidate_ids_and_the_four_grades():
    item = grade_tool(["a", "b"])["function"]["parameters"]["properties"]["grades"]["items"]
    assert item["properties"]["id"]["enum"] == ["a", "b"]
    assert item["properties"]["grade"]["enum"] == [0, 1, 2, 3]


def test_unknown_ids_bad_grades_and_repeats_are_dropped():
    data = answer([{"id": "a", "grade": 1}, {"id": "a", "grade": 3}, {"id": "x", "grade": 3},
                   {"id": "b", "grade": 7}, {"id": "b", "grade": True}, {"id": "c"}])
    assert parse_grades(data, ["a", "b", "c"]) == {"a": 1}


def test_no_tool_call_or_broken_json_gives_no_grades_and_no_signal():
    assert parse_grades({"choices": [{"message": {}}]}, ["a"]) == {}
    broken = {"choices": [{"message": {"tool_calls": [{"function": {"arguments": "{"}}]}}]}
    assert parse_grades(broken, ["a"]) == {}
    assert best_grade({}) is None
    assert best_grade({"a": 1, "b": 3}) == 3


def test_summary_counts_a_fallback_as_zero_and_applies_both_cuts():
    rows = [
        {"id": "p1", "split": "dev", "answerable": True, "grade": 3},
        {"id": "p2", "split": "dev", "answerable": True, "grade": 2},
        {"id": "n1", "split": "dev", "answerable": False, "grade": 1},
        {"id": "n2", "split": "dev", "answerable": False, "grade": None},
        {"id": "p3", "split": "test", "answerable": True, "grade": 1},
        {"id": "n3", "split": "test", "answerable": False, "grade": 0},
    ]
    s = summarize(rows)
    assert s["fallbacks"] == ["n2"]
    assert s["dev"]["auc"] == 1.0
    assert s["fixed_cut"]["dev"]["negatives_caught"] == ["n1", "n2"]
    assert s["fixed_cut"]["test"]["positives_lost"] == ["p3"]
    assert s["cut_from_dev"]["test"]["cut"] == 2


def test_part_two_regrades_every_question_the_cut_graded_below_two():
    from retrieval.run_abstain_rerank import to_regrade
    saved = {"grades": {"a": {"grades": {"x": 3}}, "b": {"grades": {"x": 1, "y": 0}},
                        "c": {"grades": {"x": 2}}, "d": {"grades": {}}}}
    assert to_regrade(saved) == {"b", "d"}


def test_a_request_too_large_is_tried_once_more_with_each_candidate_cut(monkeypatch):
    import httpx
    from portfolio_agent.retrieval.lexical import Hit

    from retrieval import run_abstain_rerank as m

    monkeypatch.setenv("GROQ_API_KEY_EVALS", "k")
    monkeypatch.setenv("GROQ_MODEL", "m")
    sent = []

    def handler(request):
        body = json.loads(request.content)
        sent.append(body["messages"][1]["content"])
        if len(sent) == 1:
            return httpx.Response(413, json={"error": "too large"})
        return httpx.Response(200, json={**answer([{"id": "a", "grade": 3}]),
                                         "usage": {"total_tokens": 9}})

    long_text = " ".join(["word"] * 1000)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        grade = m.groq_grader(client, m.NO_CUT)
        grades, tokens, _, cut = grade("q", [Hit("a", "a", (), long_text, {})])
    assert grades == {"a": 3} and tokens == 9 and cut == m.TOO_LARGE_CUT
    assert len(sent) == 2 and len(sent[1]) < len(sent[0])
