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
