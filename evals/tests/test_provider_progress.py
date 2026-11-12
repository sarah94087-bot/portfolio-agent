"""The progress line of the Promptfoo provider: the run's log is public."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "answers"))

import provider  # noqa: E402

QUESTION, ANSWER, SECRET = "a private question", "a private answer", "a private reason"
CONTEXT = {"vars": {"id": "d1-001"}}


def result(model="gpt-oss-120b", fallback=False):
    return {"user": QUESTION, "answer": ANSWER, "model": model, "fallback": fallback,
            "tokens": {"input": 100, "output": 20}}


def test_a_case_logs_its_id_model_and_tokens_but_no_text(monkeypatch, capsys):
    monkeypatch.setattr(provider, "run", lambda turns: [result(), result("qwen", True)])
    out = provider.call_api(QUESTION, {}, CONTEXT)
    line = capsys.readouterr().err
    assert line.startswith("[case] d1-001: model gpt-oss-120b,qwen, fallback True, 240 tokens, ")
    assert QUESTION not in line and ANSWER not in line
    assert out["tokenUsage"]["total"] == 240


def test_a_failed_case_logs_the_error_type_only(monkeypatch, capsys):
    def boom(turns):
        raise ValueError(SECRET)

    monkeypatch.setattr(provider, "run", boom)
    out = provider.call_api(QUESTION, {}, CONTEXT)
    line = capsys.readouterr().err
    assert "failed with ValueError" in line and SECRET not in line
    assert SECRET in out["error"]  # the results file keeps the reason


def test_switches_and_waits_show_retry_after_and_when(monkeypatch, capsys):
    r = {**result("gpt-oss-20b", True),
         "switches": ["groq/a:rate_minute(retry 23s, at 4s)"], "waits": ["groq/a:7s@0s"]}
    monkeypatch.setattr(provider, "run", lambda turns: [r])
    provider.call_api(QUESTION, {}, CONTEXT)
    line = capsys.readouterr().err
    assert "switches groq/a:rate_minute(retry 23s, at 4s), waits groq/a:7s@0s, error none" in line


def test_the_switch_text_names_a_missing_retry_after():
    import agent  # noqa: PLC0415  (answers/, on the path above)

    assert agent._switch({"from": "a", "reason": "too_large", "retry_after": None, "at": 2.5}) \
        == "a:too_large(retry ?, at 2.5s)"
    assert agent._switch({"from": "a", "reason": "invalid_tool"}) == "a:invalid_tool"
