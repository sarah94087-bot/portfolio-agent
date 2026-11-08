"""Builds apps/web/data/quality.json, the only data behind /quality (docs/08-transparency.md).

The web service builds from apps/web/ alone (vercel.json), so it cannot read evals/results.
This script copies the numbers across, and a test fails CI when the copy and the result files
differ. Nothing here is typed by hand except the thresholds, which come from
docs/03-evaluation-methodology.md, section 6.

Run from the repository root: backend/.venv/Scripts/python evals/publish_quality.py
"""

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "evals" / "results"
OUTPUT = ROOT / "apps" / "web" / "data" / "quality.json"

HYBRID = {
    "R1": "2026-11-04-8c5b5c3-stage2-C4-R1-Q0",
    "R2": "2026-11-04-8c5b5c3-stage2-C4-R2-multilingual-e5-small-Q0",
    "R3": "2026-11-04-8c5b5c3-stage2-C4-R3-multilingual-e5-small-Q0",
}
RERANK = {
    "R3": "2026-11-08-dca8892-stage4-C4-R3-multilingual-e5-small-Q1-R3",
    "R4": "2026-11-08-dca8892-stage4-C4-R3-multilingual-e5-small-Q1-R4-run3",
}
RERANK_COMPARISON = "2026-11-08-dca8892-stage4-C4-R3-multilingual-e5-small-Q1-run3-comparisons"

# (group, metric, threshold). The English group has no threshold of its own.
SCORECARD = [
    ("all", "recall@5", 0.90),
    ("he", "recall@5", 0.85),
    ("cross_lingual", "recall@5", 0.85),
    ("en", "recall@5", None),
    ("all", "mrr", 0.75),
]


def load(name: str) -> dict[str, Any]:
    return json.loads((RESULTS / f"{name}.json").read_text(encoding="utf-8"))


def stat(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "mean": round(value["mean"], 3),
        "low": round(value["low"], 3),
        "high": round(value["high"], 3),
        "n": value["n"],
    }


def row(method: str, result: dict[str, Any]) -> dict[str, Any]:
    groups = result["groups"]
    return {
        "method": method,
        "all": stat(groups["all"]["recall@5"]),
        "he": stat(groups["he"]["recall@5"]),
        "en": stat(groups["en"]["recall@5"]),
        "cross_lingual": stat(groups["cross_lingual"]["recall@5"]),
        "mrr": stat(groups["all"]["mrr"]),
    }


def build() -> dict[str, Any]:
    hybrid = {method: load(name) for method, name in HYBRID.items()}
    rerank = {method: load(name) for method, name in RERANK.items()}
    best = rerank["R4"]

    before = {item["id"]: item["recall@5"] for item in rerank["R3"]["items"]}
    after = {item["id"]: item["recall@5"] for item in best["items"]}
    if set(before) != set(after):
        raise ValueError("the R3 and R4 runs did not score the same questions")

    comparisons = load(RERANK_COMPARISON)["comparisons"]
    difference = {
        c["group"]: stat(c) for c in comparisons
        if c["a"] == "R3" and c["b"] == "R4" and c["metric"] == "recall@5"
    }

    scorecard = []
    for group, metric, threshold in SCORECARD:
        value = stat(best["groups"][group][metric])
        scorecard.append({
            "group": group,
            "metric": metric,
            "threshold": threshold,
            "passed": None if threshold is None else value["mean"] >= threshold,
            **value,
        })

    return {
        "schema": 1,
        "official": None,
        "latest": {
            "date": best["date"],
            "commit": best["commit"],
            "split": best["split"],
            "questions": best["n"],
            "chunks": best["chunks"],
        },
        "scorecard": scorecard,
        "hybrid": {
            "date": hybrid["R3"]["date"],
            "commit": hybrid["R3"]["commit"],
            "questions": hybrid["R3"]["n"],
            "chosen": "R3",
            "rows": [row(method, result) for method, result in hybrid.items()],
        },
        "rerank": {
            "date": best["date"],
            "commit": best["commit"],
            "questions": best["n"],
            "chosen": "R4",
            "rows": [row(method, result) for method, result in rerank.items()],
            "difference": difference,
            "improved": sum(after[q] > before[q] for q in after),
            "worsened": sum(after[q] < before[q] for q in after),
            "still_missing": sum(score < 1 for score in after.values()),
        },
    }


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(build(), indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
