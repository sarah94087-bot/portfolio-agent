"""Calibrating the judge against Sarah (docs/03-evaluation-methodology.md, section 4).

    python calibration/calibrate.py sample results/promptfoo-t1-latest.json
    (Sarah fills `label` in calibration/labels.yaml: pass or fail)
    python calibration/calibrate.py score

`sample` draws about 60 of the judge's decisions from a Promptfoo run, spread over the metrics,
and writes them to labels.yaml without the judge's verdict, so Sarah labels blind. The verdicts
go to judge.json beside it. Decisions on answers that qwen wrote are left out: qwen is the
judge, and a model grading itself is what the rule of section 4 exists to avoid.

`score` pairs each label with the judge's verdict and reports Cohen's kappa per metric, with a
bootstrap interval and the raw agreement. The judge is accepted on a metric at kappa >= 0.7;
below that the rubric is fixed (rubrics.py, a new judge version) and calibrated again.
"""

import json
import random
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import yaml

EVALS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EVALS))

from stats import cohen_kappa, format_rate, kappa_interval  # noqa: E402

HERE = Path(__file__).resolve().parent
LABELS, JUDGE = HERE / "labels.yaml", HERE / "judge.json"
SAMPLE, THRESHOLD = 60, 0.7
WITH_SOURCES = {"grounded", "skill_honesty"}  # metrics Sarah cannot label without the sources
HEADER = """\
# Judge calibration (docs/03-evaluation-methodology.md, section 4). For each item, read the
# question, the answer and the rule, and write `label: pass` or `label: fail`: would you, by
# this rule, pass this answer? The judge's verdict is not here, so the labels stay blind.
# Then: python calibration/calibrate.py score
"""


def _output(result: dict) -> dict:
    out = result["response"]["output"]
    return json.loads(out) if isinstance(out, str) else out


def decisions(results_path: Path) -> list[dict]:
    """Every judge decision of a Promptfoo run, with what Sarah needs to label it."""
    run = json.loads(results_path.read_text(encoding="utf-8"))
    out = []
    for r in run["results"]["results"]:
        answer = _output(r)
        if "qwen" in (answer.get("model") or ""):
            continue  # written by the judge's own family
        for c in (r.get("gradingResult") or {}).get("componentResults", []):
            a = c.get("assertion") or {}
            if a.get("type") != "llm-rubric":
                continue
            metric = a.get("metric", "judge")
            out.append({
                "key": f"{r['vars']['id']}/{metric}",
                "metric": metric,
                "turns": answer.get("turns", []),
                "answer": answer.get("answer", ""),
                "sources": [s["text"] for s in answer.get("sources", [])]
                if metric in WITH_SOURCES else [],
                "rule": a.get("value", ""),
                "judge": "pass" if c.get("pass") else "fail",
                "judge_reason": c.get("reason", ""),
                "model": answer.get("model"),
            })
    return out


def pick(items: list[dict], n: int = SAMPLE, seed: int = 0) -> list[dict]:
    """Round robin over the metrics, so a small metric is not drowned by a large one."""
    rng = random.Random(seed)
    by_metric = defaultdict(list)
    for item in items:
        by_metric[item["metric"]].append(item)
    for group in by_metric.values():
        rng.shuffle(group)
    chosen, queues = [], [by_metric[m] for m in sorted(by_metric)]
    while len(chosen) < n and any(queues):
        for q in queues:
            if q and len(chosen) < n:
                chosen.append(q.pop())
    return chosen


def sample(results_path: Path, labels: Path = LABELS, judge: Path = JUDGE,
           force: bool = False) -> int:
    if labels.exists() and not force:
        raise SystemExit(f"{labels.name} exists; labels are never overwritten (pass --force)")
    chosen = pick(decisions(results_path))
    blind = [{
        "key": d["key"], "metric": d["metric"],
        "conversation": [{"visitor": t["user"], "agent": t["answer"]} for t in d["turns"][:-1]],
        "question": d["turns"][-1]["user"] if d["turns"] else "",
        "answer": d["answer"], **({"sources": d["sources"]} if d["sources"] else {}),
        "rule": d["rule"], "label": None,
    } for d in chosen]
    for b in blind:
        if not b["conversation"]:
            del b["conversation"]
    labels.write_text(HEADER + yaml.safe_dump(blind, allow_unicode=True, sort_keys=False,
                                              width=100), encoding="utf-8")
    judge.write_text(json.dumps({
        "results": results_path.name,
        "verdicts": {d["key"]: {"judge": d["judge"], "reason": d["judge_reason"],
                                "model": d["model"]} for d in chosen},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(chosen)


def score(labels: Path = LABELS, judge: Path = JUDGE) -> dict:
    items = yaml.safe_load(labels.read_text(encoding="utf-8")) or []
    verdicts = json.loads(judge.read_text(encoding="utf-8"))["verdicts"]
    unlabeled = [i["key"] for i in items if i.get("label") not in ("pass", "fail")]
    pairs = defaultdict(list)
    for i in items:
        if i.get("label") in ("pass", "fail"):
            pairs[i["metric"]].append((i["label"], verdicts[i["key"]]["judge"]))
    report = {"date": date.today().isoformat(), "results": json.loads(
        judge.read_text(encoding="utf-8"))["results"], "unlabeled": unlabeled, "metrics": {}}
    for metric, ps in sorted(pairs.items()):
        sarah, judged = [p[0] for p in ps], [p[1] for p in ps]
        k = cohen_kappa(sarah, judged)
        agree = sum(a == b for a, b in ps)
        report["metrics"][metric] = {
            "n": len(ps), "kappa": k, "interval": kappa_interval(sarah, judged),
            "agreement": format_rate(agree, len(ps)),
            "accepted": k is not None and k >= THRESHOLD,
            "disagreements": [i["key"] for i in items if i.get("metric") == metric
                              and i.get("label") in ("pass", "fail")
                              and i["label"] != verdicts[i["key"]]["judge"]],
        }
    return report


def _print(report: dict) -> None:
    print(f"{'metric':<16}{'n':>4}  {'kappa':>6}  {'interval':<16} agreement")
    for m, r in report["metrics"].items():
        k = "  —  " if r["kappa"] is None else f"{r['kappa']:.2f}"
        iv = "—" if r["interval"] is None else f"[{r['interval'][0]:.2f}, {r['interval'][1]:.2f}]"
        mark = "ok" if r["accepted"] else "below 0.7"
        print(f"{m:<16}{r['n']:>4}  {k:>6}  {iv:<16} {r['agreement']}  {mark}")
    if report["unlabeled"]:
        print(f"{len(report['unlabeled'])} items have no label yet")


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[1] == "sample":
        n = sample(Path(argv[2]), force="--force" in argv)
        print(f"{n} decisions written to {LABELS.relative_to(EVALS)}, verdicts to "
              f"{JUDGE.relative_to(EVALS)}")
        return 0
    if len(argv) >= 2 and argv[1] == "score":
        report = score()
        _print(report)
        out = EVALS / "results" / f"calibration-{report['date']}.json"
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"written to {out.relative_to(EVALS)}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
