"""Judge calibration: blind sampling from a Promptfoo run, and kappa per metric."""

import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "calibration"))

import calibrate  # noqa: E402


def result(case, metric_verdicts, model="groq/openai/gpt-oss-120b"):
    out = {"answer": f"answer {case}", "model": model,
           "sources": [{"chunk_id": "a#all", "text": "source text"}],
           "turns": [{"user": f"question {case}", "answer": f"answer {case}"}]}
    return {"vars": {"id": case}, "response": {"output": out}, "gradingResult": {
        "componentResults": [{"assertion": {"type": "python", "metric": "no_error"}, "pass": True}]
        + [{"assertion": {"type": "llm-rubric", "metric": m, "value": f"rule {m}"},
            "pass": v, "reason": f"why {m}"} for m, v in metric_verdicts.items()]}}


@pytest.fixture
def run(tmp_path):
    results = [result(f"d1-{i:03d}", {"grounded": i % 3 != 0, "behavior": i % 4 != 0})
               for i in range(50)]
    results.append(result("d1-999", {"grounded": True}, model="groq/qwen/qwen3.8-27b"))
    path = tmp_path / "promptfoo-t1.json"
    path.write_text(json.dumps({"results": {"results": results}}), encoding="utf-8")
    return path


def test_the_sample_is_blind_spread_over_metrics_and_skips_the_judge_s_own_family(run, tmp_path):
    labels, judge = tmp_path / "labels.yaml", tmp_path / "judge.json"
    assert calibrate.sample(run, labels, judge) == 60
    items = yaml.safe_load(labels.read_text(encoding="utf-8"))
    assert all(i["label"] is None for i in items)
    assert not any("judge" in key for i in items for key in i)  # no verdict, no reason
    assert {m: sum(i["metric"] == m for i in items) for m in ("grounded", "behavior")} == \
        {"grounded": 30, "behavior": 30}
    assert not any(i["key"].startswith("d1-999") for i in items)
    assert all("sources" in i for i in items if i["metric"] == "grounded")
    assert all("sources" not in i for i in items if i["metric"] == "behavior")
    assert set(json.loads(judge.read_text(encoding="utf-8"))["verdicts"]) == \
        {i["key"] for i in items}


def test_a_failed_judge_call_is_not_a_verdict(tmp_path):
    # As Promptfoo 0.124.1 writes it: pass false, the error as the reason, graderError set.
    r = result("d1-001", {"grounded": True, "behavior": False})
    r["gradingResult"]["componentResults"][2]["metadata"] = {"graderError": True}
    r["gradingResult"]["componentResults"][2]["reason"] = "429 Too Many Requests"
    path = tmp_path / "run.json"
    path.write_text(json.dumps({"results": {"results": [r]}}), encoding="utf-8")
    assert [d["key"] for d in calibrate.decisions(path)] == ["d1-001/grounded"]
    assert calibrate.judge_errors(path) == ["d1-001/behavior"]


def test_labels_are_never_overwritten(run, tmp_path):
    labels, judge = tmp_path / "labels.yaml", tmp_path / "judge.json"
    calibrate.sample(run, labels, judge)
    with pytest.raises(SystemExit):
        calibrate.sample(run, labels, judge)


def test_score_gives_kappa_per_metric_and_names_the_disagreements(run, tmp_path):
    labels, judge = tmp_path / "labels.yaml", tmp_path / "judge.json"
    calibrate.sample(run, labels, judge)
    items = yaml.safe_load(labels.read_text(encoding="utf-8"))
    verdicts = json.loads(judge.read_text(encoding="utf-8"))["verdicts"]
    flipped = None
    for i in items:  # Sarah agrees with the judge, except on one grounded item and one left out
        i["label"] = verdicts[i["key"]]["judge"]
        if i["metric"] == "grounded" and flipped is None:
            flipped = i["key"]
            i["label"] = "fail" if i["label"] == "pass" else "pass"
    items[-1]["label"] = None
    labels.write_text(yaml.safe_dump(items, allow_unicode=True), encoding="utf-8")
    report = calibrate.score(labels, judge)
    assert report["unlabeled"] == [items[-1]["key"]]
    assert report["metrics"]["behavior"]["kappa"] == 1.0
    grounded = report["metrics"]["grounded"]
    assert grounded["disagreements"] == [flipped] and 0.7 < grounded["kappa"] < 1.0
    assert grounded["accepted"] and grounded["agreement"].startswith(f"{grounded['n'] - 1}/")
